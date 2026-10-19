"""자동 심사 설정 (ADR-0034) — 가중치와 인재상. admin 전용.

    GET /settings/scoring   지금 값 (없으면 기본값이 채워져 온다)
    PUT /settings/scoring   가중치·인재상을 바꾼다. 보낸 키만 반영

가중치는 company_profile.scoring_weights JSON 한 곳에 산다. 키·기본값·합산 규칙은
app/application/screening.py 가 원본이다 — 여기서는 저장과 조회만 한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.application import screening
from app.hiring.company import get_profile
from app.db import get_db
from app.deps import require_roles
from app.models import User

router = APIRouter(prefix="/api/v1", tags=["scoring"])


class ScoringWeights(BaseModel):
    """각 값 0~100. 묶음의 합이 100이 아니어도 된다 — 합으로 나눈다(screening._weighted)."""

    doc: int = Field(ge=0, le=100)
    interview: int = Field(ge=0, le=100)
    doc_requirements: int = Field(ge=0, le=100)
    doc_preferred: int = Field(ge=0, le=100)
    doc_culture: int = Field(ge=0, le=100)
    itv_answers: int = Field(ge=0, le=100)
    itv_truth: int = Field(ge=0, le=100)


class ScoringWeightsIn(ScoringWeights):
    """저장할 때만 묶음 합을 본다 — 이미 저장된 값이 어긋나 있어도 GET 은 열려야 한다."""

    @model_validator(mode="after")
    def _each_group_counts(self) -> "ScoringWeightsIn":
        # 한 묶음이 전부 0 이면 _weighted 가 None 을 내고, 서류 점수가 영영 안 생겨
        # 자동 심사가 전원 "보류" 로 멈춘다. 관리자 화면이 막지만 API 로도 막는다.
        for name, keys in _WEIGHT_GROUPS.items():
            if sum(getattr(self, k) for k in keys) <= 0:
                raise ValueError(f"{name} 비중이 전부 0 이면 점수를 계산할 수 없습니다")
        return self


# 합으로 나누는 묶음 셋 (screening.doc_score_from · interview_score_from · final_score)
_WEIGHT_GROUPS: dict[str, tuple[str, ...]] = {
    "서류 점수 안의": ("doc_requirements", "doc_preferred", "doc_culture"),
    "면접 점수 안의": ("itv_answers", "itv_truth"),
    "최종 점수의": ("doc", "interview"),
}


class ScoringOut(BaseModel):
    weights: ScoringWeights
    talent_profile: str | None
    defaults: ScoringWeights
    grade_bounds: dict[str, int]


class ScoringUpdate(BaseModel):
    weights: ScoringWeightsIn | None = None
    talent_profile: str | None = None


def _out(db: Session) -> ScoringOut:
    profile = get_profile(db)
    return ScoringOut(
        weights=ScoringWeights(**screening.weights(db)),
        talent_profile=profile.talent_profile,
        defaults=ScoringWeights(**screening.DEFAULT_WEIGHTS),
        grade_bounds={letter: bound for bound, letter in screening.GRADE_BOUNDS},
    )


@router.get("/settings/scoring", response_model=ScoringOut)
def get_scoring(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    return _out(db)


@router.put("/settings/scoring", response_model=ScoringOut)
def put_scoring(
    body: ScoringUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    """보낸 키만 바꾼다. 가중치를 보내면 7개 전부를 받는다 — 일부만 바꾸면 합이 어긋난다."""
    profile = get_profile(db)
    if body.weights is not None:
        profile.scoring_weights = body.weights.model_dump()
    if body.talent_profile is not None:
        profile.talent_profile = body.talent_profile.strip() or None
    db.commit()
    return _out(db)
