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


class SearchResult(BaseModel):
    items: list[ApplicationListItem]
    total: int
    took_ms: float
