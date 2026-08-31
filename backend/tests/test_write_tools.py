"""쓰기 도구 비즈니스 로직 테스트 — PostgreSQL 사용."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.agent.tools.write import assign_interviewer, change_stage, draft_email
from app.models import Application, EmailLog, StageHistory, User


class TestChangeStage:
    def test_member_can_change(self, db: Session, member_user, application):
        result = change_stage(db, member_user, {
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

    def test_배정되지_않은_멤버도_바꿀_수_있다(self, db: Session, member_user, application):
        """단계 변경에는 역할·배정 제한이 없다 (ADR-0017).

        member_user 는 이 지원자에 배정돼 있지 않다. 그래도 통과해야 한다 —
        member 에게 남은 제한은 평가 작성뿐이다.
        """
        result = change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        assert result["ok"] is True

    def test_invalid_transition_rejected(self, db: Session, member_user, application):
        result = change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "accepted",
        })
        assert "error" in result
        assert "건너뛸" in result["error"]

    def test_nonexistent_application(self, db: Session, member_user):
        result = change_stage(db, member_user, {
            "application_id": 99999,
            "to_stage": "screening",
        })
        assert "error" in result
        assert "찾을 수 없습니다" in result["error"]

    def test_stage_history_created(self, db: Session, member_user, application):
        change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        history = db.query(StageHistory).filter_by(application_id=application.id).all()
        assert len(history) == 1
        assert history[0].from_stage == "applied"
        assert history[0].to_stage == "screening"

    def test_notify_stage_queues_email(self, db: Session, member_user, application):
        application.current_stage = "screening"
        db.flush()
        change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "interview",
        })
        emails = db.query(EmailLog).filter_by(application_id=application.id).all()
        assert len(emails) == 1
        assert emails[0].stage == "interview"
        assert emails[0].status == "queued"

    def test_non_notify_stage_no_email(self, db: Session, member_user, application):
        change_stage(db, member_user, {
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

    def test_member_cannot_assign(self, db: Session, member_user, application, interviewer_user):
        result = assign_interviewer(db, member_user, {
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

    def test_누구나_면접관으로_배정될_수_있다(self, db: Session, admin_user, member_user, application):
        """대상 role 검사는 폐지됐다 (ADR-0017). admin 도 배정 대상이 될 수 있다."""
        result = assign_interviewer(db, admin_user, {
            "application_id": application.id,
            "interviewer_ids": [member_user.id, admin_user.id],
        })
        assert result["ok"] is True
        assert set(result["assigned"]) == {member_user.id, admin_user.id}

    def test_single_id_as_int(self, db: Session, admin_user, interviewer_user, application):
        result = assign_interviewer(db, admin_user, {
            "application_id": application.id,
            "interviewer_ids": interviewer_user.id,
        })
        assert result["ok"] is True


class TestDraftEmail:
    @pytest.mark.parametrize("purpose", ["interview", "accepted", "rejected", "general"])
    def test_all_purposes(self, db: Session, member_user, application, purpose):
        result = draft_email(db, member_user, {
            "application_id": application.id,
            "purpose": purpose,
        })
        assert result["ok"] is True
        assert result["to"] == application.email
        assert "subject" in result
        assert "body" in result
        assert application.name in result["body"]

    def test_default_purpose_is_general(self, db: Session, member_user, application):
        result = draft_email(db, member_user, {
            "application_id": application.id,
        })
        assert result["ok"] is True
        assert "여기에 내용을 작성하세요" in result["body"]

    def test_nonexistent_application(self, db: Session, member_user):
        result = draft_email(db, member_user, {
            "application_id": 99999,
        })
        assert "error" in result


class TestStageChangeSideEffects:
    """#148 재발 방지 — 에이전트 경로가 REST 와 같은 부수효과를 내는가.

    전에는 `email_logs` 행만 만들고 SQS 발행을 하지 않아 **메일이 영영 나가지
    않는데 응답은 `mail_queued: true`** 였다. 행 존재만 보는 테스트는 이 결함을
    통과시킨다 — 그래서 여기서는 **발행이 실제로 불렸는지**를 본다.
    """

    def test_큐로_발행까지_한다(self, db: Session, member_user, application, monkeypatch):
        published: list[int] = []
        monkeypatch.setattr("app.mail.publish", published.append)

        result = change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        result = change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "interview",  # NOTIFY_STAGES — 메일이 나가야 하는 단계
        })

        assert result["mail_queued"] is True
        assert len(published) == 1  # 행만 만들고 끝내면 여기서 걸린다

    def test_큐가_죽어도_단계_변경은_성공한다(
        self, db: Session, member_user, application, monkeypatch
    ):
        # 담당자가 카드를 못 옮기는 것이 메일이 늦는 것보다 나쁘다.
        def boom(_id):
            raise RuntimeError("SQS down")

        monkeypatch.setattr("app.mail.publish", boom)
        change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "screening",
        })
        result = change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "interview",
        })

        assert result["ok"] is True
        assert result["mail_queued"] is False

    def test_불합격은_사유가_필요하다(self, db: Session, member_user, application, monkeypatch):
        # D8. REST 에는 있던 규칙이 에이전트 경로에는 없었다.
        monkeypatch.setattr("app.mail.publish", lambda _id: None)
        result = change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "rejected",
        })
        assert "error" in result
        assert "사유" in result["error"]

    def test_불합격_사유가_이력에_남는다(
        self, db: Session, member_user, application, monkeypatch
    ):
        monkeypatch.setattr("app.mail.publish", lambda _id: None)
        result = change_stage(db, member_user, {
            "application_id": application.id,
            "to_stage": "rejected",
            "reason": "요구 기술 경험 부족",
        })
        assert result["ok"] is True

        row = (
            db.query(StageHistory)
            .filter(StageHistory.application_id == application.id)
            .order_by(StageHistory.id.desc())
            .first()
        )
        assert row.reason == "요구 기술 경험 부족"
