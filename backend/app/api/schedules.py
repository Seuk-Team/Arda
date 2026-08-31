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

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import mail
from app.db import get_db
from app.deps import require_roles
from app.models import (
    Application,
    InterviewerAssignment,
    InterviewerAvailability,
    ScheduleProposal,
    ScheduleSlot,
    User,
)
from app.schemas.schedule import ProposalCreate, ProposalOut, SlotOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["schedules"])

require_recruiter = require_roles("admin", "recruiter")

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
    user: User = Depends(require_recruiter),
):
    """일정 제안 생성. recruiter+.

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
