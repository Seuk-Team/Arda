from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import POSTING_STATUSES

PostingStatus = Literal[POSTING_STATUSES]  # ("draft", "open", "closed")


class PostingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    status: PostingStatus = "draft"


class PostingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    status: PostingStatus | None = None


class PostingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: str
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    application_count: int = 0  # B3 — 집계 쿼리로 채운다. 컬럼이 아니다
