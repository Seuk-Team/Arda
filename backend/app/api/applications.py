import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status as http
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import mail
from app.agent.summarizer import generate_summary_bg
from app.db import get_db
from app.deps import (
    assert_can_view_application,
    get_current_user,
    require_roles,
    scope_to_viewer,
)
from app.models import Application, JobPosting, StageHistory, User
from app.schemas.application_detail import (
    ApplicationDetail,
    ApplicationListItem,
    ManualApplicationCreate,
    StageHistoryOut,
)
from app.schemas.stage import StageChangeOut, StageChangeRequest
from app.stages import NOTIFY_STAGES, StageTransitionError, validate_transition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["applications"])

# 단계 변경은 담당자 권한 (01-erd.md)
require_recruiter = require_roles("admin", "recruiter")


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


@router.patch("/applications/{application_id}/stage", response_model=StageChangeOut)
def change_stage(
    application_id: int,
    body: StageChangeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_recruiter),
):
    """단계 변경 (D3) + 이력 기록 (D5) + 통지 메일 큐 발행 (G1).

    셋을 한 트랜잭션에 묶는다. 단계만 바뀌고 이력이 빠지면 "언제 누가 바꿨는지"를
    복구할 방법이 없고, 이력만 남고 단계가 안 바뀌면 화면과 어긋난다.

    권한: 01-erd.md 가 뒤로 이동을 "담당자 권한"으로 규정하고, A3 는 면접관을
    조회로 한정한다. 그래서 recruiter+ 로 둔다. 다만 02-api.md 에 이 역할이
    적혀 있지 않다 — #59 와 같은 종류의 공백이라 PR 에 적어 둔다.
    """
    application = _get_or_404(db, application_id)
    from_stage = application.current_stage

    try:
        validate_transition(from_stage, body.to_stage)
    except StageTransitionError as e:
        raise HTTPException(http.HTTP_409_CONFLICT, str(e))

    now = datetime.now(UTC)
    application.current_stage = body.to_stage
    application.updated_at = now

    db.add(
        StageHistory(
            application_id=application_id,
            from_stage=from_stage,
            to_stage=body.to_stage,
            changed_by=user.id,
            created_at=now,
        )
    )

    # 메일은 여기서 보내지 않는다 — 큐에 올리기만 하고 워커가 발송한다 (G2·G3, 큐 13번).
    # 발송이 이 요청 안에서 일어나면 SES 가 느릴 때 단계 변경까지 같이 느려지고,
    # 발송 실패가 단계 변경을 롤백시킨다.
    mail_queued = False
    if body.to_stage in NOTIFY_STAGES:
        try:
            mail.enqueue(
                db,
                application_id=application_id,
                to_email=application.email,
                stage=body.to_stage,
            )
            mail_queued = True
        except Exception:
            # 큐가 죽어도 단계 변경은 성공해야 한다 — 담당자가 카드를 못 옮기는 것이
            # 메일이 늦는 것보다 나쁘다. 행은 queued 로 남으니 나중에 셀 수 있다.
            logger.exception("메일 큐 발행 실패 application_id=%s", application_id)

    db.commit()

    return StageChangeOut(
        application_id=application_id,
        from_stage=from_stage,
        to_stage=body.to_stage,
        changed_by=user.id,
        changed_at=now,
        mail_queued=mail_queued,
    )


@router.post(
    "/postings/{posting_id}/applications",
    response_model=ApplicationDetail,
    status_code=http.HTTP_201_CREATED,
)
def create_manual_application(
    posting_id: int,
    body: ManualApplicationCreate,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    # 02-api.md 는 D6 을 recruiter+ 로 명시한다. 지시서는 인증이 없던 시점 기준이라
    # "넣지 마라"고 하지만, #61(A3)로 인증이 들어와 이 파일에 이미 적용돼 있다.
    user: User = Depends(require_recruiter),
):
    """담당자가 지원자를 직접 등록한다 (D6).

    메일·전화로 이력서를 받은 경우를 위한 경로다. 외부 지원(C1)과 세 가지가 다르다.
    """
    if db.get(JobPosting, posting_id) is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "공고를 찾을 수 없습니다")
    # 외부 지원과 달리 공고 status 를 보지 않는다. 마감된 공고에도 담당자는 넣을 수 있다.

    dup = db.scalar(
        select(Application.id).where(
            Application.job_posting_id == posting_id,
            Application.email == body.email,
        )
    )
    if dup:
        # 409 만 주면 담당자가 기존 건을 찾아 헤맨다. id 를 함께 준다
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            f"이미 등록된 지원자입니다 (application_id={dup})",
        )

    row = Application(
        job_posting_id=posting_id,
        source="manual",
        current_stage="applied",
        **body.model_dump(),
    )
    db.add(row)
    db.flush()
    # 접수 이력 1행. changed_by 는 등록한 담당자다 (외부 지원은 None = 시스템)
    db.add(
        StageHistory(
            application_id=row.id,
            from_stage=None,
            to_stage="applied",
            changed_by=user.id,
        )
    )
    db.commit()

    # M2: AI 요약 생성 (비동기)
    bg.add_task(generate_summary_bg, row.id)

    return ApplicationDetail.model_validate(row)
