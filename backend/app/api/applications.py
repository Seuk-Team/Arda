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
from app.schemas.stage import (
    BulkStageOut,
    BulkStageRequest,
    StageChangeOut,
    StageChangeRequest,
)
from app.stages import NOTIFY_STAGES, REJECTED, StageTransitionError, validate_transition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["applications"])

# 단계 변경은 담당자 권한 (01-erd.md)
require_recruiter = require_roles("admin", "recruiter")

# 한 번에 바꿀 수 있는 최대 인원 (D9). 트랜잭션 하나가 붙드는 행 수의 상한이자,
# 실수로 전체를 떨어뜨리는 일을 막는 안전장치다.
BULK_LIMIT = 200


def _require_reason(to_stage: str, reason: str | None) -> None:
    """불합격은 이유를 남긴다 (D8).

    나중에 "이 사람 왜 불합격이었죠?"에 답할 수 있어야 한다. 다른 단계는 사유가
    없어도 다음 단계 이름이 곧 설명이지만, 불합격은 그렇지 않다.
    """
    if to_stage == REJECTED and not (reason and reason.strip()):
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY, "불합격은 사유를 입력해야 합니다"
        )


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


def _apply_stage_change(
    db: Session,
    application: Application,
    to_stage: str,
    changed_by: int,
    reason: str | None,
    now: datetime,
) -> int | None:
    """단계 하나를 바꾸고 이력·메일 행을 남긴다. **커밋하지 않는다.**

    단건 변경(D3)과 일괄 변경(D9)이 같은 함수를 쓴다 — 규칙이 두 곳에 있으면
    반드시 어긋난다. 규칙 자체는 `app/stages.py` 에만 있다.

    SQS 발행은 하지 않고 `email_logs.id` 만 돌려준다. 호출부가 **커밋한 뒤에**
    발행해야 롤백된 건의 메시지가 큐에 남지 않는다 (`mail.create_log` 주석 참고).
    메일이 필요 없는 단계면 None.
    """
    from_stage = application.current_stage
    validate_transition(from_stage, to_stage)  # 어긋나면 StageTransitionError

    application.current_stage = to_stage
    application.updated_at = now

    db.add(
        StageHistory(
            application_id=application.id,
            from_stage=from_stage,
            to_stage=to_stage,
            changed_by=changed_by,
            reason=reason,  # D8 — 불합격 사유. 다른 단계에서는 대개 None
            created_at=now,
        )
    )

    if to_stage not in NOTIFY_STAGES:
        return None

    # 메일은 여기서 보내지 않는다 — 큐에 올리기만 하고 워커가 발송한다 (G2·G3).
    # 발송이 이 요청 안에서 일어나면 SES 가 느릴 때 단계 변경까지 같이 느려지고,
    # 발송 실패가 단계 변경을 롤백시킨다.
    return mail.create_log(
        db,
        application_id=application.id,
        to_email=application.email,
        stage=to_stage,
    ).id


def _publish_all(email_log_ids: list[int]) -> int:
    """커밋이 끝난 뒤 큐에 싣는다. 발행한 건수를 돌려준다.

    큐가 죽어도 단계 변경은 이미 성공이다 — 담당자가 카드를 못 옮기는 것이 메일이
    늦는 것보다 나쁘다. 행은 `queued` 로 남으니 나중에 셀 수 있다.
    """
    published = 0
    for log_id in email_log_ids:
        try:
            mail.publish(log_id)
            published += 1
        except Exception:
            logger.exception("메일 큐 발행 실패 email_log_id=%s", log_id)
    return published


@router.patch("/applications/{application_id}/stage", response_model=StageChangeOut)
def change_stage(
    application_id: int,
    body: StageChangeRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_recruiter),
):
    """단계 변경 (D3) + 이력 기록 (D5) + 불합격 사유 (D8) + 통지 메일 큐 (G1).

    단계·이력·메일 행을 한 트랜잭션에 묶는다. 단계만 바뀌고 이력이 빠지면
    "언제 누가 바꿨는지"를 복구할 방법이 없고, 이력만 남고 단계가 안 바뀌면
    화면과 어긋난다.

    권한: 01-erd.md 가 뒤로 이동을 "담당자 권한"으로 규정하고, A3 는 면접관을
    조회로 한정한다. 그래서 recruiter+ 로 둔다.
    """
    _require_reason(body.to_stage, body.reason)

    application = _get_or_404(db, application_id)
    from_stage = application.current_stage
    now = datetime.now(UTC)

    try:
        log_id = _apply_stage_change(
            db, application, body.to_stage, user.id, body.reason, now
        )
    except StageTransitionError as e:
        raise HTTPException(http.HTTP_409_CONFLICT, str(e))

    db.commit()

    return StageChangeOut(
        application_id=application_id,
        from_stage=from_stage,
        to_stage=body.to_stage,
        changed_by=user.id,
        changed_at=now,
        mail_queued=bool(log_id) and _publish_all([log_id]) == 1,
    )


@router.post("/applications/bulk-stage", response_model=BulkStageOut)
def bulk_stage(
    body: BulkStageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_recruiter),
):
    """여러 명의 단계를 한 번에 바꾼다 (D9).

    서류에서 100명을 떨어뜨리는데 카드를 하나씩 끌면 100번을 끌어야 한다.

    **부분 성공을 허용하지 않는 이유**: 50명 중 30명만 바뀌고 끝나면 담당자는
    무엇이 됐고 무엇이 안 됐는지 알 수 없다. 화면을 새로 고쳐 하나씩 대조하는
    수밖에 없는데, 그럴 바에는 처음부터 다시 하는 편이 낫다. 한 건이라도 규칙에
    걸리면 전부 되돌리고 걸린 id 를 알려준다.

    **메일은 건별로 큐에 넣는다.** 일괄이라고 한 통으로 묶으면 지원자마다 다른
    이름·공고가 들어가야 하는 문구를 만들 수 없다.
    """
    if len(body.application_ids) > BULK_LIMIT:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"한 번에 {BULK_LIMIT}명까지 가능합니다 (요청 {len(body.application_ids)}명)",
        )
    _require_reason(body.to_stage, body.reason)

    rows = db.scalars(
        select(Application).where(Application.id.in_(body.application_ids))
    ).all()

    found = {row.id for row in rows}
    not_found = [i for i in body.application_ids if i not in found]

    now = datetime.now(UTC)
    changed, skipped, failed, log_ids = [], [], [], []

    for row in rows:
        if row.current_stage == body.to_stage:
            skipped.append(row.id)  # 이미 그 단계다. 실패가 아니다
            continue
        try:
            log_id = _apply_stage_change(
                db, row, body.to_stage, user.id, body.reason, now
            )
        except StageTransitionError:
            failed.append(row.id)
            continue
        changed.append(row.id)
        if log_id is not None:
            log_ids.append(log_id)

    if failed or not_found:
        db.rollback()
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            {
                "message": "허용되지 않는 전환이 있어 전부 되돌렸습니다",
                "failed": failed,
                "not_found": not_found,
            },
        )

    db.commit()

    # 커밋이 끝난 뒤에 발행한다 — 위에서 롤백했다면 메시지가 나가면 안 된다
    return BulkStageOut(
        changed=len(changed),
        changed_ids=changed,
        skipped=skipped,
        mail_queued=_publish_all(log_ids),
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
