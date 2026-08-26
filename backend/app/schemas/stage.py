from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StageChangeRequest(BaseModel):
    to_stage: str
    # D8 — 불합격 사유. rejected 일 때는 필수인데, 그 검사는 라우터에서 한다.
    # 여기서 막으면 "to_stage 에 따라 달라지는 필수"를 표현하느라 스키마가 복잡해지고,
    # 422 메시지도 "불합격은 사유를 입력해야 합니다" 처럼 사람이 읽을 문장이 안 된다.
    reason: str | None = None


class StageChangeOut(BaseModel):
    """단계 변경 결과. 화면이 낙관적 업데이트를 되돌릴 때 쓸 값만 담는다."""

    model_config = ConfigDict(from_attributes=True)

    application_id: int
    from_stage: str
    to_stage: str
    changed_by: int
    changed_at: datetime
    mail_queued: bool  # 지원자에게 통지 메일이 큐에 올라갔는지 (G1)


class BulkStageRequest(BaseModel):
    """여러 명 한 번에 (D9)."""

    # 빈 목록은 막는다 — 아무것도 안 바꾸는 요청은 실수일 가능성이 높다.
    # 상한(200)은 라우터에서 본다. 여기서 막으면 422 메시지가 "입력 형식이
    # 잘못되었습니다" 로만 나가 담당자가 몇 명까지 되는지 알 수 없다.
    application_ids: list[int] = Field(min_length=1)
    to_stage: str
    reason: str | None = None


class BulkStageOut(BaseModel):
    changed: int  # 실제로 단계가 바뀐 인원
    changed_ids: list[int]
    skipped: list[int]  # 이미 그 단계였던 건. 실패가 아니다
    mail_queued: int  # 큐에 올라간 통지 메일 수 (건별로 한 통)
