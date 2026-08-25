from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StageChangeRequest(BaseModel):
    to_stage: str


class StageChangeOut(BaseModel):
    """단계 변경 결과. 화면이 낙관적 업데이트를 되돌릴 때 쓸 값만 담는다."""

    model_config = ConfigDict(from_attributes=True)

    application_id: int
    from_stage: str
    to_stage: str
    changed_by: int
    changed_at: datetime
    mail_queued: bool  # 지원자에게 통지 메일이 큐에 올라갔는지 (G1)
