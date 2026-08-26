from datetime import datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import assert_can_view_application, get_current_user
from app.models import Application, Evaluation, User
from app.schemas.application_detail import EvaluationOut
from app.schemas.evaluation import (
    EvaluationCreate,
    EvaluationSummary,
    EvaluationUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["evaluations"])


class EvaluationCreateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    evaluator_id: int
    score: int
    comment: str | None
    created_at: datetime


@router.post(
    "/applications/{application_id}/evaluations",
    response_model=EvaluationCreateResponse,
    status_code=HTTPStatus.CREATED,
)
def create_evaluation(
    application_id: int,
    body: EvaluationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """평가 작성 (E1). 작성자는 토큰의 사용자다."""
    # 지원자 존재 확인
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    assert_can_view_application(db, user, application_id)

    evaluation = Evaluation(
        application_id=application_id,
        evaluator_id=user.id,
        score=body.score,
        comment=body.comment,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)

    return evaluation


@router.get("/applications/{application_id}/evaluations", response_model=EvaluationSummary)
def list_evaluations(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """평가 목록 + 평균 (E2)."""
    # 지원자 존재 확인
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 지원자를 못 보는 사람이 그 지원자의 평가를 보면 A3 가 우회된다
    assert_can_view_application(db, user, application_id)

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
    user: User = Depends(get_current_user),
):
    """평가 수정 (E5 - 본인만 가능)."""
    evaluation = db.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "평가를 찾을 수 없습니다")

    # 남의 평가는 admin 도 고치지 않는다 — 평가는 작성자의 판단 기록이다 (E5)
    if evaluation.evaluator_id != user.id:
        raise HTTPException(HTTPStatus.FORBIDDEN, "본인이 쓴 평가만 수정할 수 있습니다")

    # 보낸 필드만 반영한다 (E5 부분 수정). 통째로 대입하면 comment 를 안 보낸
    # 요청이 기존 코멘트를 지운다 — 그건 PATCH 가 아니라 PUT 이다.
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(evaluation, field, value)

    db.commit()
    db.refresh(evaluation)

    return evaluation
