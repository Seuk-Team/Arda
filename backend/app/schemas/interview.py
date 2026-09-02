"""AI 면접 스키마 (ADR-0026).

설계는 docs/02_tasks/AI면접-설계.md.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SessionCreate(BaseModel):
    """담당자가 면접을 만들 때. 전부 선택값이다 — 기본값으로 충분하다."""

    # 링크 유효 기간. 비우면 서버 기본값(7일)
    expires_in_days: int | None = Field(default=None, ge=1, le=30)


class SessionOut(BaseModel):
    """담당자용. 토큰과 링크를 함께 준다 — 링크를 화면이 조립하지 않는다.

    치환을 화면에 맡기면 미리보기와 실제가 갈린다 (메일 프리필과 같은 판단).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: str
    token: str
    url: str
    expires_at: datetime | None
    consented_at: datetime | None
    started_at: datetime | None
    ended_at: datetime | None
    created_at: datetime


class TurnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    seq: int
    question: str
    transcript: str | None
    audio_duration_sec: float | None


class FindingOut(BaseModel):
    """서류 주장 ↔ 면접 발언 대조 한 건.

    **점수가 없다.** 갈래는 셋뿐이고 판단은 사람이 한다 (ADR-0026 · ADR-0003).
    양쪽 원문을 그대로 내려주는 이유는 지원자가 반박할 수 있어야 하기 때문이다.
    """

    model_config = ConfigDict(from_attributes=True)

    claim_source: str
    claim_text: str
    answer_text: str
    verdict: str


class SessionDetailOut(SessionOut):
    """담당자용 상세 — 전사와 대조 결과까지."""

    turns: list[TurnOut] = []
    findings: list[FindingOut] = []


class InterviewPublicOut(BaseModel):
    """지원자용. **토큰과 URL 을 되돌려주지 않는다** — 이미 가진 사람만 본다.

    지원자에게 필요한 것은 "내가 누구의 어느 면접에 와 있는가"와 "지금 뭘 하면
    되는가"뿐이다. 담당자 이름·평가·다른 지원자는 내려주지 않는다.
    """

    status: str
    applicant_name: str
    posting_title: str
    expires_at: datetime | None
    consent_required: bool
    # 진행 중일 때 현재 질문. pending 이면 None
    current_question: str | None = None
    question_seq: int | None = None


class ConsentRequest(BaseModel):
    """녹음·전사·보관 동의. 지원 폼의 개인정보 동의와 별개다."""

    agreed: bool
