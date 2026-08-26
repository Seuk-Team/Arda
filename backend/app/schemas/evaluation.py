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
    """평가 수정 스키마 — 부분 수정(PATCH).

    두 필드 모두 선택이다. 02-api.md 가 "score·comment 부분 수정 허용"으로
    규정하는데 `score` 를 필수로 두면 코멘트만 고칠 수 없고, `comment` 를 빼고
    보내면 기존 코멘트가 지워진다. 보낸 필드만 반영한다(`exclude_unset`).

    `None` 을 **명시적으로** 보내면 코멘트를 비우는 뜻이다. 아예 안 보내는 것과
    다르다 — 그 구분이 `exclude_unset` 의 존재 이유다.
    """
    score: int | None = Field(default=None, ge=1, le=5, description="평가 점수 1~5")
    comment: str | None = None


class EvaluationSummary(BaseModel):
    """평가 목록 + 평균 응답 (D1과 형식 통일)."""
    items: list[EvaluationOut]
    count: int
    avg_score: float | None  # 평가가 없으면 null (0이 아니다)
