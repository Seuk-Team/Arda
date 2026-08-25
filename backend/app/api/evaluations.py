from datetime import datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, Evaluation
from app.schemas.application_detail import EvaluationOut
from app.schemas.evaluation import (
    EvaluationCreate,
    EvaluationSummary,
    EvaluationUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["evaluations"])


class EvaluationCreateResponse(BaseModel):
    """평가 생성 응답. evaluator_id는 인증 추가 후 채워진다."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    score: int
    comment: str | None
    created_at: datetime


@router.post(
    "/applications/{application_id}/evaluations",
    response_model=EvaluationCreateResponse,
    status_code=HTTPStatus.CREATED,
)
def create_evaluation(
    application_id: int, body: EvaluationCreate, db: Session = Depends(get_db)
):
    """평가 작성 (E1)."""
    # 지원자 존재 확인
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 평가 생성
    evaluation = Evaluation(
        application_id=application_id,
        evaluator_id=None,  # TODO(A1): 토큰의 사용자로 채운다
        score=body.score,
        comment=body.comment,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    return evaluation


@router.get("/applications/{application_id}/evaluations", response_model=EvaluationSummary)
def list_evaluations(application_id: int, db: Session = Depends(get_db)):
    """평가 목록 + 평균 (E2)."""
    # 지원자 존재 확인
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 최신순으로 평가 조회
    rows = db.scalars(
        select(Evaluation)
        .where(Evaluation.application_id == application_id)
        .order_by(Evaluation.created_at.desc())
    ).all()

    # 평균 계산
    # 평가가 없을 때 0을 주면 "0점을 받았다"로 읽힌다.
    # null이어야 "아직 평가가 없음"으로 이해된다.
    scores = [e.score for e in rows]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    return EvaluationSummary(
        items=[EvaluationOut.model_validate(e) for e in rows],
        count=len(rows),
        avg_score=avg_score,
    )


@router.patch("/evaluations/{evaluation_id}", response_model=EvaluationOut)
def update_evaluation(
    evaluation_id: int,
    body: EvaluationUpdate,
    db: Session = Depends(get_db),
):
    """평가 수정 (E5 - 본인만 가능)."""
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "평가를 찾을 수 없습니다")

    # TODO(A1): 본인 평가만 수정 가능한지 검사 (evaluator_id == 토큰의 사용자)

    evaluation.score = body.score
    evaluation.comment = body.comment
    db.commit()
    db.refresh(evaluation)

    return evaluation
