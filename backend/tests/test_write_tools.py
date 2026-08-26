"""쓰기 도구 비즈니스 로직 테스트 — PostgreSQL 사용."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.agent.tools.write import assign_interviewer, change_stage, draft_email
from app.models import Application, EmailLog, StageHistory, User


class TestChangeStage:
    def test_recruiter_can_change(self, db: Session, recruiter_user, application):
        result = change_stage(db, recruiter_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        assert result["ok"] is True
        assert result["from_stage"] == "applied"
        assert result["to_stage"] == "screening"

    def test_admin_can_change(self, db: Session, admin_user, application):
        result = change_stage(db, admin_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        assert result["ok"] is True

    def test_interviewer_cannot_change(self, db: Session, interviewer_user, application):
        result = change_stage(db, interviewer_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        assert "error" in result
        assert "권한" in result["error"]

    def test_invalid_transition_rejected(self, db: Session, recruiter_user, application):
        result = change_stage(db, recruiter_user, {
            "application_id": application.id,
            "to_stage": "accepted",
        })
        assert "error" in result
        assert "건너뛸" in result["error"]

    def test_nonexistent_application(self, db: Session, recruiter_user):
        result = change_stage(db, recruiter_user, {
            "application_id": 99999,
            "to_stage": "screening",
        })
        assert "error" in result
        assert "찾을 수 없습니다" in result["error"]

    def test_stage_history_created(self, db: Session, recruiter_user, application):
        change_stage(db, recruiter_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        history = db.query(StageHistory).filter_by(application_id=application.id).all()
        assert len(history) == 1
        assert history[0].from_stage == "applied"
        assert history[0].to_stage == "screening"

    def test_notify_stage_queues_email(self, db: Session, recruiter_user, application):
        application.current_stage = "screening"
        db.flush()
        change_stage(db, recruiter_user, {
            "application_id": application.id,
            "to_stage": "interview",
        })
        emails = db.query(EmailLog).filter_by(application_id=application.id).all()
        assert len(emails) == 1
        assert emails[0].stage == "interview"
        assert emails[0].status == "queued"

    def test_non_notify_stage_no_email(self, db: Session, recruiter_user, application):
        change_stage(db, recruiter_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        emails = db.query(EmailLog).filter_by(application_id=application.id).all()
        assert len(emails) == 0


class TestAssignInterviewer:
    def test_admin_can_assign(self, db: Session, admin_user, interviewer_user, application):
        result = assign_interviewer(db, admin_user, {
            "application_id": application.id,
            "interviewer_ids": [interviewer_user.id],
        })
        assert result["ok"] is True
        assert interviewer_user.id in result["assigned"]

    def test_recruiter_cannot_assign(self, db: Session, recruiter_user, application, interviewer_user):
        result = assign_interviewer(db, recruiter_user, {
            "application_id": application.id,
            "interviewer_ids": [interviewer_user.id],
        })
        assert "error" in result
        assert "어드민" in result["error"]

    def test_nonexistent_application(self, db: Session, admin_user):
        result = assign_interviewer(db, admin_user, {
            "application_id": 99999,
            "interviewer_ids": [1],
        })
        assert "error" in result

    def test_non_interviewer_rejected(self, db: Session, admin_user, recruiter_user, application):
        result = assign_interviewer(db, admin_user, {
            "application_id": application.id,
            "interviewer_ids": [recruiter_user.id],
        })
        assert "error" in result
        assert "면접관이 아닌" in result["error"]

    def test_single_id_as_int(self, db: Session, admin_user, interviewer_user, application):
        result = assign_interviewer(db, admin_user, {
            "application_id": application.id,
            "interviewer_ids": interviewer_user.id,
        })
        assert result["ok"] is True


class TestDraftEmail:
    @pytest.mark.parametrize("purpose", ["interview", "accepted", "rejected", "general"])
    def test_all_purposes(self, db: Session, recruiter_user, application, purpose):
        result = draft_email(db, recruiter_user, {
            "application_id": application.id,
            "purpose": purpose,
        })
        assert result["ok"] is True
        assert result["to"] == application.email
        assert "subject" in result
        assert "body" in result
        assert application.name in result["body"]

    def test_default_purpose_is_general(self, db: Session, recruiter_user, application):
        result = draft_email(db, recruiter_user, {
            "application_id": application.id,
        })
        assert result["ok"] is True
        assert "여기에 내용을 작성하세요" in result["body"]

    def test_nonexistent_application(self, db: Session, recruiter_user):
        result = draft_email(db, recruiter_user, {
            "application_id": 99999,
        })
        assert "error" in result
