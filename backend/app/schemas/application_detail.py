from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StageHistoryOut(BaseModel):
    """단계 변경 이력 한 건 (D5). 최신순은 relationship 의 order_by 가 보장한다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    from_stage: str | None  # 최초 접수 시 None
    to_stage: str
    changed_by: int | None  # None = 시스템(외부 지원 접수)
    created_at: datetime


class EvaluationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evaluator_id: int
    score: int
    comment: str | None
    created_at: datetime


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    body: str
    created_at: datetime


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str  # 원본 파일명
    kind: str
    size_bytes: int
    content_type: str
    created_at: datetime
    # s3_key 는 내려보내지 않는다. 다운로드는 presigned URL(F1) 로 따로 발급한다


class ApplicationListItem(BaseModel):
    """목록용. self_intro 를 넣지 않는다 — 5천 자 × 100건이면 응답이 수 MB 가 된다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    current_stage: str
    career_years: int | None
    created_at: datetime


class ApplicationDetail(BaseModel):
    """상세용. 패널이 한 번에 그릴 수 있도록 자식 4종을 함께 담는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    job_posting_id: int
    name: str
    email: str
    phone: str
    education: str | None
    career_years: int | None
    skills: list[str] | None
    self_intro: str | None

    ai_summary: str | None
    ai_summary_at: datetime | None

    current_stage: str
    source: str
    created_at: datetime
    updated_at: datetime

    stage_history: list[StageHistoryOut] = []
    evaluations: list[EvaluationOut] = []
    notes: list[NoteOut] = []
    files: list[FileOut] = []

    avg_score: float | None = None  # 평가 평균. 평가가 없으면 None


class ManualApplicationCreate(BaseModel):
    """담당자 직접 등록(D6) 요청 본문.

    외부 지원(C1)과 달리 privacy_agreed_at 을 **받는다**. 서버가 now() 로 지어내지 않는다.
    담당자가 대신 동의를 체크할 수 없기 때문이다 — 동의는 메일·전화로 이미 받았을 수 있고,
    그 실제 시각이 기록돼야 한다. 서버 시각을 넣으면 동의한 적 없는 시각이 동의 기록이 된다.
    """

    name: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=20)
    education: str | None = Field(default=None, max_length=100)
    career_years: int | None = None
    skills: list[str] | None = None
    self_intro: str | None = None
    privacy_agreed_at: datetime  # 필수. 없으면 422
