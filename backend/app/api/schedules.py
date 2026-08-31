"""면접 일정 제안 API — 일정 자동화(ADR-0016)의 2단계.

배정된 면접관(E3)의 가용 시간에서 후보 슬롯을 뽑아 지원자에게 제안한다.
제안 생성은 사람(담당자)의 명시적 액션이다 — 시스템은 교집합 계산과
메일 왕복 제거만 한다. 지원자 쪽 조회·확정은 공개 라우트가 맡는다(3단계).
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import mail
from app.db import get_db
from app.deps import get_current_user
from app.models import (
    Application,
    InterviewerAssignment,
    InterviewerAvailability,
    JobPosting,
    ScheduleProposal,
    ScheduleSlot,
    User,
)
from app.schemas.schedule import (
    ConfirmRequest,
    InterviewListOut,
    InterviewOut,
    ProposalCreate,
    ProposalOut,
    ProposalStatusOut,
    PublicSlotOut,
    SchedulePublicOut,
    SlotOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["schedules"])

PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "").rstrip("/")


def _build_candidates(
    windows: list[InterviewerAvailability],
    confirmed: dict[int, list[tuple[datetime, datetime]]],
    slot_minutes: int,
    max_slots: int,
    now: datetime,
) -> list[tuple[int, datetime, datetime]]:
    """가용 시간 창을 슬롯 길이로 잘라 후보를 만든다.

    - 과거분·이미 확정된 면접과 겹치는 슬롯은 제외한다 (확정 시점에 한 번 더
      검증하지만, 어차피 안 될 선택지를 지원자에게 보여주는 것부터가 잘못이다).
    - 창 하나가 아무리 길어도 max_slots 개까지만 자른다 — 몇 달짜리 창을
      통째로 조각내는 낭비를 막는 상한이다. 전체는 마지막에 다시 자른다.
    """
    step = timedelta(minutes=slot_minutes)
    seen: set[tuple[int, datetime]] = set()
    candidates: list[tuple[int, datetime, datetime]] = []

    for w in sorted(windows, key=lambda w: w.start_at):
        made = 0
        start = w.start_at
        while start + step <= w.end_at and made < max_slots:
            end = start + step
            key = (w.interviewer_id, start)
            overlap = any(
                start < c_end and end > c_start
                for c_start, c_end in confirmed.get(w.interviewer_id, ())
            )
            if start > now and key not in seen and not overlap:
                seen.add(key)
                candidates.append((w.interviewer_id, start, end))
                made += 1
            start = end

    candidates.sort(key=lambda c: (c[1], c[0]))
    return candidates[:max_slots]


@router.post(
    "/applications/{application_id}/schedule-proposals",
    response_model=ProposalOut,
    status_code=HTTPStatus.CREATED,
)
def create_proposal(
    application_id: int,
    body: ProposalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """일정 제안 생성. 로그인한 사람이면 누구나 (ADR-0017).

    흐름: 배정 면접관의 가용 시간 → 후보 슬롯 → 제안 저장 → 제안 메일 큐 발행.
    재제안하면 기존 proposed 제안은 canceled 로 남는다(이력 보존, 라이브 제안은
    항상 최대 1건). 메일은 커밋 뒤에 발행한다 (mail.create_log 주석 참고).
    """
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 배정된 면접관(E3)이 재료다 — 없으면 슬롯을 만들 수 없다
    interviewer_ids = list(
        db.scalars(
            select(InterviewerAssignment.interviewer_id).where(
                InterviewerAssignment.application_id == application_id
            )
        )
    )
    if not interviewer_ids:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "배정된 면접관이 없습니다 — 먼저 면접관을 배정하세요 (E3)",
        )

    now = datetime.now(timezone.utc)

    # 아직 끝나지 않은 가용 시간 창
    windows = list(
        db.scalars(
            select(InterviewerAvailability)
            .where(InterviewerAvailability.interviewer_id.in_(interviewer_ids))
            .where(InterviewerAvailability.end_at > now)
        )
    )

    # 이미 확정된 면접(같은 면접관의 다른 지원자 포함)과 겹치면 후보에서 뺀다
    confirmed: dict[int, list[tuple[datetime, datetime]]] = {}
    rows = db.execute(
        select(ScheduleSlot.interviewer_id, ScheduleSlot.start_at, ScheduleSlot.end_at)
        .join(ScheduleProposal, ScheduleProposal.confirmed_slot_id == ScheduleSlot.id)
        .where(ScheduleProposal.status == "confirmed")
        .where(ScheduleSlot.interviewer_id.in_(interviewer_ids))
        .where(ScheduleSlot.end_at > now)
    ).all()
    for iid, s, e in rows:
        confirmed.setdefault(iid, []).append((s, e))

    candidates = _build_candidates(
        windows, confirmed, body.slot_minutes, body.max_slots, now
    )
    if not candidates:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "생성 가능한 후보 슬롯이 없습니다 — 면접관 가용 시간을 확인하세요",
        )

    # 재제안: 라이브 제안은 항상 최대 1건. 이전 것은 canceled 로 이력만 남긴다
    db.execute(
        update(ScheduleProposal)
        .where(ScheduleProposal.application_id == application_id)
        .where(ScheduleProposal.status == "proposed")
        .values(status="canceled", updated_at=now)
    )

    proposal = ScheduleProposal(
        application_id=application_id,
        # public_token(B6)과 같은 근거 — 128비트라 추측으로 맞힐 수 없다
        token=secrets.token_urlsafe(16),
        status="proposed",
        expires_at=body.expires_at,
        created_by=user.id,
    )
    db.add(proposal)
    db.flush()  # 슬롯이 proposal.id 를 참조한다

    slots = [
        ScheduleSlot(
            proposal_id=proposal.id,
            interviewer_id=interviewer_id,
            start_at=start,
            end_at=end,
        )
        for interviewer_id, start, end in candidates
    ]
    db.add_all(slots)

    # 제안 메일 — 워커가 stage=interview 렌더 때 라이브 제안을 보고 링크를 싣는다
    log = mail.create_log(
        db,
        application_id=application_id,
        to_email=application.email,
        stage="interview",
    )
    db.commit()

    # 커밋 뒤 발행 — 큐가 죽어도 제안은 이미 성공이다. 행은 queued 로 남는다
    mail_queued = True
    try:
        mail.publish(log.id)
    except Exception:
        mail_queued = False
        logger.exception("제안 메일 큐 발행 실패 email_log_id=%s", log.id)

    # 담당자 화면 표시용 면접관 이름
    names = dict(
        db.execute(
            select(User.id, User.name).where(User.id.in_(interviewer_ids))
        ).all()
    )
    return ProposalOut(
        id=proposal.id,
        application_id=application_id,
        token=proposal.token,
        status=proposal.status,
        expires_at=proposal.expires_at,
        url=f"{PUBLIC_APP_BASE_URL}/schedule/{proposal.token}",
        slots=[
            SlotOut.model_validate(s).model_copy(
                update={"interviewer_name": names.get(s.interviewer_id)}
            )
            for s in slots
        ],
        mail_queued=mail_queued,
        created_at=proposal.created_at,
    )



@router.get(
    "/applications/{application_id}/schedule-proposals",
    response_model=ProposalStatusOut,
)
def get_latest_proposal(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이 지원자의 최신 일정 제안 상태. 대시보드·상세 패널의 칩 용도.

    조회는 로그인한 사람 전체에게 열려 있다 (ADR-0017).
    제안이 하나도 없으면 404 — 화면은 "일정 없음"으로 그린다.
    """
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    proposal = db.scalar(
        select(ScheduleProposal)
        .where(ScheduleProposal.application_id == application_id)
        .order_by(ScheduleProposal.created_at.desc())
        .limit(1)
    )
    if proposal is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "일정 제안이 없습니다")

    # 조회 시점 만료 판정 — 공개 라우트와 같은 규칙 (스케줄러 없음)
    now = datetime.now(timezone.utc)
    if (
        proposal.status == "proposed"
        and proposal.expires_at is not None
        and proposal.expires_at <= now
    ):
        proposal.status = "expired"
        proposal.updated_at = now
        db.commit()

    confirmed_slot = None
    if proposal.status == "confirmed" and proposal.confirmed_slot_id is not None:
        confirmed_slot = db.get(ScheduleSlot, proposal.confirmed_slot_id)

    return ProposalStatusOut(
        status=proposal.status,
        confirmed_slot=(
            PublicSlotOut.model_validate(confirmed_slot) if confirmed_slot else None
        ),
        expires_at=proposal.expires_at,
        created_at=proposal.created_at,
    )


@router.get("/schedules", response_model=InterviewListOut)
def list_confirmed_interviews(
    from_at: datetime | None = Query(None, alias="from", description="이 시각 이후 시작분만"),
    to_at: datetime | None = Query(None, alias="to", description="이 시각 이전 시작분만"),
    mine: bool = Query(False, description="내가 면접관인 건만"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """확정된 면접 목록 (ADR-0016). 면접 일정 화면의 데이터 소스.

    역할 분기가 없다 — 로그인한 사람은 전체를 보고, mine=true 로 자기가
    면접관인 건만 좁힌다 (ADR-0017). 좁히는 것은 이제 필터이지 권한이 아니다.
    """
    query = (
        select(ScheduleSlot, Application, JobPosting, User)
        .join(ScheduleProposal, ScheduleProposal.confirmed_slot_id == ScheduleSlot.id)
        .join(Application, Application.id == ScheduleProposal.application_id)
        .join(JobPosting, JobPosting.id == Application.job_posting_id)
        .join(User, User.id == ScheduleSlot.interviewer_id)
        .where(ScheduleProposal.status == "confirmed")
        .order_by(ScheduleSlot.start_at)
    )
    if from_at is not None:
        query = query.where(ScheduleSlot.start_at >= from_at)
    if to_at is not None:
        query = query.where(ScheduleSlot.start_at < to_at)
    if mine:
        query = query.where(ScheduleSlot.interviewer_id == user.id)

    rows = db.execute(query).all()
    items = [
        InterviewOut(
            proposal_id=slot.proposal_id,
            application_id=application.id,
            applicant_name=application.name,
            posting_title=posting.title,
            interviewer_id=interviewer.id,
            interviewer_name=interviewer.name,
            start_at=slot.start_at,
            end_at=slot.end_at,
        )
        for slot, application, posting, interviewer in rows
    ]
    return InterviewListOut(items=items, count=len(items))

# ── 공개 라우트 — 지원자용 (토큰 접근, 로그인 없음) ──────────────────
#
# 공고 쪽 공개 경로는 api/public.py 에 있지만, 일정 로직은 이 파일에 모은다 —
# 제안 생성과 확정이 같은 규칙(겹침 검증·상태 전이)을 공유하기 때문이다.


def _get_proposal_by_token(db: Session, token: str) -> ScheduleProposal:
    """토큰으로 제안을 찾고 조회 시점 판정을 한다 (B4 마감과 같은 방식).

    - 없는 토큰 → 404
    - canceled(재제안으로 대체된 옛 링크) → 410 Gone. 새 링크가 메일로 나갔다 —
      "있었지만 끝났다"를 알려야 지원자가 옛 메일을 붙잡고 헤매지 않는다.
    - proposed 인데 기한이 지남 → expired 로 바꿔 저장 (스케줄러 없음)
    """
    proposal = db.scalar(
        select(ScheduleProposal).where(ScheduleProposal.token == token)
    )
    if proposal is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "유효하지 않은 링크입니다")
    if proposal.status == "canceled":
        raise HTTPException(
            HTTPStatus.GONE, "이 일정 제안은 더 이상 유효하지 않습니다 — 최신 안내 메일을 확인해 주세요"
        )

    now = datetime.now(timezone.utc)
    if (
        proposal.status == "proposed"
        and proposal.expires_at is not None
        and proposal.expires_at <= now
    ):
        proposal.status = "expired"
        proposal.updated_at = now
        db.commit()

    return proposal


@router.get("/public/schedule/{token}", response_model=SchedulePublicOut)
def get_schedule_public(token: str, db: Session = Depends(get_db)):
    """지원자용 일정·전형 현황 조회. 공개 — 토큰이 곧 인증이다.

    expired 도 200 으로 내려준다 — 지원자가 "기한이 지났다"와 자기 전형 현황을
    봐야 하기 때문이다(빈 화면보다 낫다). confirmed 는 확정 시각 재확인 용도로
    링크가 계속 살아 있다 — "24시간 언제든 확인"이 이 기능의 요지다.
    """
    proposal = _get_proposal_by_token(db, token)
    application = db.get(Application, proposal.application_id)
    posting = db.get(JobPosting, application.job_posting_id)

    confirmed_slot = None
    if proposal.status == "confirmed" and proposal.confirmed_slot_id is not None:
        confirmed_slot = db.get(ScheduleSlot, proposal.confirmed_slot_id)

    return SchedulePublicOut(
        status=proposal.status,
        applicant_name=application.name,
        posting_title=posting.title if posting else "",
        current_stage=application.current_stage,
        expires_at=proposal.expires_at,
        slots=[
            PublicSlotOut.model_validate(s)
            for s in sorted(proposal.slots, key=lambda s: s.start_at)
        ],
        confirmed_slot=(
            PublicSlotOut.model_validate(confirmed_slot) if confirmed_slot else None
        ),
    )


@router.post("/public/schedule/{token}/confirm", response_model=SchedulePublicOut)
def confirm_schedule(token: str, body: ConfirmRequest, db: Session = Depends(get_db)):
    """슬롯 선택 → 즉시 확정. 공개.

    지원자의 슬롯 선택은 지원자 본인의 결정이므로 담당자 승인 없이 즉시 확정이다
    (ADR-0016). 확정 통보 메일은 워커가 confirmed 상태를 보고 확정 시각을 싣는다.
    """
    proposal = _get_proposal_by_token(db, token)

    # 같은 제안에 확정이 두 번 붙는 것을 막는다 — 더블클릭·중복 탭이 정상 사용이다
    db.refresh(proposal, with_for_update=True)

    if proposal.status == "confirmed":
        raise HTTPException(HTTPStatus.CONFLICT, "이미 확정된 일정입니다")
    if proposal.status == "expired":
        raise HTTPException(
            HTTPStatus.CONFLICT, "선택 기한이 지났습니다 — 담당자에게 문의해 주세요"
        )

    slot = db.get(ScheduleSlot, body.slot_id)
    if slot is None or slot.proposal_id != proposal.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "슬롯을 찾을 수 없습니다")

    # 확정 시점 겹침 재검증 — 제안이 나간 뒤 같은 면접관의 다른 면접이 먼저
    # 확정됐을 수 있다 (슬롯은 생성 시점 스냅샷이다, models.py 참고)
    clash = db.scalar(
        select(ScheduleSlot.id)
        .join(ScheduleProposal, ScheduleProposal.confirmed_slot_id == ScheduleSlot.id)
        .where(ScheduleProposal.status == "confirmed")
        .where(ScheduleSlot.interviewer_id == slot.interviewer_id)
        .where(ScheduleSlot.start_at < slot.end_at)
        .where(ScheduleSlot.end_at > slot.start_at)
        .limit(1)
    )
    if clash is not None:
        raise HTTPException(
            HTTPStatus.CONFLICT,
            "그 사이 마감된 시간입니다 — 다른 시간을 선택해 주세요",
        )

    now = datetime.now(timezone.utc)
    proposal.status = "confirmed"
    proposal.confirmed_slot_id = slot.id
    proposal.updated_at = now

    application = db.get(Application, proposal.application_id)
    # 확정 통보 — 워커가 confirmed 를 보고 {면접일시}에 확정 시각(KST)을 싣는다
    log = mail.create_log(
        db,
        application_id=application.id,
        to_email=application.email,
        stage="interview",
    )
    db.commit()
    try:
        mail.publish(log.id)
    except Exception:
        # 확정은 이미 저장됐다 — 메일이 늦는 것이 확정을 무르는 것보다 낫다
        logger.exception("확정 통보 메일 큐 발행 실패 email_log_id=%s", log.id)

    posting = db.get(JobPosting, application.job_posting_id)
    return SchedulePublicOut(
        status="confirmed",
        applicant_name=application.name,
        posting_title=posting.title if posting else "",
        current_stage=application.current_stage,
        expires_at=proposal.expires_at,
        slots=[
            PublicSlotOut.model_validate(s)
            for s in sorted(proposal.slots, key=lambda s: s.start_at)
        ],
        confirmed_slot=PublicSlotOut.model_validate(slot),
    )
