"""n8n 워크플로 전용 내부 API — /internal/email-logs/{id}/render · /result.

인증(서비스 토큰), 렌더, 결과 기록의 멱등성 을 검증한다. 실제 SES·SMTP 호출은
없다 — 이 API 는 데이터 층만 만진다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models import Application, EmailLog, JobPosting, User


@pytest.fixture()
def client(db: Session, monkeypatch) -> TestClient:
    """서비스 토큰만 세팅한 클라이언트 — 별도 사용자 인증은 없다(공용 게이트)."""
    monkeypatch.setenv("ARDA_SERVICE_TOKEN", "test-token-x")
    monkeypatch.setenv("SES_FROM_EMAIL", "no-reply@test.local")
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def sample_log(db: Session, admin_user: User) -> EmailLog:
    """지원자·공고·로그 최소 세팅. system 발송·applied 단계.

    **`created_by` 에 상수를 박지 않는다.** `created_by=1` 로 두면 빈 테스트 DB
    에는 id 1 인 사용자가 없어 FK 위반으로 죽는다 — 로컬에 시드가 있으면 통과하고
    CI(빈 DB)에서만 깨져서 원인을 찾기 어렵다. conftest 의 `admin_user` 를 쓴다.
    """
    posting = JobPosting(
        title="테스트 공고", description="본문", status="open", created_by=admin_user.id
    )
    db.add(posting)
    db.flush()

    application = Application(
        job_posting_id=posting.id,
        name="지원자김",
        email="candidate@test.local",
        phone="010-1234-5678",
        privacy_agreed_at=datetime.now(UTC),
    )
    db.add(application)
    db.flush()

    log = EmailLog(
        application_id=application.id,
        to_email="candidate@test.local",
        stage="applied",
        status="queued",
        actor_kind="system",
    )
    db.add(log)
    db.commit()
    return log


class TestAuth:
    def test_missing_token_401(self, client, sample_log):
        r = client.get(f"/api/v1/internal/email-logs/{sample_log.id}/render")
        assert r.status_code == 401

    def test_wrong_token_401(self, client, sample_log):
        r = client.get(
            f"/api/v1/internal/email-logs/{sample_log.id}/render",
            headers={"X-Service-Token": "wrong"},
        )
        assert r.status_code == 401

    def test_env_not_set_401(self, db: Session, monkeypatch, sample_log):
        monkeypatch.delenv("ARDA_SERVICE_TOKEN", raising=False)
        app.dependency_overrides[get_db] = lambda: db
        c = TestClient(app, raise_server_exceptions=False)
        r = c.get(
            f"/api/v1/internal/email-logs/{sample_log.id}/render",
            headers={"X-Service-Token": "anything"},
        )
        assert r.status_code == 401
        app.dependency_overrides.pop(get_db, None)


class TestRender:
    HEADERS = {"X-Service-Token": "test-token-x"}

    def test_render_applied_template(self, client, sample_log):
        r = client.get(
            f"/api/v1/internal/email-logs/{sample_log.id}/render",
            headers=self.HEADERS,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["to"] == "candidate@test.local"
        assert "지원자김" in data["body_text"]
        assert data["subject"]
        assert data["from_email"] == "no-reply@test.local"
        assert data["body_html"] is None

    def test_render_uses_committed_body(self, client, sample_log, db: Session):
        sample_log.subject = "고정된 제목"
        sample_log.body = "이 문장 그대로 나감"
        db.commit()

        r = client.get(
            f"/api/v1/internal/email-logs/{sample_log.id}/render",
            headers=self.HEADERS,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["subject"] == "고정된 제목"
        assert data["body_text"] == "이 문장 그대로 나감"

    def test_render_missing_log_404(self, client):
        r = client.get(
            "/api/v1/internal/email-logs/999999/render",
            headers=self.HEADERS,
        )
        assert r.status_code == 404

    def test_render_already_sent_409(self, client, sample_log, db: Session):
        sample_log.status = "sent"
        db.commit()

        r = client.get(
            f"/api/v1/internal/email-logs/{sample_log.id}/render",
            headers=self.HEADERS,
        )
        assert r.status_code == 409


class TestResult:
    HEADERS = {"X-Service-Token": "test-token-x"}

    def test_record_sent(self, client, sample_log, db: Session):
        r = client.post(
            f"/api/v1/internal/email-logs/{sample_log.id}/result",
            headers=self.HEADERS,
            json={"status": "sent", "provider_message_id": "<msg-1@n8n>"},
        )
        assert r.status_code == 204, r.text

        db.refresh(sample_log)
        assert sample_log.status == "sent"
        assert sample_log.provider_message_id == "<msg-1@n8n>"
        assert sample_log.sent_at is not None

    def test_record_failed_increments_retry(self, client, sample_log, db: Session):
        sample_log.retry_count = 2
        db.commit()

        r = client.post(
            f"/api/v1/internal/email-logs/{sample_log.id}/result",
            headers=self.HEADERS,
            json={"status": "failed", "error": "smtp timeout"},
        )
        assert r.status_code == 204

        db.refresh(sample_log)
        assert sample_log.status == "failed"
        assert sample_log.retry_count == 3

    def test_record_sent_is_idempotent(self, client, sample_log, db: Session):
        client.post(
            f"/api/v1/internal/email-logs/{sample_log.id}/result",
            headers=self.HEADERS,
            json={"status": "sent", "provider_message_id": "<msg-1@n8n>"},
        )
        db.refresh(sample_log)
        first_sent_at = sample_log.sent_at
        assert sample_log.provider_message_id == "<msg-1@n8n>"

        r = client.post(
            f"/api/v1/internal/email-logs/{sample_log.id}/result",
            headers=self.HEADERS,
            json={"status": "sent", "provider_message_id": "<msg-2@n8n>"},
        )
        assert r.status_code == 204

        db.refresh(sample_log)
        assert sample_log.status == "sent"
        assert sample_log.provider_message_id == "<msg-1@n8n>"
        assert sample_log.sent_at == first_sent_at

    def test_missing_log_404(self, client):
        r = client.post(
            "/api/v1/internal/email-logs/999999/result",
            headers=self.HEADERS,
            json={"status": "sent"},
        )
        assert r.status_code == 404

    def test_missing_token_401(self, client, sample_log):
        r = client.post(
            f"/api/v1/internal/email-logs/{sample_log.id}/result",
            json={"status": "sent"},
        )
        assert r.status_code == 401


class TestPublishDispatch:
    """mail.publish 가 MAIL_DISPATCH 값에 따라 갈리는지."""

    def test_worker_default_uses_sqs(self, monkeypatch):
        from app import mail

        monkeypatch.delenv("MAIL_DISPATCH", raising=False)

        calls = {"sqs": 0, "n8n": 0}

        class _FakeSqs:
            def send_message(self, **_kw):
                calls["sqs"] += 1

        monkeypatch.setattr(mail, "_sqs", lambda: _FakeSqs())
        monkeypatch.setattr(mail, "_queue_url", lambda: "q")
        monkeypatch.setattr(mail, "_publish_to_n8n", lambda _id: calls.__setitem__("n8n", calls["n8n"] + 1))

        mail.publish(1)
        assert calls == {"sqs": 1, "n8n": 0}

    def test_n8n_dispatch_calls_webhook(self, monkeypatch):
        from app import mail

        monkeypatch.setenv("MAIL_DISPATCH", "n8n")

        calls = {"sqs": 0, "n8n": 0}
        monkeypatch.setattr(mail, "_publish_to_n8n", lambda _id: calls.__setitem__("n8n", calls["n8n"] + 1))

        def _fail_sqs():
            raise AssertionError("worker path called when n8n set")

        monkeypatch.setattr(mail, "_sqs", _fail_sqs)

        mail.publish(1)
        assert calls == {"sqs": 0, "n8n": 1}
