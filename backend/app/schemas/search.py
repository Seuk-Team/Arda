from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_posting_id: int
    name: str
    email: str
    current_stage: str
    career_years: int | None = None
    created_at: datetime
    # sort=score 일 때만 채운다. 평가가 없으면 null — 0 이 아니다 (0 은 "0점을 받았다"로 읽힌다)
    avg_score: float | None = None


class SearchResult(BaseModel):
    items: list[ApplicationListItem]
    total: int
    took_ms: float
    # 다음 페이지가 없으면 null. 깊은 페이지에서는 offset 대신 이것을 쓴다 (H5)
    next_cursor: str | None = None
