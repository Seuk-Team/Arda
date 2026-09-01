"""쓰기 도구 비즈니스 로직 테스트 — PostgreSQL 사용."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent.tools.write import (
    assign_interviewer,
    change_stage,
    draft_email,
    send_email,
)
from app.models import (
    Application,
    EmailLog,
    EmailTemplate,
    StageHistory,
    User,
)


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

    def test_설정에서_고친_문구를_쓴다(self, db: Session, admin_user, application):
        """예전에는 자체 하드코딩 문구라, 담당자가 문구를 고쳐도 아르만 옛 말을 했다."""
        db.add(
            EmailTemplate(
                stage="interview",
                subject="바뀐 제목",
                body="{지원자명} 님, 바뀐 본문입니다.\n\n{서명}",
                updated_by=admin_user.id,
            )
        )
        db.flush()
        result = draft_email(db, admin_user, {
            "application_id": application.id,
            "purpose": "interview",
        })
        assert result["subject"] == "바뀐 제목"
        assert "바뀐 본문입니다" in result["body"]

    def test_아르_이름으로_서명한다(self, db: Session, admin_user, application):
        result = draft_email(db, admin_user, {
            "application_id": application.id,
            "purpose": "interview",
        })
        assert "채용 에이전트 아르 드림" in result["body"]

    def test_불합격_초안은_사람_이름으로_서명한다(
        self, db: Session, admin_user, application
    ):
        """AI 가 심사했다는 오해를 만들지 않는다 (G4 결정 6)."""
        result = draft_email(db, admin_user, {
            "application_id": application.id,
            "purpose": "rejected",
        })
        assert f"채용 담당자 {admin_user.name} 드림" in result["body"]

    def test_초안은_아무것도_보내지_않는다(
        self, db: Session, admin_user, application
    ):
        before = db.scalar(
            select(func.count(EmailLog.id)).where(
                EmailLog.application_id == application.id
            )
        )
        draft_email(db, admin_user, {
            "application_id": application.id,
            "purpose": "interview",
        })
        after = db.scalar(
            select(func.count(EmailLog.id)).where(
                EmailLog.application_id == application.id
            )
        )
        assert before == after


class TestSendEmail:
    """실제 발송 도구 (G4). 확인 게이트를 지난 뒤에만 여기까지 온다."""

    @pytest.fixture(autouse=True)
    def _no_queue(self, monkeypatch):
        self.published: list[int] = []
        monkeypatch.setattr(
            "app.stage_service.mail.publish", lambda i: self.published.append(i)
        )

    def test_행이_남고_큐까지_발행한다(self, db: Session, member_user, application):
        result = send_email(db, member_user, {
            "application_id": application.id,
            "subject": "면접 안내드립니다",
            "body": "내일 뵙겠습니다.",
        })
        assert result["ok"] is True
        log = db.get(EmailLog, result["email_log_id"])
        assert log.stage == "custom"
        assert log.actor_kind == "agent"
        assert log.actor_id == member_user.id  # 아르가 아니라 승인한 사람
        assert self.published == [log.id]

    def test_수신자는_지원자_주소로_고정된다(
        self, db: Session, member_user, application
    ):
        """도구가 주소를 인자로 받지 않는다 — 오발송 반경을 여기서 자른다."""
        result = send_email(db, member_user, {
            "application_id": application.id,
            "subject": "제목",
            "body": "본문",
            "to": "attacker@evil.example",  # 무시된다
        })
        log = db.get(EmailLog, result["email_log_id"])
        assert log.to_email == application.email

    def test_서명이_붙는다(self, db: Session, member_user, application):
        result = send_email(db, member_user, {
            "application_id": application.id,
            "subject": "제목",
            "body": "본문",
        })
        log = db.get(EmailLog, result["email_log_id"])
        assert log.body.rstrip().endswith("채용 에이전트 아르 드림")

    def test_제목이나_본문이_비면_에러(self, db: Session, member_user, application):
        assert "error" in send_email(db, member_user, {
            "application_id": application.id, "subject": "  ", "body": "본문",
        })
        assert "error" in send_email(db, member_user, {
            "application_id": application.id, "subject": "제목", "body": "",
        })

    def test_없는_지원자는_에러(self, db: Session, member_user):
        assert "error" in send_email(db, member_user, {
            "application_id": 99999, "subject": "제목", "body": "본문",
        })


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
