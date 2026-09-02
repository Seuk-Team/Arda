"""AI 면접 API (ADR-0026) — 세션 생성과 지원자 공개 접근.

이 기능은 **틀렸을 때 지원자의 목소리를 동의 없이 녹음한다.** 그래서 규칙 하나에
테스트 하나를 붙인다. 특히 아래 둘은 코드가 무너지면 바로 사고다:

- 동의(`consented_at`) 없이는 시작할 수 없다 — 지원 폼의 개인정보 동의와 별개다
- 공개 라우트가 담당자 정보·다른 지원자를 내려주지 않는다

만료는 스케줄러가 아니라 **조회 시점 판정**이라(일정 제안·B4 와 같은 방식) 그것도 본다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import Application, InterviewSession, InterviewTurn, User


@pytest.fixture()
def as_user(db: Session):
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


def _session(db: Session, application: Application, admin_user: User, **kw) -> InterviewSession:
    row = InterviewSession(
        application_id=application.id,
        token=kw.pop("token", "tok-test"),
        status=kw.pop("status", "pending"),
        expires_at=kw.pop("expires_at", datetime.now(UTC) + timedelta(days=7)),
        created_by=admin_user.id,
        **kw,
    )
    db.add(row)
    db.flush()
    return row


def _question(db: Session, session: InterviewSession, seq: int = 1) -> InterviewTurn:
    turn = InterviewTurn(session_id=session.id, seq=seq, question="자기소개 부탁드립니다")
    db.add(turn)
    db.flush()
    return turn


class TestCreate:
    def test_세션을_만들면_토큰과_링크가_함께_온다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        res = as_user(admin_user).post(
            f"/api/v1/applications/{application.id}/interview-sessions", json={}
        )
        assert res.status_code == 201
        body = res.json()
        assert body["status"] == "pending"
        assert len(body["token"]) >= 20  # token_urlsafe(16) = 128비트
        # 링크를 화면이 조립하지 않는다 — 서버가 준다
        assert body["token"] in body["url"]
        assert body["consented_at"] is None

    def test_없는_지원자면_404(self, as_user, admin_user: User):
        res = as_user(admin_user).post(
            "/api/v1/applications/999999/interview-sessions", json={}
        )
        assert res.status_code == 404

    def test_다시_만들어도_이전_세션이_죽지_않는다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """공고 public-link 와 다른 점이다 — 거기는 재발급이라 옛 토큰이 무효가 된다.

        면접은 이력이 남는 편이 낫다(stage_history 와 같은 철학).
        """
        client = as_user(admin_user)
        first = client.post(
            f"/api/v1/applications/{application.id}/interview-sessions", json={}
        ).json()
        second = client.post(
            f"/api/v1/applications/{application.id}/interview-sessions", json={}
        ).json()

        assert first["token"] != second["token"]
        rows = db.scalars(
            select(InterviewSession).where(
                InterviewSession.application_id == application.id
            )
        ).all()
        assert len(rows) == 2
        assert all(r.status == "pending" for r in rows)


class TestConsentGate:
    """녹음 동의는 지원 폼의 개인정보 동의와 **별개다**. 없으면 시작하지 않는다."""

    def test_동의_없이_시작하면_422(
        self, public, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        _question(db, s)
        db.commit()

        res = public.post("/api/v1/public/interview/tok-test/start")
        assert res.status_code == 422
        db.refresh(s)
        assert s.status == "pending"  # 시작되지 않았다
        assert s.started_at is None

    def test_동의를_거절하면_422_이고_기록도_안_남는다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        db.commit()

        res = public.post(
            "/api/v1/public/interview/tok-test/consent", json={"agreed": False}
        )
        assert res.status_code == 422
        db.refresh(s)
        assert s.consented_at is None

    def test_동의하면_시작할_수_있다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        _question(db, s)
        db.commit()

        assert (
            public.post(
                "/api/v1/public/interview/tok-test/consent", json={"agreed": True}
            ).status_code
            == 200
        )
        res = public.post("/api/v1/public/interview/tok-test/start")
        assert res.status_code == 200
        assert res.json()["status"] == "in_progress"

        db.refresh(s)
        assert s.consented_at is not None
        assert s.started_at is not None

    def test_질문이_없으면_시작하지_않는다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        """빈 면접을 여는 것보다 낫다. 질문 자동 생성은 설계 §5 의 5번이다."""
        s = _session(db, application, admin_user, consented_at=datetime.now(UTC))
        db.commit()

        res = public.post("/api/v1/public/interview/tok-test/start")
        assert res.status_code == 422
        db.refresh(s)
        assert s.status == "pending"


class TestPublicView:
    def test_없는_토큰은_404(self, public):
        assert public.get("/api/v1/public/interview/없는토큰").status_code == 404

    def test_담당자_정보를_내려주지_않는다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        """지원자에게 필요한 건 자기 면접 상태뿐이다."""
        s = _session(db, application, admin_user)
        db.commit()

        body = public.get("/api/v1/public/interview/tok-test").json()
        assert body["applicant_name"] == application.name
        assert "token" not in body  # 이미 가진 사람만 본다
        assert "url" not in body
        assert "created_by" not in body
        assert body["consent_required"] is True

    def test_진행_중이면_현재_질문이_온다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        _question(db, s, seq=1)
        db.commit()

        body = public.get("/api/v1/public/interview/tok-test").json()
        assert body["current_question"] == "자기소개 부탁드립니다"
        assert body["question_seq"] == 1

    def test_답한_질문은_현재_질문이_아니다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        turn = _question(db, s, seq=1)
        turn.transcript = "안녕하세요, 백엔드 개발자입니다"
        db.commit()

        body = public.get("/api/v1/public/interview/tok-test").json()
        assert body["current_question"] is None


class TestExpiry:
    """스케줄러 없이 조회 시점에 판정한다 — B4 마감·일정 제안과 같은 방식."""

    def test_기한이_지나면_조회_시점에_expired_가_된다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        s = _session(
            db,
            application,
            admin_user,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        db.commit()

        # 빈 화면보다 낫다 — 만료도 200 으로 내려준다
        body = public.get("/api/v1/public/interview/tok-test").json()
        assert body["status"] == "expired"

        db.refresh(s)
        assert s.status == "expired"

    def test_만료된_링크로는_시작할_수_없다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        s = _session(
            db,
            application,
            admin_user,
            consented_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        _question(db, s)
        db.commit()

        assert public.post("/api/v1/public/interview/tok-test/start").status_code == 410


class TestQuestions:
    def test_질문을_넣으면_순서대로_저장된다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        db.commit()

        res = as_user(admin_user).put(
            f"/api/v1/interview-sessions/{s.id}/questions",
            json={"questions": ["자기소개", "가장 어려웠던 문제", "왜 우리 회사인가"]},
        )
        assert res.status_code == 200
        turns = res.json()["turns"]
        assert [t["seq"] for t in turns] == [1, 2, 3]
        assert turns[1]["question"] == "가장 어려웠던 문제"

    def test_시작한_뒤에는_질문을_못_바꾼다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """진행 중에 바뀌면 지원자가 본 질문과 저장된 질문이 어긋난다."""
        s = _session(db, application, admin_user, status="in_progress")
        _question(db, s)
        db.commit()

        res = as_user(admin_user).put(
            f"/api/v1/interview-sessions/{s.id}/questions",
            json={"questions": ["바꾼 질문"]},
        )
        assert res.status_code == 409

    def test_빈_목록은_422(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        db.commit()
        res = as_user(admin_user).put(
            f"/api/v1/interview-sessions/{s.id}/questions", json={"questions": []}
        )
        assert res.status_code == 422


class TestAnswer:
    @pytest.fixture()
    def running(self, db: Session, application: Application, admin_user: User):
        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        for i, q in enumerate(["질문1", "질문2", "질문3"], start=1):
            db.add(InterviewTurn(session_id=s.id, seq=i, question=q))
        db.commit()
        return s

    def test_답하면_다음_질문으로_넘어간다(self, public, db: Session, running):
        assert public.get("/api/v1/public/interview/tok-test").json()["question_seq"] == 1

        res = public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "안녕하세요"}
        )
        assert res.status_code == 200
        assert res.json()["question_seq"] == 2
        assert res.json()["current_question"] == "질문2"

    def test_답_안_한_가장_앞_질문에_붙는다(self, public, db: Session, running):
        """마지막 질문을 보면 안 된다 — 3개 중 1번만 답했을 때 3번을 내주게 된다."""
        public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "첫 답"}
        )
        turns = db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == running.id)
            .order_by(InterviewTurn.seq)
        ).all()
        assert turns[0].transcript == "첫 답"
        assert turns[1].transcript is None
        assert turns[2].transcript is None

    def test_다_답하면_현재_질문이_없다(self, public, db: Session, running):
        for t in ["1", "2", "3"]:
            public.post(
                "/api/v1/public/interview/tok-test/answer", json={"transcript": t}
            )
        body = public.get("/api/v1/public/interview/tok-test").json()
        assert body["current_question"] is None

        # 더 답하려 하면 409 — 종료하라고 알려 준다
        res = public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "4"}
        )
        assert res.status_code == 409

    def test_시작_전에는_답할_수_없다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        _question(db, s)
        db.commit()
        res = public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "미리"}
        )
        assert res.status_code == 409


class TestFinish:
    def test_다_안_답해도_끝낼_수_있다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        """중간에 그만두는 것도 지원자의 선택이다. 막으면 in_progress 로 영영 남는다."""
        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        _question(db, s)
        db.commit()

        res = public.post("/api/v1/public/interview/tok-test/finish")
        assert res.status_code == 200
        assert res.json()["status"] == "done"

        db.refresh(s)
        assert s.ended_at is not None

    def test_두_번_눌러도_같은_결과(
        self, public, db: Session, application: Application, admin_user: User
    ):
        """새로고침으로 500 을 만들지 않는다."""
        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        db.commit()

        assert public.post("/api/v1/public/interview/tok-test/finish").status_code == 200
        assert public.post("/api/v1/public/interview/tok-test/finish").status_code == 200
