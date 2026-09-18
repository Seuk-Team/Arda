"""메일 SMTP 폴백 — n8n 이 멈춰도 통보가 나간다 (2026-09-16).

발송 경로가 **n8n 하나뿐**이라 그것이 멈추면 합격·불합격 통보가 통째로 멎는다.
그 사실이 드러나는 것은 지원자가 "연락이 없다" 고 말할 때다
([ADR-0031](../../docs/03_decision/0031-aws-최소화.md) 의 "워커는 SMTP 20줄 비상
폴백만" · [ADR-0036](../../docs/03_decision/0036-SQS-워커-폐기.md) 후속).

**실제 SMTP 는 부르지 않는다** — `send_message` 를 mock 한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.hiring.company import get_profile
from app.models import Application, EmailLog, JobPosting, User
from app.shared import mail, mail_smtp


@pytest.fixture()
def log(db: Session, admin_user: User) -> EmailLog:
    posting = JobPosting(
        title="공고", description="본문", status="open", created_by=admin_user.id
    )
    db.add(posting)
    db.flush()
    application = Application(
        job_posting_id=posting.id,
        name="지원자정",
        email="fallback@test.local",
        phone="010-0000-0000",
        privacy_agreed_at=datetime.now(UTC),
    )
    db.add(application)
    db.flush()
    row = EmailLog(
        application_id=application.id,
        to_email=application.email,
        stage="applied",
        status="queued",
        actor_kind="system",
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def smtp_on(monkeypatch):
    monkeypatch.setattr(mail_smtp, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(mail_smtp, "SMTP_USER", "bot@test.local")
    monkeypatch.setattr(mail_smtp, "SMTP_PASSWORD", "pw")


class TestSendLog:
    def test_보내면_sent_로_남는다(self, db: Session, log: EmailLog, smtp_on):
        with patch("app.shared.mail_smtp.send_message") as sent:
            assert mail_smtp.send_log(db, log) is True

        sent.assert_called_once()
        assert log.status == "sent"
        assert log.sent_at is not None

    def test_보낸_사람_이름은_DB_회사명을_쓴다(self, db: Session, log: EmailLog, smtp_on):
        """환경변수(시험에서는 Arda)가 아니라 company_profile.name (2026-09-17 운영 점검)."""
        get_profile(db).name = "코드브릿지"
        db.flush()
        with patch("app.shared.mail_smtp.send_message") as sent:
            mail_smtp.send_log(db, log)

        assert sent.call_args.kwargs["from_name"] == "코드브릿지 채용팀"

    def test_폴백으로_나간_것을_구별할_수_있다(self, db: Session, log: EmailLog, smtp_on):
        """`provider_message_id` 가 빈 `sent` 행이 곧 "폴백으로 나갔다" 는 표시다."""
        with patch("app.shared.mail_smtp.send_message"):
            mail_smtp.send_log(db, log)

        assert log.provider_message_id is None

    def test_이미_보낸_행은_다시_안_보낸다(self, db: Session, log: EmailLog, smtp_on):
        """두 번째 사본이 가면 지원자는 같은 통보를 두 번 받는다."""
        log.status = "sent"
        db.commit()

        with patch("app.shared.mail_smtp.send_message") as sent:
            assert mail_smtp.send_log(db, log) is False
        sent.assert_not_called()

    def test_실패하면_재시도_횟수만_올리고_queued_로_둔다(
        self, db: Session, log: EmailLog, smtp_on
    ):
        with patch(
            "app.shared.mail_smtp.send_message", side_effect=RuntimeError("SMTP 죽음")
        ):
            assert mail_smtp.send_log(db, log) is False

        assert log.status == "queued", "실패를 sent 로 적으면 영영 안 보낸다"
        assert log.retry_count == 1


class TestFlushPending:
    """n8n 이 웹훅은 받고(200) 그 뒤 죽으면 행이 `queued` 로 남는다 — 발행 시점에는
    성공으로 보여 폴백이 안 걸린다. 그래서 나중에 훑는 경로가 따로 필요하다."""

    def test_오래_묵은_것만_보낸다(self, db: Session, log: EmailLog, smtp_on):
        log.created_at = datetime.now(UTC) - timedelta(minutes=30)
        db.commit()

        with patch("app.shared.mail_smtp.send_message"):
            result = mail_smtp.flush_pending(db, after_min=10)

        assert result == {"found": 1, "sent": 1, "given_up": 0}
        assert log.status == "sent"

    def test_여러_건을_한_회차에_모두_보낸다(self, db: Session, log: EmailLog, smtp_on):
        """한 행씩 잠그고 보내는 반복이 첫 행에서 멈추지 않는다."""
        old = datetime.now(UTC) - timedelta(minutes=30)
        other = EmailLog(
            application_id=log.application_id, to_email=log.to_email,
            stage="custom", subject="안내", body="확정 본문",
            status="queued", actor_kind="system", created_at=old,
        )
        log.created_at = old
        db.add(other)
        db.commit()

        with patch("app.shared.mail_smtp.send_message") as sent:
            result = mail_smtp.flush_pending(db, after_min=10)

        assert result == {"found": 2, "sent": 2, "given_up": 0}
        assert sent.call_count == 2
        assert log.status == other.status == "sent"

    def test_실패한_행은_같은_회차에_다시_집지_않는다(self, db: Session, log: EmailLog, smtp_on):
        """실패하면 queued 로 남는다 — 같은 회차에 또 집으면 상한까지 연달아 두드린다."""
        log.created_at = datetime.now(UTC) - timedelta(minutes=30)
        db.commit()

        with patch(
            "app.shared.mail_smtp.send_message", side_effect=RuntimeError("SMTP 죽음")
        ) as sent:
            result = mail_smtp.flush_pending(db, after_min=10)

        assert sent.call_count == 1
        assert result == {"found": 1, "sent": 0, "given_up": 0}
        assert log.status == "queued"
        assert log.retry_count == 1

    def test_상한만큼_실패하면_failed_로_접는다(self, db: Session, log: EmailLog, smtp_on):
        """주소가 틀렸거나 계정이 잠긴 행을 몇 분마다 영원히 두드리지 않는다."""
        log.created_at = datetime.now(UTC) - timedelta(minutes=30)
        log.retry_count = mail_smtp.FLUSH_MAX_RETRY - 1
        db.commit()

        with patch("app.shared.mail_smtp.send_message", side_effect=RuntimeError("거절")):
            result = mail_smtp.flush_pending(db, after_min=10)

        assert result["given_up"] == 1
        assert log.status == "failed"

        # 접힌 뒤에는 다시 집지 않는다
        with patch("app.shared.mail_smtp.send_message") as sent:
            assert mail_smtp.flush_pending(db, after_min=10)["found"] == 0
        sent.assert_not_called()

    def test_방금_생긴_것은_건드리지_않는다(self, db: Session, log: EmailLog, smtp_on):
        """n8n 이 정상이면 몇 초 안에 나간다 — 그 사이에 끼어들면 두 번 간다."""
        with patch("app.shared.mail_smtp.send_message") as sent:
            result = mail_smtp.flush_pending(db, after_min=10)

        assert result["found"] == 0
        sent.assert_not_called()

    def test_failed_는_되살리지_않는다(self, db: Session, log: EmailLog, smtp_on):
        """상한을 넘겨 접은 건이다 — 되살리려면 사람이 보고 판단해야 한다."""
        log.status = "failed"
        log.created_at = datetime.now(UTC) - timedelta(hours=2)
        db.commit()

        with patch("app.shared.mail_smtp.send_message") as sent:
            assert mail_smtp.flush_pending(db, after_min=10)["found"] == 0
        sent.assert_not_called()


class TestFlushLoop:
    """쓸어 담기를 API 가 스스로 돈다 (2026-09-17, 수택님 B1).

    전에는 `python -m app.shared.mail_smtp` 를 사람이 쳐야 했다 — 사람이 n8n 장애를
    모르는 동안은 아무도 안 보냈다.
    """

    def test_SMTP_설정이_없으면_띄우지_않는다(self, monkeypatch):
        monkeypatch.setattr(mail_smtp, "SMTP_HOST", "")
        assert mail_smtp.start_flush_loop() is None

    def test_간격이_0이면_띄우지_않는다(self, monkeypatch, smtp_on):
        monkeypatch.setattr(mail_smtp, "FLUSH_INTERVAL_MIN", 0)
        assert mail_smtp.start_flush_loop() is None

    def test_간격마다_쓸어_담고_멈추라면_멈춘다(self, monkeypatch, smtp_on):
        import threading

        monkeypatch.setattr(mail_smtp, "FLUSH_INTERVAL_MIN", 0.001)  # 0.06초
        ran = threading.Event()
        calls: list[int] = []

        class _Db:
            def __enter__(self):
                return "db"

            def __exit__(self, *exc):
                return False

        def fake_flush(db):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("한 회차 실패")  # 다음 회차는 돌아야 한다
            ran.set()
            return {}

        monkeypatch.setattr("app.db.SessionLocal", lambda: _Db())
        monkeypatch.setattr(mail_smtp, "flush_pending", fake_flush)

        stop = mail_smtp.start_flush_loop()
        assert stop is not None
        try:
            assert ran.wait(5), "두 번째 회차가 돌지 않았다"
        finally:
            stop.set()
        n = len(calls)
        threading.Event().wait(0.3)
        assert len(calls) <= n + 1, "멈추라고 했는데 계속 돈다"


class TestPublishFallback:
    """`mail.publish` 가 n8n 에 못 실으면 SMTP 로 물러선다."""

    class _Broken:
        def publish(self, email_log_id: int) -> None:
            raise RuntimeError("n8n 죽음")

    def test_n8n_이_죽으면_SMTP_로_보낸다(self, smtp_on):
        with patch("app.shared.mail_smtp.send_log_id", return_value=True) as fb:
            mail.publish(7, dispatcher=self._Broken())
        fb.assert_called_once_with(7)

    def test_SMTP_설정이_없으면_예외를_올린다(self, monkeypatch):
        """설정이 없는데 **조용히 다른 데로 보내지 않는다.** 호출부가 알아야 한다."""
        monkeypatch.setattr(mail_smtp, "SMTP_HOST", "")

        with pytest.raises(RuntimeError):
            mail.publish(7, dispatcher=self._Broken())

    def test_폴백마저_실패하면_예외를_올린다(self, smtp_on):
        with patch("app.shared.mail_smtp.send_log_id", return_value=False):
            with pytest.raises(RuntimeError):
                mail.publish(7, dispatcher=self._Broken())

    def test_이미_SMTP_경로면_다시_안_부른다(self, smtp_on):
        """폴백이 자기 자신을 또 부르면 실패가 두 번 난다."""
        from app.adapter.outbound.mail import SmtpMailDispatcher

        with patch(
            "app.shared.mail_smtp.send_log_id", side_effect=RuntimeError("SMTP 죽음")
        ) as fb:
            with pytest.raises(RuntimeError):
                mail.publish(7, dispatcher=SmtpMailDispatcher())
        assert fb.call_count == 1


class TestSwitch:
    def test_smtp_env_uses_smtp_dispatcher(self, monkeypatch):
        from app.adapter.outbound.mail import SmtpMailDispatcher

        monkeypatch.setenv("MAIL_DISPATCH", "smtp")
        assert isinstance(mail._get_dispatcher(), SmtpMailDispatcher)

    def test_설정이_없으면_폴백은_꺼진_것으로_본다(self, monkeypatch):
        monkeypatch.setattr(mail_smtp, "SMTP_HOST", "")
        assert mail_smtp.available() is False
