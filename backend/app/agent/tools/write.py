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

from app import mail
from app.models import (
    Application,
    InterviewerAssignment,
    InterviewerAvailability,
    JobPosting,
    ScheduleProposal,
    ScheduleSlot,
    User,
)
from app.stage_service import apply_stage_change, publish_all, require_reason
from app.stages import StageTransitionError

# 확인 게이트를 타는 도구. **부수효과가 있는 것만 넣는다.**
# draft_email 은 초안 텍스트만 돌려주고 아무것도 바꾸지 않아서 뺐다 — 초안 하나
# 보려고 확인 카드를 지나야 하면 승인 한 번의 의미가 흐려진다. 실제로 되돌릴 수
# 없는 것은 send_email 이고, 그것이 게이트를 탄다 (G4 결정 3).
WRITE_TOOL_NAMES = frozenset({
    "change_stage", "assign_interviewer", "send_email", "create_schedule_proposal",
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
        # 도구를 승인한 사람이 발송 주체다 — 문구는 템플릿이라 아르가 쓴 것이
        # 아니다. 아르가 문안을 쓰는 것은 send_email 뿐이다 (G4).
        actor_kind="human",
        actor_id=user.id,
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


def _posting_title(db: Session, app: Application) -> str:
    posting = db.get(JobPosting, app.job_posting_id)
    return posting.title if posting else ""


# purpose 는 에이전트가 쓰는 말이고 stage 는 시스템의 말이다. 사이를 여기서 잇는다.
_PURPOSE_STAGE = {
    "interview": "interview",
    "accepted": "accepted",
    "rejected": "rejected",
}


def draft_email(db: Session, user: User, params: dict) -> dict:
    """이메일 초안 생성. **DB 에 쓰지 않고 초안 텍스트만 반환한다.**

    문구를 여기서 따로 짓지 않는다 — `mail` 의 템플릿을 그대로 쓴다. 예전에는
    이 함수가 자체 하드코딩 문구를 갖고 있었고, 그래서 **에이전트가 보여준 초안과
    시스템이 실제로 보내는 메일의 문구가 달랐다.** 담당자가 설정 화면에서 문구를
    고쳐도 아르만 옛 문구를 말하는 상태였다. 저장소를 하나로 합친다 (G4).

    서명은 아르 이름으로 들어간다 — 이 문안을 쓴 것이 아르이기 때문이다. 단
    합격·불합격은 `mail.build_signature` 가 사람 이름으로 되돌린다.
    """
    application_id = int(params["application_id"])
    purpose = params.get("purpose", "general")

    app = db.get(Application, application_id)
    if app is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}

    stage = _PURPOSE_STAGE.get(purpose)
    if stage is None:
        # general — 대응하는 템플릿이 없다. 채울 골격만 준다.
        signature = mail.build_signature("custom", "agent", user.name)
        return {
            "ok": True,
            "to": app.email,
            "subject": f"[{mail.COMPANY_NAME}] {app.name}님께 안내드립니다",
            "body": (
                f"{app.name} 님 안녕하세요.\n\n"
                "[여기에 내용을 작성하세요]\n\n"
                f"{signature}"
            ),
        }

    subject, body = mail.render(
        db,
        stage,
        app.name,
        _posting_title(db, app),
        actor_kind="agent",
        actor_name=user.name,
    )
    return {"ok": True, "to": app.email, "subject": subject, "body": body}


def send_email(db: Session, user: User, params: dict) -> dict:
    """메일 발송 (G4). **확인 게이트를 지난 뒤에만 실행된다.**

    안전장치가 겹으로 있다:

    - **수신자를 인자로 받지 않는다.** `application_id` 로 DB 의 주소만 쓴다 —
      아르가 임의 주소로 보낼 방법 자체가 없다.
    - 확인 카드에 수신자·제목·본문 전문이 뜬다. 사람이 그것을 읽고 승인한다.
    - 승인된 본문이 `email_logs` 에 그대로 남는다. 발송은 되돌릴 수 없으므로
      "무엇이 나갔는가"라도 남아야 한다.
    - 발송 자체는 하지 않는다 — 수동 발송 API 와 **같은 함수**로 큐에 올린다.
      순서를 따로 쓰면 #148 처럼 메일이 조용히 증발한다.
    """
    application_id = int(params["application_id"])
    subject = (params.get("subject") or "").strip()
    body = (params.get("body") or "").strip()

    app = db.get(Application, application_id)
    if app is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}
    if not subject or not body:
        return {"error": "제목과 본문이 모두 필요합니다"}

    values = {
        "지원자명": app.name,
        "공고명": _posting_title(db, app),
        "회사명": mail.COMPANY_NAME,
        "면접일시": mail.INTERVIEW_AT_UNKNOWN,
        "서명": mail.build_signature("custom", "agent", user.name),
    }

    log = mail.create_custom_log(
        db,
        application_id=app.id,
        to_email=app.email,
        subject=mail.fill(subject, values),
        body=mail.fill_body(body, values),
        actor_kind="agent",
        actor_id=user.id,  # 아르가 아니라 **승인한 사람**이다
    )
    db.commit()
    publish_all([log.id])  # 커밋 뒤 발행 — 실패해도 행은 queued 로 남는다

    return {
        "ok": True,
        "email_log_id": log.id,
        "to": log.to_email,
        "subject": log.subject,
    }
