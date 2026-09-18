"""데모 지원자 로그인 시 상태 초기화 (심사위원 공유 계정).

`DEMO_APPLICANT_EMAILS` 에 든 지원자가 로그인하면 그 지원자의 **인적성·면접 일정·
AI 면접** 을 기준(fresh) 상태로 되돌린다. 앞 심사위원이 검사를 제출했거나 면접을
끝내 놨어도, 다음 심사위원이 세 화면을 처음부터 볼 수 있게 한다.

**기준 행 자체(담당자가 보낸 인적성·일정 제안·면접 세션)는 남기고 완료/응답만 지운다.**
그래서 세 화면이 "대기 중" 으로 보이려면 담당자가 그 지원자에게 한 번은 보내 둬야 한다
(그 발송 자체가 담당자 기능 시연이기도 하다).

실제 지원자는 이 경로에 오지 않는다 — 호출부(applicant_login)가 is_demo_applicant 로
건다. 리셋 대상은 이메일이 정확히 일치하는 지원서뿐이다.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Application,
    AptitudeAnswer,
    AptitudeSession,
    InterviewFinding,
    InterviewSession,
    InterviewTurn,
    ScheduleProposal,
    ScheduleSlot,
    User,
)

logger = logging.getLogger(__name__)


def reset_demo_applicant(db: Session, email: str) -> None:
    """이메일로 지원서를 찾아 세 도메인 상태를 fresh 로 되돌린다. 없으면 아무것도 안 함."""
    norm = email.strip().lower()
    app_ids = list(
        db.scalars(select(Application.id).where(Application.email == norm)).all()
    )
    if not app_ids:
        return

    # 만료도 미래로 밀어 준다 — 조회 시점 만료 판정(_not_expired)이 심사 기간에 걸쳐
    # 세 화면을 계속 보이게. status 만 되돌리면 만료된 pending 은 여전히 숨겨진다.
    far = datetime.now(timezone.utc) + timedelta(days=45)

    # ── 인적성: 응답 삭제 + pending 으로 (재응시 가능) ──
    apt_ids = list(
        db.scalars(
            select(AptitudeSession.id).where(AptitudeSession.application_id.in_(app_ids))
        ).all()
    )
    if apt_ids:
        db.execute(delete(AptitudeAnswer).where(AptitudeAnswer.session_id.in_(apt_ids)))
        for s in db.scalars(
            select(AptitudeSession).where(AptitudeSession.id.in_(apt_ids))
        ).all():
            s.status = "pending"
            s.submitted_at = None
            s.ai_summary = None
            s.ai_summary_model = None
            s.expires_at = far

    # ── 면접 일정: proposed 로, 확정 취소 (다시 고를 수 있게) ──
    for p in db.scalars(
        select(ScheduleProposal).where(ScheduleProposal.application_id.in_(app_ids))
    ).all():
        p.status = "proposed"
        p.confirmed_slot_id = None
        p.expires_at = far

    # ── AI 면접: turns·findings 삭제 + pending 으로 (다시 시작 가능) ──
    iv_ids = list(
        db.scalars(
            select(InterviewSession.id).where(
                InterviewSession.application_id.in_(app_ids)
            )
        ).all()
    )
    if iv_ids:
        db.execute(delete(InterviewTurn).where(InterviewTurn.session_id.in_(iv_ids)))
        db.execute(delete(InterviewFinding).where(InterviewFinding.session_id.in_(iv_ids)))
        for s in db.scalars(
            select(InterviewSession).where(InterviewSession.id.in_(iv_ids))
        ).all():
            s.status = "pending"
            s.consented_at = None
            s.started_at = None
            s.ended_at = None
            s.ai_score = None
            s.ai_score_detail = None
            s.truth_samples = None
            s.scored_at = None
            s.expires_at = far

    # ── 기준 데이터가 없으면 만들어 준다 (self-healing) — 원격 시드 없이 세 화면이 뜨게.
    #    대표 지원서 하나에만 붙이고, 담당자·면접관 id 는 첫 admin 을 쓴다(데모 편의). ──
    app_id = app_ids[0]
    admin_id = db.scalar(select(User.id).where(User.role == "admin").order_by(User.id).limit(1))
    if admin_id:
        if not apt_ids:
            db.add(AptitudeSession(
                application_id=app_id, token=secrets.token_hex(32),
                status="pending", expires_at=far, created_by=admin_id,
            ))
        if not iv_ids:
            db.add(InterviewSession(
                application_id=app_id, token=secrets.token_hex(32),
                status="pending", expires_at=far, created_by=admin_id,
            ))
        has_sched = db.scalar(
            select(ScheduleProposal.id).where(
                ScheduleProposal.application_id.in_(app_ids)
            ).limit(1)
        )
        if not has_sched:
            p = ScheduleProposal(
                application_id=app_id, token=secrets.token_hex(32),
                status="proposed", expires_at=far, created_by=admin_id,
            )
            db.add(p)
            db.flush()
            base = (datetime.now(timezone.utc) + timedelta(days=2)).replace(
                hour=1, minute=0, second=0, microsecond=0
            )  # ~10:00 KST
            for d in range(3):
                st = base + timedelta(days=d)
                db.add(ScheduleSlot(
                    proposal_id=p.id, interviewer_id=admin_id,
                    start_at=st, end_at=st + timedelta(hours=1),
                ))

    db.commit()
    logger.info(
        "demo_applicant_reset",
        extra={"email_domain": norm.rpartition("@")[2], "apps": len(app_ids)},
    )
