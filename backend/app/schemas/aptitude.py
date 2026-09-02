"""사전 성향 설문 스키마 (ADR-0027)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.aptitude_questions import LIKERT_MAX, LIKERT_MIN


class SessionOut(BaseModel):
    """담당자용. 링크는 서버가 조립한다 (AI 면접 SessionOut 과 같은 판단)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    status: str
    token: str
    url: str
    expires_at: datetime | None
    submitted_at: datetime | None
    created_at: datetime


class BulkSendOut(BaseModel):
    """공고 단위 일괄 발송 결과. 몇 건이 왜 빠졌는지 숫자로 남긴다 —
    "보냈다"만 돌려주면 담당자가 빠진 사람을 찾을 방법이 없다."""

    sent: int
    skipped_already_sent: int
    skipped_stage: int


class AnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_key: str
    question_text: str
    value: int


class CategoryStatOut(BaseModel):
    """카테고리 평균 — 코드가 계산한다. LLM 이 죽어도 이 표는 뜬다."""

    category: str
    label: str
    mean: float
    count: int


class AptitudeDetailOut(BaseModel):
    """지원자 상세 패널용. 세션이 없으면 status='none' 뿐이다.

    통계·응답 원문을 요약과 나란히 내려준다 — 요약이 원문을 왜곡하면
    대조로 드러나야 한다 (ADR-0027).
    """

    status: str  # none | pending | done | expired
    url: str | None = None
    expires_at: datetime | None = None
    submitted_at: datetime | None = None
    answers: list[AnswerOut] = []
    stats: list[CategoryStatOut] = []
    ai_summary: str | None = None
    ai_summary_model: str | None = None


class PublicQuestionOut(BaseModel):
    key: str
    text: str


class AptitudePublicOut(BaseModel):
    """지원자용. 토큰·담당자 정보를 되돌려주지 않는다 (AI 면접과 같은 규칙)."""

    status: str
    applicant_name: str
    posting_title: str
    expires_at: datetime | None
    # pending 일 때만 문항을 내려준다 — 제출 뒤에는 보여 줄 이유가 없다
    questions: list[PublicQuestionOut] = []
    likert_labels: dict[int, str] = {}


class AnswerIn(BaseModel):
    key: str
    value: int = Field(ge=LIKERT_MIN, le=LIKERT_MAX)


class SubmitRequest(BaseModel):
    """전 문항 응답. 부분 제출은 받지 않는다 — 반쯤 남은 설문은 통계를 왜곡한다."""

    answers: list[AnswerIn]
