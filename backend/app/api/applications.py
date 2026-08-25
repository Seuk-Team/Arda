from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.deps import (
    assert_can_view_application,
    get_current_user,
    scope_to_viewer,
)
from app.models import Application, JobPosting, StageHistory, User
from app.schemas.application_detail import (
    ApplicationDetail,
    ApplicationListItem,
    StageHistoryOut,
)

router = APIRouter(prefix="/api/v1", tags=["applications"])


def _get_or_404(db: Session, application_id: int) -> Application:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")
    return application


@router.get("/postings/{posting_id}/applications", response_model=list[ApplicationListItem])
def list_applications(
    posting_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """공고별 지원자 목록 (D1). 최신순. 자소서 전문은 담지 않는다.

    면접관에게는 본인 배정 건만 보인다 (A3).
    """
    if db.get(JobPosting, posting_id) is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "공고를 찾을 수 없습니다")

    stmt = scope_to_viewer(
        select(Application).where(Application.job_posting_id == posting_id), user
    )
    rows = db.scalars(stmt.order_by(Application.created_at.desc())).all()
    return [ApplicationListItem.model_validate(r) for r in rows]


@router.get("/applications/{application_id}", response_model=ApplicationDetail)
def get_application(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """지원자 상세 (D4). 패널이 한 번에 그릴 수 있도록 자식 4종을 함께 준다.

    selectinload 를 안 쓰면 관계마다 쿼리가 따로 나간다(N+1).
    상세 패널은 자주 열리므로 한 번에 읽는다.
    """
    assert_can_view_application(db, user, application_id)

    row = db.scalar(
        select(Application)
        .options(
            selectinload(Application.stage_history),
            selectinload(Application.evaluations),
            selectinload(Application.notes),
            selectinload(Application.files),
        )
        .where(Application.id == application_id)
    )
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")

    scores = [e.score for e in row.evaluations]
    return ApplicationDetail.model_validate(row).model_copy(
        update={"avg_score": round(sum(scores) / len(scores), 1) if scores else None}
    )


@router.get("/applications/{application_id}/history", response_model=list[StageHistoryOut])
def get_history(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """단계 이력만 (D5). 최신순."""
    _get_or_404(db, application_id)
    assert_can_view_application(db, user, application_id)

    rows = db.scalars(
        select(StageHistory)
        .where(StageHistory.application_id == application_id)
        .order_by(StageHistory.created_at.desc())
    ).all()
    return [StageHistoryOut.model_validate(r) for r in rows]
