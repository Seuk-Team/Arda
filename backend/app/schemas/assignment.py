from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AssignRequest(BaseModel):
    """면접관 배정 요청."""
    interviewer_ids: list[int] = Field(min_items=1, description="배정할 면접관 ID 목록")


class AssignmentOut(BaseModel):
    """배정 관계 응답."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    interviewer_id: int
    assigned_by: int | None = None  # TODO(A1): 토큰의 사용자로 채운다
    created_at: datetime


class AssignmentListOut(BaseModel):
    """배정된 면접관 목록 응답."""
    items: list[AssignmentOut]
    count: int


class AssignResponse(BaseModel):
    """배정 완료 응답."""
    assigned: list[int]  # 실제로 배정된 면접관 ID 목록
