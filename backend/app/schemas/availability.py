"""면접관 가용 시간 (일정 자동화, ADR-0016) 요청·응답 형태."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class AvailabilityCreate(BaseModel):
    """가용 시간 등록 요청."""

    start_at: datetime
    end_at: datetime

    @model_validator(mode="after")
    def _check_range(self) -> "AvailabilityCreate":
        # naive datetime 은 서버 시간대 해석에 따라 슬롯이 밀린다 — 아예 받지 않는다
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("start_at·end_at 은 시간대(+09:00 등)를 포함해야 합니다")
        if self.start_at >= self.end_at:
            raise ValueError("start_at 은 end_at 보다 앞서야 합니다")
        return self


class AvailabilityOut(BaseModel):
    """가용 시간 응답."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    interviewer_id: int
    start_at: datetime
    end_at: datetime
    created_at: datetime


class AvailabilityListOut(BaseModel):
    """가용 시간 목록 응답."""

    items: list[AvailabilityOut]
    count: int
