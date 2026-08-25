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
    EmailLog,
    InterviewerAssignment,
    StageHistory,
    User,
)
from app.stages import NOTIFY_STAGES, StageTransitionError, validate_transition

WRITE_TOOL_NAMES = frozenset({"change_stage", "assign_interviewer", "draft_email"})


def change_stage(db: Session, user: User, params: dict) -> dict:
    """단계 변경 + 이력 기록 + 메일 큐 발행."""
    if user.role not in ("admin", "recruiter"):
        return {"error": "단계 변경 권한이 없습니다"}

    application_id = int(params["application_id"])
    to_stage = params["to_stage"]

    app = db.get(Application, application_id)
    if app is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}

    from_stage = app.current_stage
    try:
        validate_transition(from_stage, to_stage)
    except StageTransitionError as e:
        return {"error": str(e)}

    now = datetime.now(UTC)
    app.current_stage = to_stage
    app.updated_at = now

    db.add(
        StageHistory(
            application_id=application_id,
            from_stage=from_stage,
            to_stage=to_stage,
            changed_by=user.id,
            created_at=now,
        )
    )

    mail_queued = to_stage in NOTIFY_STAGES
    if mail_queued:
        db.add(
            EmailLog(
                application_id=application_id,
                to_email=app.email,
                stage=to_stage,
                status="queued",
                created_at=now,
            )
        )

    db.commit()

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

    users = db.scalars(select(User).where(User.id.in_(interviewer_ids))).all()
    if len(users) != len(set(interviewer_ids)):
        return {"error": "존재하지 않는 사용자가 있습니다"}

    bad = [u.id for u in users if u.role != "interviewer"]
    if bad:
        return {"error": f"면접관이 아닌 사용자입니다: {bad}"}

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
            f"가능한 일정을 알려주시면 조율하겠습니다.\n\n"
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
