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

from app.interview.session_service import add_default_questions, seed_questions_bg
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

    app_id = app_ids[0]
    admin_id = db.scalar(select(User.id).where(User.role == "admin").order_by(User.id).limit(1))

    # ── 인적성/일정: 없으면 생성 (self-healing) — 원격 시드 없이 화면이 뜨게 ──
    if admin_id and not apt_ids:
        db.add(AptitudeSession(
            application_id=app_id, token=secrets.token_hex(32),
            status="pending", expires_at=far, created_by=admin_id,
        ))
    has_sched = db.scalar(
        select(ScheduleProposal.id).where(
            ScheduleProposal.application_id.in_(app_ids)
        ).limit(1)
    )
    if admin_id and not has_sched:
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

    # ── AI 면접: 세션을 하나만 남긴다 (심사위원마다 새로 볼 하나). **질문 turn 은 보존**
    #    하고 답변만 비운다 — 파이프라인이 뽑아 둔 질문이 로그인마다 사라지지 않게.
    #    질문이 없으면 폴백을 넣고, 커밋 뒤 seed_questions_bg 로 자소서 기반 커스텀으로
    #    올린다(폴백 그대로일 때만 바꾸므로 이후 로그인엔 재생성 없음 = API 1회). ──
    iv_sessions = list(db.scalars(
        select(InterviewSession)
        .where(InterviewSession.application_id.in_(app_ids))
        .order_by(InterviewSession.id)
    ).all())
    keep_iv = iv_sessions[0] if iv_sessions else None
    extra_iv = [s.id for s in iv_sessions[1:]]
    if extra_iv:
        db.execute(delete(InterviewTurn).where(InterviewTurn.session_id.in_(extra_iv)))
        db.execute(delete(InterviewFinding).where(InterviewFinding.session_id.in_(extra_iv)))
        db.execute(delete(InterviewSession).where(InterviewSession.id.in_(extra_iv)))

    if keep_iv is None and admin_id:
        keep_iv = InterviewSession(
            application_id=app_id, token=secrets.token_hex(32),
            status="pending", expires_at=far, created_by=admin_id,
        )
        db.add(keep_iv)
        db.flush()

    keep_iv_id = None
    if keep_iv is not None:
        keep_iv.status = "pending"
        keep_iv.consented_at = None
        keep_iv.started_at = None
        keep_iv.ended_at = None
        keep_iv.ai_score = None
        keep_iv.ai_score_detail = None
        keep_iv.truth_samples = None
        keep_iv.scored_at = None
        keep_iv.expires_at = far
        db.execute(delete(InterviewFinding).where(InterviewFinding.session_id == keep_iv.id))
        turns = list(db.scalars(
            select(InterviewTurn).where(InterviewTurn.session_id == keep_iv.id)
        ).all())
        for t in turns:  # 답변만 비우고 질문은 남긴다
            t.audio_s3_key = None
            t.transcript = None
            t.answered_at = None
            t.audio_duration_sec = None
            t.stt_cost_usd = None
        if not turns:
            add_default_questions(db, keep_iv.id)
        keep_iv_id = keep_iv.id

    db.commit()

    # 폴백 → 자소서 기반 커스텀 질문 업그레이드 (idempotent · 폴백 그대로일 때만).
    if keep_iv_id is not None:
        try:
            seed_questions_bg(keep_iv_id)
        except Exception:  # noqa: BLE001
            logger.exception("demo 면접 질문 생성 실패: session=%s", keep_iv_id)

    logger.info(
        "demo_applicant_reset",
        extra={"email_domain": norm.rpartition("@")[2], "apps": len(app_ids)},
    )
