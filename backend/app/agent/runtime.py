"""에이전트 실행 루프 (M3+M4).

사용자 메시지 → LLM (도구 포함) → tool_use 파싱 → 실행 → 반복
텍스트 응답이 나오면 종료.

M4: 쓰기 도구(change_stage, assign_interviewer, draft_email)는
즉시 실행하지 않고 pending_action 으로 반환한다.
프론트에서 확인 카드를 표시하고, 사용자가 승인하면 /confirm 이 실행한다.

실제 LLM 호출과 도구 루프는 `app.agent.backends` 의 어댑터가 맡는다. 이 모듈은
DB·사용자 같은 앱 개념을 `ToolRunner` 로 묶어 넘기고, 결과를 로깅한다.
백엔드 선택은 `AGENT_CHAT_BACKEND` (기본 anthropic).
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import User

from .backends import get_chat_backend
from .backends.anthropic_backend import (  # noqa: F401  (기존 임포트 경로 유지)
    AGENT_MODEL,
    CACHE_READ_RATE,
    CACHE_WRITE_RATE,
    PRICING,
    _estimate_cost,
)
from .backends.base import (  # noqa: F401  (기존 임포트 경로 유지)
    MAX_HISTORY_MESSAGES,
    MAX_ROUNDS,
    AgentResult,
    PendingAction,
    trim_history,
)
from .tools import TOOL_DEFINITIONS, WRITE_TOOL_NAMES, execute_tool

logger = logging.getLogger(__name__)

__all__ = [
    "AGENT_MODEL",
    "MAX_HISTORY_MESSAGES",
    "MAX_ROUNDS",
    "PRICING",
    "AgentResult",
    "PendingAction",
    "run_agent",
]

# 이력 자르기는 백엔드 공통이라 backends.base 로 옮겼다. 이름은 유지한다.
_trim_history = trim_history


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


class _DbToolRunner:
    """어댑터가 쓰는 도구 통로. DB 세션·사용자를 어댑터 밖에 붙잡아 둔다."""

    definitions = TOOL_DEFINITIONS

    def __init__(self, db: Session, user: User, compact: bool = False):
        self._db = db
        self._user = user
        # 백엔드 프로필에 따라 도구 결과를 줄일지. 어댑터가 결과 형태를 알 필요는
        # 없으므로 축소는 여기(앱 쪽)에서 하고, 어댑터는 플래그만 알린다.
        self._compact = compact

    def is_deferred(self, name: str) -> bool:
        return name in WRITE_TOOL_NAMES

    def describe(self, name: str, arguments: dict) -> str:
        return _describe_action(name, arguments, self._db)

    def execute(self, name: str, arguments: dict) -> str:
        return execute_tool(
            name, arguments, self._db, self._user, compact=self._compact
        )


def run_agent(
    message: str,
    history: list[dict],
    db: Session,
    user: User,
    system_prompt: str,
    request_id: str | None = None,
) -> AgentResult:
    """에이전트 대화 루프를 실행한다. 동기 호출."""
    backend = get_chat_backend()

    result = backend.run_chat(
        message=message,
        history=history,
        system_prompt=system_prompt,
        tools=_DbToolRunner(db, user, compact=backend.compact_tool_results),
        request_id=request_id,
    )

    logger.info(
        "agent_run",
        extra={
            "request_id": request_id,
            "user_id": user.id,
            # 모델명만으로는 부족하다 — 토크나이저가 달라 백엔드 간 토큰 비교가
            # 불가능하므로 backend:model 로 남긴다.
            "model": result.model,
            "backend": result.backend,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "cache_write_tokens": result.cache_write_tokens,
            "cache_read_tokens": result.cache_read_tokens,
            "rounds": result.rounds,
            "tool_calls": len(result.tool_calls),
            "cost_usd": round(result.cost_usd, 6),
        },
    )

    return result
