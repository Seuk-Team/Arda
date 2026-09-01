"""에이전트 실행 루프 (M3+M4).

사용자 메시지 → Claude (도구 포함) → tool_use 파싱 → 실행 → 반복
텍스트 응답이 나오면 종료.

M4: 쓰기 도구(change_stage, assign_interviewer, draft_email)는
즉시 실행하지 않고 pending_action 으로 반환한다.
프론트에서 확인 카드를 표시하고, 사용자가 승인하면 /confirm 이 실행한다.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import User

from .tools import TOOL_DEFINITIONS, WRITE_TOOL_NAMES, execute_tool

logger = logging.getLogger(__name__)

AGENT_MODEL = os.getenv("AGENT_CHAT_MODEL", "claude-haiku-4-5-20251001")
MAX_ROUNDS = 10

# 대화 이력 상한 (메시지 개수 = user/assistant 쌍 × 2).
# 이력은 라운드마다 통째로 재전송되므로 상한이 없으면 대화가 길어질수록
# 호출당 입력이 선형으로, 대화 전체 비용은 제곱으로 늘어난다.
MAX_HISTORY_MESSAGES = 20

# 프롬프트 캐시 요율 (입력 단가 기준) — 쓰기 1.25배, 읽기 0.1배
CACHE_WRITE_RATE = 1.25
CACHE_READ_RATE = 0.10

PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-5": (5.00, 25.00),
}


def _estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """호출 비용(USD) 추정.

    캐시를 켜면 캐시로 처리된 몫이 input_tokens 에서 빠진다. 캐시 항을 더하지
    않으면 비용이 실제보다 작게 나온다 — 아낀 것이 아니라 안 보이는 것이다.
    """
    input_price, output_price = PRICING.get(model, (1.00, 5.00))
    return (
        input_tokens * input_price
        + cache_write_tokens * input_price * CACHE_WRITE_RATE
        + cache_read_tokens * input_price * CACHE_READ_RATE
        + output_tokens * output_price
    ) / 1_000_000


@dataclass
class PendingAction:
    tool_name: str
    arguments: dict
    description: str


@dataclass
class AgentResult:
    reply: str
    tool_calls: list[dict] = field(default_factory=list)
    pending_action: PendingAction | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    model: str = ""


_STAGE_KR = {
    "applied": "접수",
    "screening": "서류심사",
    "interview": "면접",
    "accepted": "합격",
    "rejected": "불합격",
}

_PURPOSE_KR = {
    "interview": "면접 안내",
    "accepted": "합격 안내",
    "rejected": "불합격 안내",
    "general": "일반 안내",
}


def _applicant_label(db: Session, application_id: int | None) -> str:
    """지원자 ID → '김도현(서울대 컴공)' 형태. 못 찾으면 '#ID'."""
    if application_id is None:
        return "지원자"
    from app.models import Application
    app = db.get(Application, int(application_id))
    if app is None:
        return f"지원자 #{application_id}"
    parts = [app.name]
    if app.education:
        parts.append(f"({app.education})")
    return " ".join(parts)


def _describe_action(name: str, args: dict, db: Session) -> str:
    """사용자에게 보여줄 확인 메시지를 만든다."""
    label = _applicant_label(db, args.get("application_id"))
    if name == "change_stage":
        to = _STAGE_KR.get(args.get("to_stage", ""), args.get("to_stage", ""))
        return f"{label}을(를) {to} 단계로 변경합니다"
    if name == "assign_interviewer":
        ids = args.get("interviewer_ids", [])
        return f"{label}에 면접관 {len(ids)}명을 배정합니다"
    if name == "create_schedule_proposal":
        max_slots = args.get("max_slots", 5)
        return f"{label}에게 면접 일정 후보 {max_slots}개를 제안합니다"
    if name == "draft_email":
        purpose = _PURPOSE_KR.get(args.get("purpose", "general"), "안내")
        return f"{label}에게 {purpose} 이메일 초안을 생성합니다"
    if name == "send_email":
        # **한 줄 요약으로 끝내지 않는다.** 메일은 되돌릴 수 없어서, 승인하는
        # 사람이 실제로 나갈 제목·본문을 그대로 읽고 눌러야 한다. 프론트 확인
        # 카드가 arguments 의 subject·body 를 따로 렌더하고, 이 문장은 그
        # 위에 붙는 머리말이다.
        return f"{label}에게 아래 내용으로 메일을 발송합니다"
    return f"{name} 실행"


def _trim_history(history: list[dict]) -> list[dict]:
    """대화 이력을 최근 MAX_HISTORY_MESSAGES 개로 자른다.

    Anthropic 규칙상 messages 는 user 로 시작해야 하므로, 자른 뒤 맨 앞이
    assistant 면 짝이 맞을 때까지 더 버린다.
    """
    trimmed = history[-MAX_HISTORY_MESSAGES:]
    while trimmed and trimmed[0].get("role") != "user":
        trimmed = trimmed[1:]
    return trimmed


def run_agent(
    message: str,
    history: list[dict],
    db: Session,
    user: User,
    system_prompt: str,
    request_id: str | None = None,
) -> AgentResult:
    """에이전트 대화 루프를 실행한다. 동기 호출."""
    try:
        import anthropic
    except ImportError:
        return AgentResult(reply="anthropic 패키지가 설치되지 않았습니다.")

    client = anthropic.Anthropic()

    messages = _trim_history(history)
    messages.append({"role": "user", "content": message})

    tools = TOOL_DEFINITIONS

    result = AgentResult(reply="", model=AGENT_MODEL)

    rounds = 0

    for _ in range(MAX_ROUNDS):
        rounds += 1
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=4096,
            # 고정부(도구 정의 + 시스템 프롬프트 ≈ 20KB)를 캐시한다. 렌더 순서가
            # tools → system → messages 라, 마지막 system 블록의 표시가 도구까지
            # 함께 묶는다. 두 번째 호출부터 이 몫이 0.1배 요금이 된다.
            # 캐시가 걸렸는지는 cache_read_tokens 로 확인한다 (0이면 안 걸린 것).
            system=[{
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=tools,
            messages=messages,
        )

        usage = response.usage
        result.input_tokens += usage.input_tokens
        result.output_tokens += usage.output_tokens
        # 캐시 필드는 캐시를 쓰지 않는 응답에는 없거나 None 이다
        result.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        result.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

        if response.stop_reason == "end_turn":
            texts = [b.text for b in response.content if b.type == "text"]
            result.reply = "\n".join(texts)
            break

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            texts = [b.text for b in response.content if b.type == "text"]
            result.reply = "\n".join(texts) if texts else "응답을 생성할 수 없습니다."
            break

        # 쓰기 도구가 포함되어 있으면 실행하지 않고 확인 요청으로 반환
        write_tool = next((tu for tu in tool_uses if tu.name in WRITE_TOOL_NAMES), None)
        if write_tool:
            # 인자 값에는 지원자 이름·이메일이 들어올 수 있다. 키 이름만 남긴다 (J5)
            logger.info(
                "pending_write_tool",
                extra={"tool": write_tool.name, "tool_args": sorted(write_tool.input)},
            )
            result.tool_calls.append({"name": write_tool.name, "input": write_tool.input})

            texts = [b.text for b in response.content if b.type == "text"]
            result.reply = "\n".join(texts) if texts else ""
            result.pending_action = PendingAction(
                tool_name=write_tool.name,
                arguments=write_tool.input,
                description=_describe_action(write_tool.name, write_tool.input, db),
            )
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tu in tool_uses:
            logger.info("tool_call", extra={"tool": tu.name, "tool_args": sorted(tu.input)})
            result.tool_calls.append({"name": tu.name, "input": tu.input})

            output = execute_tool(tu.name, tu.input, db, user)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": output,
            })

        messages.append({"role": "user", "content": tool_results})
    else:
        result.reply = "도구 호출 횟수 제한에 도달했습니다. 질문을 더 구체적으로 해주세요."

    cost = _estimate_cost(
        AGENT_MODEL,
        result.input_tokens,
        result.output_tokens,
        result.cache_write_tokens,
        result.cache_read_tokens,
    )
    logger.info(
        "agent_run",
        extra={
            "request_id": request_id,
            "user_id": user.id,
            "model": AGENT_MODEL,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cache_write_tokens": result.cache_write_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "rounds": rounds,
            "tool_calls": len(result.tool_calls),
            "cost_usd": round(cost, 6),
        },
    )

    return result
