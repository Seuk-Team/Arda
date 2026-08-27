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

PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-5": (5.00, 25.00),
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICING.get(model, (1.00, 5.00))
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000


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
    model: str = ""


def _describe_action(name: str, args: dict) -> str:
    """사용자에게 보여줄 확인 메시지를 만든다."""
    if name == "change_stage":
        return f"지원자 #{args.get('application_id')}의 단계를 '{args.get('to_stage')}'(으)로 변경합니다"
    if name == "assign_interviewer":
        ids = args.get("interviewer_ids", [])
        return f"지원자 #{args.get('application_id')}에 면접관 {ids}을(를) 배정합니다"
    if name == "draft_email":
        purpose = args.get("purpose", "general")
        return f"지원자 #{args.get('application_id')}에게 '{purpose}' 이메일 초안을 생성합니다"
    return f"{name} 실행"


def run_agent(
    message: str,
    history: list[dict],
    db: Session,
    user: User,
    system_prompt: str,
) -> AgentResult:
    """에이전트 대화 루프를 실행한다. 동기 호출."""
    try:
        import anthropic
    except ImportError:
        return AgentResult(reply="anthropic 패키지가 설치되지 않았습니다.")

    client = anthropic.Anthropic()

    messages = list(history)
    messages.append({"role": "user", "content": message})

    tools = TOOL_DEFINITIONS

    result = AgentResult(reply="", model=AGENT_MODEL)

    for _ in range(MAX_ROUNDS):
        response = client.messages.create(
            model=AGENT_MODEL,
            max_tokens=4096,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        result.input_tokens += response.usage.input_tokens
        result.output_tokens += response.usage.output_tokens

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
            logger.info("pending_write_tool", extra={"tool": write_tool.name, "input": write_tool.input})
            result.tool_calls.append({"name": write_tool.name, "input": write_tool.input})

            texts = [b.text for b in response.content if b.type == "text"]
            result.reply = "\n".join(texts) if texts else ""
            result.pending_action = PendingAction(
                tool_name=write_tool.name,
                arguments=write_tool.input,
                description=_describe_action(write_tool.name, write_tool.input),
            )
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tu in tool_uses:
            logger.info("tool_call", extra={"tool": tu.name, "input": tu.input})
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

    cost = _estimate_cost(AGENT_MODEL, result.input_tokens, result.output_tokens)
    logger.info(
        "agent_run",
        extra={
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "tool_calls": len(result.tool_calls),
            "cost_usd": round(cost, 6),
        },
    )

    return result
