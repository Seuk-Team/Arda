"""사전 성향 설문 API (ADR-0027) — 발송·공개 응답·담당자 조회.

이 기능의 경계는 ADR 이 고정했고, 무너지면 사고인 것들에 테스트를 붙인다:

- **전 문항 필수·재제출 불가** — 부분 응답은 통계를 왜곡한다
- **공개 라우트가 담당자 정보를 내려주지 않는다** (AI 면접과 같은 규칙)
- **문항 스냅샷** — 상수가 바뀌어도 지원자가 본 문장이 남는다
- 발송 대상은 접수·서류검토 단계뿐, 이미 받은 지원자는 일괄 발송에서 제외
- 만료는 조회 시점 판정 (B4·일정 제안·AI 면접과 같은 방식)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.aptitude_questions import QUESTION_KEYS, QUESTIONS
from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import (
    Application,
    AptitudeAnswer,
    AptitudeSession,
    EmailLog,
    JobPosting,
    User,
)


@pytest.fixture()
def as_user(db: Session, monkeypatch):
    monkeypatch.setattr(mail, "publish", lambda _id: None)

    def make(user: User) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


@pytest.fixture()
def public(db: Session):
    """토큰만으로 접근하는 공개 라우트용. 인증을 걸지 않는다."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _session(db: Session, application: Application, admin_user: User, **kw) -> AptitudeSession:
    row = AptitudeSession(
        application_id=application.id,
        token=kw.pop("token", "apt-tok-test"),
        status=kw.pop("status", "pending"),
        expires_at=kw.pop("expires_at", datetime.now(UTC) + timedelta(days=7)),
        created_by=admin_user.id,
        **kw,
    )
    db.add(row)
    db.flush()
    return row


def _full_answers(value: int = 4) -> list[dict]:
    return [{"key": k, "value": value} for k in QUESTION_KEYS]


def _application(db: Session, posting: JobPosting, *, stage: str, email: str) -> Application:
    row = Application(
        job_posting_id=posting.id,
        name="테스트지원자",
        email=email,
        phone="010-0000-0000",
        current_stage=stage,
        privacy_agreed_at=datetime.now(UTC),
        source="form",
    )
    db.add(row)
    db.flush()
    return row


# ── 발송 ──────────────────────────────────────────────────────────


class TestSend:
    def test_bulk_send_creates_sessions_and_mail(
        self, as_user, admin_user, posting, application, db: Session
    ):
        client = as_user(admin_user)
        resp = client.post(f"/api/v1/postings/{posting.id}/aptitude/send")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sent"] == 1
        assert body["skipped_already_sent"] == 0
        assert body["skipped_stage"] == 0

        session = db.scalar(
            select(AptitudeSession).where(
                AptitudeSession.application_id == application.id
            )
        )
        assert session is not None
        assert session.status == "pending"

        log = db.scalar(
            select(EmailLog).where(EmailLog.application_id == application.id)
        )
        assert log is not None
        assert log.status == "queued"
        assert session.token in log.body  # 링크가 본문에 실린다
        assert "불이익이 없습니다" in log.body  # ADR-0027 결정 4 의 문구

    def test_bulk_send_skips_already_sent_and_late_stages(
        self, as_user, admin_user, posting, application, db: Session
    ):
        _session(db, application, admin_user)  # 이미 발송된 지원자
        late = _application(db, posting, stage="accepted", email="late@fixture.local")

        client = as_user(admin_user)
        body = client.post(f"/api/v1/postings/{posting.id}/aptitude/send").json()
        assert body["sent"] == 0
        assert body["skipped_already_sent"] == 1
        assert body["skipped_stage"] == 1
        assert (
            db.scalar(
                select(AptitudeSession).where(
                    AptitudeSession.application_id == late.id
                )
            )
            is None
        )

    def test_send_one_always_new_row(
        self, as_user, admin_user, application, db: Session
    ):
        """재발송은 새 행 — 옛 링크가 죽지 않는다 (AI 면접과 같은 철학)."""
        _session(db, application, admin_user, token="apt-old")
        client = as_user(admin_user)
        resp = client.post(f"/api/v1/applications/{application.id}/aptitude/send")
        assert resp.status_code == 201
        rows = db.scalars(
            select(AptitudeSession).where(
                AptitudeSession.application_id == application.id
            )
        ).all()
        assert len(rows) == 2

    def test_send_one_rejects_late_stage(
        self, as_user, admin_user, posting, db: Session
    ):
        late = _application(db, posting, stage="interview", email="itv@fixture.local")
        client = as_user(admin_user)
        resp = client.post(f"/api/v1/applications/{late.id}/aptitude/send")
        assert resp.status_code == 422


# ── 공개 라우트 ────────────────────────────────────────────────────


class TestPublic:
    def test_get_pending_returns_questions_only(
        self, public, admin_user, application, posting, db: Session
    ):
        _session(db, application, admin_user)
        body = public.get("/api/v1/public/aptitude/apt-tok-test").json()
        assert body["status"] == "pending"
        assert body["applicant_name"] == application.name
        assert body["posting_title"] == posting.title
        assert len(body["questions"]) == len(QUESTIONS)
        # 담당자·토큰·평가 정보를 내려주지 않는다
        assert "token" not in body
        assert "created_by" not in body

    def test_unknown_token_404(self, public):
        assert public.get("/api/v1/public/aptitude/no-such").status_code == 404

    def test_expiry_judged_at_read(
        self, public, admin_user, application, db: Session
    ):
        _session(
            db,
            application,
            admin_user,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        body = public.get("/api/v1/public/aptitude/apt-tok-test").json()
        assert body["status"] == "expired"
        assert body["questions"] == []


class TestSubmit:
    def test_happy_path_snapshots_questions(
        self, public, admin_user, application, db: Session
    ):
        session = _session(db, application, admin_user)
        with patch("app.api.aptitude.generate_aptitude_summary_bg") as bg:
            resp = public.post(
                "/api/v1/public/aptitude/apt-tok-test/submit",
                json={"answers": _full_answers()},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "done"
        assert bg.call_count == 1

        db.refresh(session)
        assert session.status == "done"
        assert session.submitted_at is not None
        answers = db.scalars(
            select(AptitudeAnswer).where(AptitudeAnswer.session_id == session.id)
        ).all()
        assert len(answers) == len(QUESTIONS)
        # 문항 문구 스냅샷 — 상수가 바뀌어도 지원자가 본 문장이 남는다
        by_key = {a.question_key: a for a in answers}
        for q in QUESTIONS:
            assert by_key[q["key"]].question_text == q["text"]

    def test_partial_answers_rejected(
        self, public, admin_user, application, db: Session
    ):
        _session(db, application, admin_user)
        answers = _full_answers()[:-1]  # 한 문항 누락
        resp = public.post(
            "/api/v1/public/aptitude/apt-tok-test/submit",
            json={"answers": answers},
        )
        assert resp.status_code == 422

    def test_unknown_key_rejected(
        self, public, admin_user, application, db: Session
    ):
        _session(db, application, admin_user)
        answers = _full_answers()
        answers[0] = {"key": "made_up_key", "value": 3}
        resp = public.post(
            "/api/v1/public/aptitude/apt-tok-test/submit",
            json={"answers": answers},
        )
        assert resp.status_code == 422

    def test_value_out_of_range_rejected(
        self, public, admin_user, application, db: Session
    ):
        _session(db, application, admin_user)
        answers = _full_answers()
        answers[0]["value"] = 6
        resp = public.post(
            "/api/v1/public/aptitude/apt-tok-test/submit",
            json={"answers": answers},
        )
        assert resp.status_code == 422

    def test_resubmit_conflict(
        self, public, admin_user, application, db: Session
    ):
        """재제출 불가 — 다시 받으려면 재발송이다."""
        _session(db, application, admin_user)
        with patch("app.api.aptitude.generate_aptitude_summary_bg"):
            first = public.post(
                "/api/v1/public/aptitude/apt-tok-test/submit",
                json={"answers": _full_answers()},
            )
            assert first.status_code == 200
            second = public.post(
                "/api/v1/public/aptitude/apt-tok-test/submit",
                json={"answers": _full_answers()},
            )
        assert second.status_code == 409

    def test_expired_submit_gone(
        self, public, admin_user, application, db: Session
    ):
        _session(
            db,
            application,
            admin_user,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        resp = public.post(
            "/api/v1/public/aptitude/apt-tok-test/submit",
            json={"answers": _full_answers()},
        )
        assert resp.status_code == 410


# ── 담당자 조회 ────────────────────────────────────────────────────


class TestDetail:
    def test_none_when_never_sent(self, as_user, admin_user, application):
        client = as_user(admin_user)
        body = client.get(f"/api/v1/applications/{application.id}/aptitude").json()
        assert body["status"] == "none"
        assert body["answers"] == []
        assert body["stats"] == []

    def test_done_returns_answers_stats_summary(
        self, as_user, public, admin_user, application, db: Session
    ):
        session = _session(db, application, admin_user)
        with patch("app.api.aptitude.generate_aptitude_summary_bg"):
            public.post(
                "/api/v1/public/aptitude/apt-tok-test/submit",
                json={"answers": _full_answers(value=5)},
            )
        session.ai_summary = "전 문항에 5점으로 응답했습니다."
        session.ai_summary_model = "test:model aptitude_summary.v1"
        db.flush()

        client = as_user(admin_user)
        body = client.get(f"/api/v1/applications/{application.id}/aptitude").json()
        assert body["status"] == "done"
        assert len(body["answers"]) == len(QUESTIONS)
        assert body["ai_summary"] == "전 문항에 5점으로 응답했습니다."
        # 통계는 코드 계산 — 전부 5점이면 카테고리 평균도 전부 5.0
        assert body["stats"], "통계가 비어 있으면 안 된다"
        for stat in body["stats"]:
            assert stat["mean"] == 5.0

    def test_latest_session_wins(
        self, as_user, admin_user, application, db: Session
    ):
        """재발송 후에는 최신 세션 기준으로 보여 준다."""
        _session(
            db,
            application,
            admin_user,
            token="apt-old",
            status="expired",
            created_at=datetime.now(UTC) - timedelta(days=10),
        )
        _session(db, application, admin_user, token="apt-new")
        client = as_user(admin_user)
        body = client.get(f"/api/v1/applications/{application.id}/aptitude").json()
        assert body["status"] == "pending"
        assert "apt-new" in body["url"]


# ── 통계 계산 ──────────────────────────────────────────────────────


class TestStats:
    def test_category_means(self, db: Session, admin_user, application):
        from app.agent.aptitude import compute_stats

        session = _session(db, application, admin_user)
        # 협업 2문항에 2·4 → 평균 3.0, 나머지는 5
        values = {"collab_help": 2, "collab_feedback": 4}
        for q in QUESTIONS:
            db.add(
                AptitudeAnswer(
                    session_id=session.id,
                    question_key=q["key"],
                    question_text=q["text"],
                    value=values.get(q["key"], 5),
                )
            )
        db.flush()
        db.refresh(session)

        stats = {s["category"]: s for s in compute_stats(list(session.answers))}
        assert stats["collaboration"]["mean"] == 3.0
        assert stats["collaboration"]["count"] == 2
        assert stats["growth"]["mean"] == 5.0
