from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.models import POSTING_STATUSES

PostingStatus = Literal[POSTING_STATUSES]  # ("draft", "open", "closed")


def _reject_past(value: date | None) -> date | None:
    """지난 날짜를 마감일로 받지 않는다 (B4).

    받아 두면 저장하는 순간 이미 마감된 공고가 되어, 담당자는 만들자마자 닫힌
    공고를 보게 된다. 오타를 그때 알려주는 편이 낫다. 오늘은 허용한다 —
    "오늘까지 접수"가 정상적인 요구다.
    """
    if value is not None and value < date.today():
        raise ValueError("마감일은 오늘 이후여야 합니다")
    return value


class PostingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: PostingStatus = "draft"
    deadline: date | None = None  # B4. NULL = 상시 접수

    _check_deadline = field_validator("deadline")(_reject_past)


class PostingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: PostingStatus | None = None
    deadline: date | None = None

    # 보낸 필드만 반영하므로(exclude_unset) 이 검사는 deadline 을 실제로 보낼 때만 돈다.
    # `null` 을 명시적으로 보내면 마감일을 지우는 뜻이고, 그건 막지 않는다.
    _check_deadline = field_validator("deadline")(_reject_past)


class PostingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: str
    deadline: date | None = None
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    application_count: int = 0  # B3 — 집계 쿼리로 채운다. 컬럼이 아니다

    @computed_field
    @property
    def d_day(self) -> int | None:
        """마감까지 남은 일수. 화면이 `D-12` 로 표시한다 (B4).

        컬럼이 아니라 응답 시점에 계산한다 — 날짜가 바뀌면 값도 바뀌어야 하는데
        저장해 두면 어제 계산한 값이 그대로 남는다. 마감일이 없으면 null.
        지난 날짜면 음수다(`D+3` 표시는 화면이 판단한다).
        """
        if self.deadline is None:
            return None
        return (self.deadline - date.today()).days


class PublicLinkOut(BaseModel):
    """공개 지원 링크 발급 결과 (B6)."""

    public_token: str
    url: str
