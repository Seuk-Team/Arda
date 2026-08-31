"""면접 일정 제안 (일정 자동화, ADR-0016) 요청·응답 형태."""

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProposalCreate(BaseModel):
    """일정 제안 생성 요청. 본문 없이도 기본값으로 동작한다."""

    slot_minutes: int = Field(60, ge=15, le=240, description="슬롯 길이(분)")
    max_slots: int = Field(5, ge=1, le=20, description="후보 슬롯 최대 개수")
    expires_at: datetime | None = Field(None, description="선택 기한. NULL = 무기한")

    @model_validator(mode="after")
    def _check_expires(self) -> "ProposalCreate":
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise ValueError("expires_at 은 시간대(+09:00 등)를 포함해야 합니다")
            if self.expires_at <= datetime.now(timezone.utc):
                raise ValueError("expires_at 은 미래여야 합니다")
        return self


class SlotOut(BaseModel):
    """후보 슬롯 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    interviewer_id: int
    interviewer_name: str | None = None  # 담당자 화면 표시용 — 라우터가 채운다
    start_at: datetime
    end_at: datetime


class PublicSlotOut(BaseModel):
    """지원자에게 보여주는 슬롯 — 면접관 정보는 노출하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    start_at: datetime
    end_at: datetime


class SchedulePublicOut(BaseModel):
    """지원자용 일정·전형 현황 (공개, 토큰 접근)."""

    status: str  # proposed / confirmed / expired
    applicant_name: str
    posting_title: str
    current_stage: str  # 전형 진행 현황 — 링크 하나로 일정과 함께 확인한다
    expires_at: datetime | None
    slots: list[PublicSlotOut]
    confirmed_slot: PublicSlotOut | None  # confirmed 때만 값 존재


class ConfirmRequest(BaseModel):
    """지원자의 슬롯 선택."""

    slot_id: int


class ProposalStatusOut(BaseModel):
    """담당자 화면용 최신 제안 상태 — 대시보드·상세 패널이 칩 하나를 그리는 용도."""

    status: str  # proposed / confirmed / expired / canceled
    confirmed_slot: PublicSlotOut | None
    expires_at: datetime | None
    created_at: datetime


class ProposalOut(BaseModel):
    """일정 제안 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    token: str
    status: str
    expires_at: datetime | None
    url: str  # 지원자에게 나가는 공개 선택 링크
    slots: list[SlotOut]
    mail_queued: bool  # 제안 메일이 큐에 실렸는가 (실패해도 제안 자체는 유효)
    created_at: datetime
