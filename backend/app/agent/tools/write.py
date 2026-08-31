"""쓰기 도구 구현 (M4). 반드시 사용자 확인을 거친 뒤에만 실행한다.

runtime 이 write 도구 호출을 감지하면 실행하지 않고 pending_action 으로 돌려보낸다.
프론트가 확인 카드를 띄우고, 사용자가 승인하면 /confirm 엔드포인트가 여기를 호출한다.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException, status as http
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import (
    Application,
    InterviewerAssignment,
    InterviewerAvailability,
    ScheduleProposal,
    ScheduleSlot,
    User,
)
from app.stage_service import apply_stage_change, publish_all, require_reason
from app.stages import StageTransitionError

WRITE_TOOL_NAMES = frozenset({
    "change_stage", "assign_interviewer", "draft_email", "create_schedule_proposal",
})


def change_stage(db: Session, user: User, params: dict) -> dict:
    """단계 변경 + 이력 기록 + 메일 큐 발행.

    **부수효과는 REST 와 같은 함수를 쓴다** (`app/stage_service.py`, #148). 전에는
    여기서 `email_logs` 행을 직접 만들고 SQS 발행을 하지 않아, 에이전트로 단계를
    바꾸면 메일이 영영 나가지 않는데 응답은 `mail_queued: true` 였다. 불합격
    사유(D8)도 남지 않았다. 규칙만 공유하고 순서를 따로 쓰면 이렇게 갈린다.
    """
    application_id = int(params["application_id"])
    to_stage = params["to_stage"]
    reason = params.get("reason")

    app = db.get(Application, application_id)
    if app is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}

    # D8 — 불합격은 사유가 필수다. REST 와 같은 규칙을 쓴다.
    # 도구는 예외 대신 error 를 돌려준다(에이전트가 사용자에게 되물어야 한다).
    try:
        require_reason(to_stage, reason)
    except HTTPException as e:
        return {"error": e.detail}

    from_stage = app.current_stage
    now = datetime.now(UTC)
    try:
        log_id = apply_stage_change(db, app, to_stage, user.id, reason, now)
    except StageTransitionError as e:
        return {"error": str(e)}

    db.commit()

    # 커밋 뒤 발행 — 롤백된 건의 메시지가 큐에 남지 않게.
    mail_queued = bool(log_id) and publish_all([log_id]) == 1

    return {
        "ok": True,
        "application_id": application_id,
        "from_stage": from_stage,
        "to_stage": to_stage,
        "mail_queued": mail_queued,
    }


def assign_interviewer(db: Session, user: User, params: dict) -> dict:
    """면접관 배정. ADR-0013: 어드민만 가능."""
    if user.role != "admin":
        return {"error": "면접관 배정은 어드민만 가능합니다 (ADR-0013)"}

    application_id = int(params["application_id"])
    interviewer_ids = params["interviewer_ids"]
    if isinstance(interviewer_ids, int):
        interviewer_ids = [interviewer_ids]

    if db.get(Application, application_id) is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}

    # 역할 검사는 없다 — 누구나 면접관으로 배정될 수 있다 (ADR-0017).
    users = db.scalars(select(User).where(User.id.in_(interviewer_ids))).all()
    if len(users) != len(set(interviewer_ids)):
        return {"error": "존재하지 않는 사용자가 있습니다"}

    db.execute(
        pg_insert(InterviewerAssignment)
        .values([
            {
                "application_id": application_id,
                "interviewer_id": u.id,
                "assigned_by": user.id,
            }
            for u in users
        ])
        .on_conflict_do_nothing(index_elements=["application_id", "interviewer_id"])
    )
    db.commit()

    return {
        "ok": True,
        "application_id": application_id,
        "assigned": [u.id for u in users],
    }


def create_schedule_proposal(db: Session, user: User, params: dict) -> dict:
    """면접 일정 제안 생성. 배정된 면접관의 가용 시간에서 후보 슬롯을 뽑는다."""
    import logging
    import secrets

    from app import mail
    from app.api.schedules import _build_candidates

    logger = logging.getLogger(__name__)

    application_id = int(params["application_id"])
    slot_minutes = int(params.get("slot_minutes", 60))
    max_slots = int(params.get("max_slots", 5))

    app = db.get(Application, application_id)
    if app is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}

    interviewer_ids = list(
        db.scalars(
            select(InterviewerAssignment.interviewer_id).where(
                InterviewerAssignment.application_id == application_id
            )
        )
    )
    if not interviewer_ids:
        return {"error": "배정된 면접관이 없습니다 — 먼저 면접관을 배정하세요"}

    now = datetime.now(UTC)

    windows = list(
        db.scalars(
            select(InterviewerAvailability)
            .where(InterviewerAvailability.interviewer_id.in_(interviewer_ids))
            .where(InterviewerAvailability.end_at > now)
        )
    )

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

    candidates = _build_candidates(windows, confirmed, slot_minutes, max_slots, now)
    if not candidates:
        return {"error": "생성 가능한 후보 슬롯이 없습니다 — 면접관 가용 시간을 확인하세요"}

    from sqlalchemy import update
    db.execute(
        update(ScheduleProposal)
        .where(ScheduleProposal.application_id == application_id)
        .where(ScheduleProposal.status == "proposed")
        .values(status="canceled", updated_at=now)
    )

    proposal = ScheduleProposal(
        application_id=application_id,
        token=secrets.token_urlsafe(16),
        status="proposed",
        created_by=user.id,
    )
    db.add(proposal)
    db.flush()

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

    log = mail.create_log(
        db,
        application_id=application_id,
        to_email=app.email,
        stage="interview",
    )
    db.commit()

    mail_queued = True
    try:
        mail.publish(log.id)
    except Exception:
        mail_queued = False
        logger.exception("제안 메일 큐 발행 실패 email_log_id=%s", log.id)

    names = dict(
        db.execute(
            select(User.id, User.name).where(User.id.in_(interviewer_ids))
        ).all()
    )

    return {
        "ok": True,
        "application_id": application_id,
        "proposal_id": proposal.id,
        "status": "proposed",
        "slots": [
            {
                "interviewer_name": names.get(s.interviewer_id),
                "start_at": s.start_at.isoformat(),
                "end_at": s.end_at.isoformat(),
            }
            for s in slots
        ],
        "mail_queued": mail_queued,
    }


def draft_email(db: Session, user: User, params: dict) -> dict:
    """이메일 초안 생성. DB에 쓰지 않고 초안 텍스트만 반환한다."""
    application_id = int(params["application_id"])
    purpose = params.get("purpose", "general")

    app = db.get(Application, application_id)
    if app is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}

    templates = {
        "interview": (
            f"{app.name}님 안녕하세요.\n\n"
            f"서류 검토 결과, 면접에 초대드리고자 합니다.\n"
            f"면접 일정 선택 링크를 별도로 보내드릴 예정이니 확인 부탁드립니다.\n\n"
            f"감사합니다."
        ),
        "accepted": (
            f"{app.name}님 안녕하세요.\n\n"
            f"축하드립니다. 최종 합격을 알려드립니다.\n"
            f"입사 관련 안내를 별도로 보내드리겠습니다.\n\n"
            f"감사합니다."
        ),
        "rejected": (
            f"{app.name}님 안녕하세요.\n\n"
            f"검토 결과를 안내드립니다. 아쉽게도 이번에는 함께하기 어렵게 되었습니다.\n"
            f"지원해주셔서 감사드리며, 앞으로의 활동을 응원합니다.\n\n"
            f"감사합니다."
        ),
        "general": (
            f"{app.name}님 안녕하세요.\n\n"
            f"[여기에 내용을 작성하세요]\n\n"
            f"감사합니다."
        ),
    }

    body = templates.get(purpose, templates["general"])

    return {
        "ok": True,
        "to": app.email,
        "subject": _subject(purpose, app.name),
        "body": body,
    }


def _subject(purpose: str, name: str) -> str:
    subjects = {
        "interview": f"[Arda] {name}님, 면접 안내드립니다",
        "accepted": f"[Arda] {name}님, 최종 합격을 축하드립니다",
        "rejected": f"[Arda] {name}님, 지원 결과 안내",
        "general": f"[Arda] {name}님께 안내드립니다",
    }
    return subjects.get(purpose, subjects["general"])
