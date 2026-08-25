from pydantic import BaseModel, Field

from app.schemas.application_detail import EvaluationOut


class EvaluationCreate(BaseModel):
    """평가 작성 스키마.

    DB에 체크 제약이 있지만 여기서도 코드로 막는다.
    제약만 믿으면 IntegrityError가 500으로 나가고, 화면이 사용자에게 설명할 수 없다.
    API는 정규화된 에러(422)를 줘야 사용자가 이해한다.
    """
    score: int = Field(ge=1, le=5, description="평가 점수 1~5")
    comment: str | None = None


class EvaluationUpdate(BaseModel):
    """평가 수정 스키마."""
    score: int = Field(ge=1, le=5, description="평가 점수 1~5")
    comment: str | None = None


class EvaluationSummary(BaseModel):
    """평가 목록 + 평균 응답 (D1과 형식 통일)."""
    items: list[EvaluationOut]
    count: int
    avg_score: float | None  # 평가가 없으면 null (0이 아니다)
