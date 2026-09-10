"""자동 심사 (ADR-0034) — 합산 규칙은 DB 없이, 판정·배정은 트랜잭션 격리 DB 로.

메일은 큐에 행만 남기고 발행(SQS/n8n)은 conftest 스위치가 꺼 두므로 실제로 나가지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import screening
from app.models import (
    Application,
    AptitudeSession,
    EmailLog,
    InterviewerAssignment,
    InterviewerAvailability,
    JobPosting,
    PostingInterviewer,
    ScheduleProposal,
    StageHistory,
    User,
)

W = screening.DEFAULT_WEIGHTS


# ── 합산 규칙 (순수) ─────────────────────────────────────────────


class TestScoreMath:
    def test_doc_score_weighted(self):
        detail = {"requirements": 80, "preferred": 60, "culture": 70}
        # (80*50 + 60*20 + 70*30) / 100 = 73
        assert screening.doc_score_from(detail, W) == 73

    def test_doc_score_missing_part_renormalizes(self):
        # 우대가 없으면 요건·인재상만으로 (80*50 + 70*30)/80 = 76.25 → 76
        assert screening.doc_score_from({"requirements": 80, "culture": 70}, W) == 76

    def test_doc_score_all_missing_is_none(self):
        assert screening.doc_score_from({}, W) is None

    def test_interview_without_truth_uses_answers_only(self):
        assert screening.interview_score_from(64, None, W) == 64

    def test_interview_with_truth(self):
        # (64*70 + 90*30)/100 = 71.8 → 72
        assert screening.interview_score_from(64, 90, W) == 72

    def test_final_needs_both(self):
        assert screening.final_score(80, None, W) is None
        assert screening.final_score(80, 60, W) == 70.0

    @pytest.mark.parametrize("score,letter", [(90, "S"), (85, "S"), (70, "A"), (55, "B"), (54.9, "C"), (None, None)])
    def test_grade(self, score, letter):
        assert screening.grade(score) == letter

    def test_truth_consistency(self):
        assert screening.truth_consistency(None) is None
        assert screening.truth_consistency({"n": 0}) is None
        assert screening.truth_consistency({"n": 4, "truth_sum": 260.0}) == 65

    def test_weights_fall_back_to_defaults_without_db(self):
        assert screening.weights(None) == W


# ── 판정 (DB) ────────────────────────────────────────────────────


def _score(app: Application, score: int) -> None:
    app.doc_score = score
    app.doc_score_detail = {"requirements": score, "preferred": score, "culture": score}


def _history(db: Session, app: Application) -> list[StageHistory]:
    return db.scalars(
        select(StageHistory).where(StageHistory.application_id == app.id).order_by(StageHistory.id)
    ).all()


class TestDecideDocument:
    def test_pass_moves_to_interview_via_screening(self, db, posting, application):
        _score(application, 75)
        result = screening.decide_document(db, application)

        assert result == "pass"
        assert application.current_stage == "interview"
        assert application.doc_decision == "pass"
        assert application.decision_source == "agent"
        assert application.doc_score_detail["threshold"] == 60
        stages = [h.to_stage for h in _history(db, application)]
        assert stages[-2:] == ["screening", "interview"]
        # 시스템이 옮겼다 — changed_by 는 NULL
        assert all(h.changed_by is None for h in _history(db, application)[-2:])

    def test_pass_creates_aptitude_and_interview_mail_without_pool(self, db, posting, application):
        _score(application, 90)
        screening.decide_document(db, application)

        assert db.scalar(select(AptitudeSession).where(AptitudeSession.application_id == application.id))
        stages = set(db.scalars(select(EmailLog.stage).where(EmailLog.application_id == application.id)))
        assert "custom" in stages  # 인적성 링크 메일
        assert "interview" in stages  # 면접관 풀이 없어 안내 메일로 폴백
        assert application.doc_score_detail["needs_manual_assignment"] is True

    def test_reject_moves_to_rejected_without_mail(self, db, posting, application):
        _score(application, 40)
        result = screening.decide_document(db, application)

        assert result == "reject"
        assert application.current_stage == "rejected"
        assert application.doc_decision == "reject"
        assert _history(db, application)[-1].reason.startswith("아르 서류 심사 불합격")
        # 불합격 메일은 마감 뒤 일괄 — 지금은 행이 없어야 한다
        assert db.scalar(select(EmailLog).where(EmailLog.application_id == application.id)) is None

    def test_threshold_is_per_posting(self, db, posting, application):
        posting.pass_threshold = 80
        _score(application, 75)
        assert screening.decide_document(db, application) == "reject"

    def test_manual_mode_only_scores(self, db, posting, application):
        posting.screening_mode = "manual"
        _score(application, 95)
        assert screening.decide_document(db, application) == "hold"
        assert application.current_stage == "applied"

    def test_human_decision_is_not_overridden(self, db, posting, application):
        application.decision_source = "human"
        _score(application, 95)
        assert screening.decide_document(db, application) == "hold"
        assert application.current_stage == "applied"

    def test_no_score_holds(self, db, posting, application):
        assert screening.decide_document(db, application) == "hold"

    def test_not_applied_holds(self, db, posting, application):
        application.current_stage = "screening"
        _score(application, 95)
        assert screening.decide_document(db, application) == "hold"


class TestInterviewerAutoAssign:
    def _pool(self, db, posting, users: list[User]) -> None:
        for u in users:
            db.add(PostingInterviewer(job_posting_id=posting.id, user_id=u.id))
        db.flush()

    def _avail(self, db, user: User, hours_from_now: int = 24) -> None:
        start = datetime.now(timezone.utc) + timedelta(hours=hours_from_now)
        db.add(InterviewerAvailability(interviewer_id=user.id, start_at=start, end_at=start + timedelta(hours=3)))
        db.flush()

    def test_pick_least_loaded_with_availability(self, db, posting, application, admin_user, member_user, interviewer_user):
        self._pool(db, posting, [admin_user, member_user, interviewer_user])
        self._avail(db, member_user)
        self._avail(db, interviewer_user)
        # member 는 이미 다른 지원자 1건 배정됨 → interviewer 가 뽑힌다
        other = Application(
            job_posting_id=posting.id, name="다른 지원자", email="other@fixture.local", phone="010",
            privacy_agreed_at=datetime.now(timezone.utc),
        )
        db.add(other); db.flush()
        db.add(InterviewerAssignment(application_id=other.id, interviewer_id=member_user.id, assigned_by=admin_user.id))
        db.flush()

        picked = screening.pick_interviewer(db, posting, datetime.now(timezone.utc))
        assert picked == interviewer_user.id  # admin 은 가용 시간이 없어 제외

    def test_empty_pool_returns_none(self, db, posting):
        assert screening.pick_interviewer(db, posting, datetime.now(timezone.utc)) is None

    def test_pass_assigns_and_proposes(self, db, posting, application, admin_user, interviewer_user):
        self._pool(db, posting, [interviewer_user])
        self._avail(db, interviewer_user)
        _score(application, 85)

        screening.decide_document(db, application)

        assigned = db.scalar(
            select(InterviewerAssignment).where(InterviewerAssignment.application_id == application.id)
        )
        assert assigned is not None and assigned.interviewer_id == interviewer_user.id
        proposal = db.scalar(select(ScheduleProposal).where(ScheduleProposal.application_id == application.id))
        assert proposal is not None and proposal.status == "proposed"
        assert application.doc_score_detail["needs_manual_assignment"] is False
        assert application.doc_score_detail["auto_interviewer_id"] == interviewer_user.id


class TestSendPendingRejections:
    def test_only_agent_rejections_without_mail(self, db, posting, application, admin_user):
        _score(application, 10)
        screening.decide_document(db, application)
        assert application.decision_source == "agent"

        # 사람이 직접 불합격시킨 다른 지원자 — 대상 아님
        human = Application(
            job_posting_id=posting.id, name="수동 불합격", email="human@fixture.local", phone="010",
            privacy_agreed_at=datetime.now(timezone.utc), current_stage="rejected", decision_source="human",
        )
        db.add(human); db.flush()

        assert screening.send_pending_rejections(db, posting.id) == 1
        logs = db.scalars(select(EmailLog).where(EmailLog.stage == "rejected")).all()
        assert [log.application_id for log in logs] == [application.id]
        assert logs[0].actor_kind == "agent"

        # 두 번 눌러도 두 번 안 간다
        assert screening.send_pending_rejections(db, posting.id) == 0
