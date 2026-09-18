"""AI 면접 API (ADR-0026) — 세션 생성과 지원자 공개 접근.

이 기능은 **틀렸을 때 지원자의 목소리를 동의 없이 녹음한다.** 그래서 규칙 하나에
테스트 하나를 붙인다. 특히 아래 둘은 코드가 무너지면 바로 사고다:

- 동의(`consented_at`) 없이는 시작할 수 없다 — 지원 폼의 개인정보 동의와 별개다
- 공개 라우트가 담당자 정보·다른 지원자를 내려주지 않는다

만료는 스케줄러가 아니라 **조회 시점 판정**이라(일정 제안·B4 와 같은 방식) 그것도 본다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

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


class TestLinkMail:
    """링크를 만들면 지원자에게 메일로 나간다 (2026-09-18, 팀 논의).

    전에는 담당자가 「링크 복사」로 손수 전달했다 — 인적성 설문은 자동으로 나가는데
    면접만 손으로 나가고 있었다.
    """

    def _logs(self, db: Session, application: Application):
        from app.models import EmailLog

        return db.scalars(
            select(EmailLog)
            .where(EmailLog.application_id == application.id)
            .order_by(EmailLog.id)
        ).all()

    def test_만들면_링크_메일이_쌓인다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        with patch("app.shared.mail.publish") as pub:
            body = as_user(admin_user).post(
                f"/api/v1/applications/{application.id}/interview-sessions", json={}
            ).json()

        logs = self._logs(db, application)
        assert len(logs) == 1
        log = logs[0]
        assert log.to_email == application.email
        assert log.status == "queued" and log.stage == "custom"
        assert body["token"] in log.body, "링크가 본문에 없다"
        assert "AI 면접" in log.subject
        pub.assert_called_once_with(log.id)

    def test_회사명은_DB_값을_쓴다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """#323 이 설문·수동 메일에서 고친 자리 — 면접 링크 메일은 그 뒤에 들어와 빠져 있었다.
        환경변수를 바로 읽으면 같은 지원자에게 단계 메일과 회사명이 갈린다."""
        from app.hiring.company import get_profile

        get_profile(db).name = "코드브릿지"
        db.flush()

        with patch("app.shared.mail.publish"):
            as_user(admin_user).post(
                f"/api/v1/applications/{application.id}/interview-sessions", json={}
            )

        log = self._logs(db, application)[0]
        assert log.subject.startswith("[코드브릿지] ")
        assert "코드브릿지 " in log.body
        assert "Arda" not in log.subject + log.body  # 시험의 환경변수 값

    def test_앱_안내가_함께_간다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """수택님 지적 — 웹으로 들어가는 길과 앱으로 들어가는 길을 둘 다 적는다."""
        with patch("app.shared.mail.publish"):
            as_user(admin_user).post(
                f"/api/v1/applications/{application.id}/interview-sessions", json={}
            )

        body = self._logs(db, application)[0].body
        assert "생년월일" in body and "앱" in body

    def test_notify_false_면_안_보낸다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """링크만 뽑아 두고 나중에 보내는 자리."""
        with patch("app.shared.mail.publish") as pub:
            res = as_user(admin_user).post(
                f"/api/v1/applications/{application.id}/interview-sessions",
                json={"notify": False},
            )

        assert res.status_code == 201
        assert self._logs(db, application) == []
        pub.assert_not_called()

    def test_다시_보내도_같은_링크다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """재발송마다 새 세션을 만들면 앱은 가장 먼저 만든 방으로 들어가 담당자와 갈린다."""
        client = as_user(admin_user)
        with patch("app.shared.mail.publish"):
            first = client.post(
                f"/api/v1/applications/{application.id}/interview-sessions", json={}
            ).json()
            res = client.post(f"/api/v1/interview-sessions/{first['id']}/send")

        assert res.status_code == 201
        assert res.json()["token"] == first["token"]
        logs = self._logs(db, application)
        assert len(logs) == 2
        assert all(first["token"] in log.body for log in logs)
        assert (
            db.scalars(
                select(InterviewSession).where(
                    InterviewSession.application_id == application.id
                )
            ).all().__len__()
            == 1
        ), "재발송이 세션을 새로 만들면 안 된다"

    def test_끝난_면접은_다시_안_보낸다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user, token="tok-done", status="done")
        db.commit()

        res = as_user(admin_user).post(f"/api/v1/interview-sessions/{s.id}/send")
        assert res.status_code == 409

    def test_만료된_링크는_다시_안_보낸다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        s = _session(
            db, application, admin_user, token="tok-old",
            expires_at=datetime.now(UTC) - timedelta(days=1),
        )
        db.commit()

        res = as_user(admin_user).post(f"/api/v1/interview-sessions/{s.id}/send")
        assert res.status_code == 410

    def test_메일이_안_나가도_면접은_만들어진다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """발행 실패는 로그만 — 행은 queued 로 남아 나중에 쓸어 담긴다(mail_smtp)."""
        with patch("app.shared.mail.publish", side_effect=RuntimeError("n8n 죽음")):
            res = as_user(admin_user).post(
                f"/api/v1/applications/{application.id}/interview-sessions", json={}
            )

        assert res.status_code == 201
        assert self._logs(db, application)[0].status == "queued"


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
        _session(db, application, admin_user)
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

    def test_텍스트와_음성을_같이_보내면_422(self, public, running):
        """어느 쪽이 진짜 답인지 서버가 고르게 두지 않는다."""
        res = public.post(
            "/api/v1/public/interview/tok-test/answer",
            json={"transcript": "네", "audio_s3_key": _AUDIO_KEY},
        )
        assert res.status_code == 422

    def test_둘_다_안_보내면_422(self, public, running):
        res = public.post("/api/v1/public/interview/tok-test/answer", json={})
        assert res.status_code == 422

    def test_짧게_답하면_진행_보조가_같이_온다(self, public, db: Session, running):
        """ADR-0026 결정 4 — 판정이 아니라 다음에 할 행동 한 문장."""
        res = public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "네"}
        )
        assert res.status_code == 200
        pacing = res.json()["pacing"]
        assert pacing["action"] == "follow_up"
        assert pacing["message"]

    def test_충분히_답하면_진행_보조가_없다(self, public, db: Session, running):
        res = public.post(
            "/api/v1/public/interview/tok-test/answer",
            json={"transcript": "결제 정산 API 를 맡아 응답 시간을 절반으로 줄였습니다"},
        )
        assert res.json()["pacing"] is None

    def test_진행_보조는_저장되지_않는다(self, public, db: Session, running):
        """평가로 새는 길을 아예 안 만든다 — 답변 응답에만 실리고 끝이다."""
        public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "네"}
        )
        # 다시 조회하면 없다. 새로고침할 때마다 같은 말을 반복하지 않는다.
        assert public.get("/api/v1/public/interview/tok-test").json()["pacing"] is None

        turn = db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == running.id)
            .order_by(InterviewTurn.seq)
        ).first()
        # 저장된 것은 전사뿐 — 신호를 적어 두는 칸이 없다
        assert turn.transcript == "네"

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

    def test_번호를_주면_그_칸에_넣는다(self, public, db: Session, running):
        """워커가 전사를 뒤에서 돌리면 도착 순서가 어긋난다 — 그때 3번 답이
        1번 칸에 들어가면 담당자가 엉뚱한 대조를 한다."""
        public.post(
            "/api/v1/public/interview/tok-test/answer",
            json={"transcript": "셋째 답", "seq": 3},
        )
        turns = db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == running.id)
            .order_by(InterviewTurn.seq)
        ).all()
        assert turns[0].transcript is None
        assert turns[2].transcript == "셋째 답"

    def test_이미_답한_번호면_409(self, public, running):
        """같은 답이 두 번 도착해도 앞의 것을 덮어쓰지 않는다."""
        public.post(
            "/api/v1/public/interview/tok-test/answer",
            json={"transcript": "첫 답", "seq": 1},
        )
        again = public.post(
            "/api/v1/public/interview/tok-test/answer",
            json={"transcript": "다시", "seq": 1},
        )
        assert again.status_code == 409

    def test_번호를_안_주면_지금까지와_같다(self, public, db: Session, running):
        """워커 말고도 부르는 곳이 있다 — 기본값이 바뀌면 그쪽이 깨진다."""
        public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "첫 답"}
        )
        turns = db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == running.id)
            .order_by(InterviewTurn.seq)
        ).all()
        assert turns[0].transcript == "첫 답"

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

    def test_대조를_뒤에서_돌린다(
        self, public, db: Session, application: Application, admin_user: User, monkeypatch
    ):
        """**여기서 sLLM 을 기다리지 않는다.** 끝내기 요청이 몇십 초 멈추면 지원자는
        이미 다 답했는데 화면만 붙잡힌다 (설계 §5-6)."""
        import app.agent.interview_findings as fnd

        called = []
        monkeypatch.setattr(fnd, "generate_findings_bg", called.append)

        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        _question(db, s)
        db.commit()

        assert public.post("/api/v1/public/interview/tok-test/finish").status_code == 200
        assert called == [s.id]

    def test_두_번_눌러도_같은_결과(
        self, public, db: Session, application: Application, admin_user: User
    ):
        """새로고침으로 500 을 만들지 않는다."""
        _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        db.commit()

        assert public.post("/api/v1/public/interview/tok-test/finish").status_code == 200
        assert public.post("/api/v1/public/interview/tok-test/finish").status_code == 200


# 발급 경로가 만드는 모양. 테스트에서 손으로 적을 일이 많아 상수로 둔다.
_AUDIO_KEY = "interviews/11111111-2222-3333-4444-555555555555/answer.webm"


def _stt_result(text: str = "결제 정산 API 를 맡아 응답 시간을 절반으로 줄였습니다"):
    """`app.agent.stt.transcribe` 의 반환 계약 그대로."""
    return {
        "raw": text,
        "resolved": text + " (해석됨)",
        "duration_ms": 900,
        "audio_duration_sec": 12.5,
        "cost_usd": 0.00125,
    }


class TestAnswerAudio:
    """음성 답변 → 전사 (설계 §5-4).

    **오디오를 실제로 전사하지 않는다.** `stt.transcribe` 를 mock 한다 — 테스트가
    외부 API 를 부르면 CI 에서 돈이 나가고 키가 없으면 무작위로 깨진다.
    """

    @pytest.fixture()
    def running(self, db: Session, application: Application, admin_user: User):
        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        db.add(InterviewTurn(session_id=s.id, seq=1, question="질문1"))
        db.commit()
        return s

    def test_음성을_주면_전사해서_길이와_비용까지_적는다(
        self, public, db: Session, running
    ):
        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", return_value=_stt_result()) as mock_stt,
        ):
            res = public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={"audio_s3_key": _AUDIO_KEY},
            )

        assert res.status_code == 200
        mock_stt.assert_called_once()

        turn = db.scalars(
            select(InterviewTurn).where(InterviewTurn.session_id == running.id)
        ).first()
        db.refresh(turn)
        assert turn.transcript.startswith("결제 정산 API")
        assert float(turn.audio_duration_sec) == 12.5
        assert float(turn.stt_cost_usd) == 0.00125
        assert turn.audio_s3_key == _AUDIO_KEY

    def test_다듬은_문장이_아니라_원문을_저장한다(self, public, db: Session, running):
        """대조에서 **원문으로 인용**되는 자리다 (ADR-0026 결정 3)."""
        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", return_value=_stt_result()),
        ):
            public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={"audio_s3_key": _AUDIO_KEY},
            )

        turn = db.scalars(
            select(InterviewTurn).where(InterviewTurn.session_id == running.id)
        ).first()
        db.refresh(turn)
        assert "(해석됨)" not in turn.transcript

    def test_말이_느리면_진행_보조가_질문을_바꾸자고_한다(self, public, running):
        """`audio_duration_sec` 이 진행 보조까지 실제로 전달되는지 (배선 확인)."""
        slow = _stt_result()
        slow["audio_duration_sec"] = 40.0  # 같은 문장을 40초에 = 아주 느리다

        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", return_value=slow),
        ):
            res = public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={"audio_s3_key": _AUDIO_KEY},
            )

        assert res.json()["pacing"]["action"] == "rephrase"

    def test_보통_속도면_진행_보조가_없다(self, public, running):
        """24자를 12.5초 = 1.9자/초. 중간에 한두 번 생각하며 말한 평범한 답변이다."""
        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", return_value=_stt_result()),
        ):
            res = public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={"audio_s3_key": _AUDIO_KEY},
            )
        assert res.json()["pacing"] is None

    def test_남의_이력서_키는_거절한다(self, public, db: Session, running):
        """서버가 S3 를 대신 읽어 주는 경로다 — 키를 믿으면 그대로 유출이다."""
        with patch("app.shared.s3.read_object") as mock_read:
            res = public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={
                    "audio_s3_key": "applications/"
                    "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/resume.pdf"
                },
            )
        assert res.status_code == 422
        mock_read.assert_not_called()  # 읽어 보지도 않는다

    def test_전사에_실패하면_아무것도_저장하지_않는다(
        self, public, db: Session, running
    ):
        """반쯤 저장하면 답을 못 한 채로 다음 질문으로 넘어간다."""
        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", side_effect=RuntimeError("STT 죽음")),
        ):
            res = public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={"audio_s3_key": _AUDIO_KEY},
            )

        assert res.status_code == 502
        turn = db.scalars(
            select(InterviewTurn).where(InterviewTurn.session_id == running.id)
        ).first()
        db.refresh(turn)
        assert turn.transcript is None
        assert turn.audio_duration_sec is None
        # 같은 질문이 그대로 보여야 다시 답할 수 있다
        assert public.get("/api/v1/public/interview/tok-test").json()["question_seq"] == 1

    def test_말이_안_담긴_녹음은_422(self, public, db: Session, running):
        """빈 문자열을 넣으면 '답한 질문'이 되어 다음으로 넘어간다."""
        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", return_value=_stt_result("   ")),
        ):
            res = public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={"audio_s3_key": _AUDIO_KEY},
            )
        assert res.status_code == 422


class TestAnalyze:
    """녹화 진위 분석 (ADR-0029).

    **설정이 없으면 꺼져 있어야 한다** — ADR-0029 결정 5 가 "①②③ 이 정해지기
    전에는 운영에 붙이지 않는다"고 정했다. 그 방어가 여기서 깨지면 환경변수
    하나 없이도 운영에서 켜진다.
    """

    @pytest.fixture()
    def turn(self, db: Session, application: Application, admin_user: User):
        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        t = InterviewTurn(
            session_id=s.id, seq=1, question="질문1", audio_s3_key=_AUDIO_KEY
        )
        db.add(t)
        db.commit()
        return t

    def test_설정이_없으면_503(self, as_user, admin_user: User, turn):
        with patch("app.interview.lie_analysis.SERVICE_URL", ""):
            res = as_user(admin_user).post(f"/api/v1/interview-turns/{turn.id}/analyze")
        assert res.status_code == 503

    def test_녹화가_없는_회차는_409(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user, status="in_progress")
        t = InterviewTurn(session_id=s.id, seq=1, question="질문1")  # 녹화 없음
        db.add(t)
        db.commit()

        with patch("app.interview.lie_analysis.SERVICE_URL", "http://lie.invalid"):
            res = as_user(admin_user).post(f"/api/v1/interview-turns/{t.id}/analyze")
        assert res.status_code == 409

    def test_없는_회차는_404(self, as_user, admin_user: User):
        with patch("app.interview.lie_analysis.SERVICE_URL", "http://lie.invalid"):
            res = as_user(admin_user).post("/api/v1/interview-turns/99999999/analyze")
        assert res.status_code == 404

    def test_결과를_그대로_돌려주고_저장하지_않는다(
        self, as_user, db: Session, admin_user: User, turn
    ):
        """담을 표를 아직 안 정했다 — 값이 먼저 쌓이면 근거처럼 쓰이기 시작한다."""
        result = {"pred": 0, "truth_pct": 100.0, "lie_pct": 0.0, "observations": []}
        with (
            patch("app.interview.lie_analysis.SERVICE_URL", "http://lie.invalid"),
            patch("app.shared.s3.read_object", return_value=b"fake-video"),
            patch("app.interview.lie_analysis.analyze", return_value=result) as mock_analyze,
        ):
            res = as_user(admin_user).post(f"/api/v1/interview-turns/{turn.id}/analyze")

        assert res.status_code == 200
        assert res.json() == result
        mock_analyze.assert_called_once()

        # 회차에는 아무것도 안 붙었다 — 저장 칸 자체가 없다
        db.refresh(turn)
        assert not hasattr(turn, "lie_pct")

    def test_분석이_죽으면_502(self, as_user, admin_user: User, turn):
        with (
            patch("app.interview.lie_analysis.SERVICE_URL", "http://lie.invalid"),
            patch("app.shared.s3.read_object", return_value=b"fake-video"),
            patch("app.interview.lie_analysis.analyze", side_effect=RuntimeError("서비스 죽음")),
        ):
            res = as_user(admin_user).post(f"/api/v1/interview-turns/{turn.id}/analyze")
        assert res.status_code == 502


class TestAudioUploadUrl:
    """답변 음성 업로드 URL — 이력서 경로와 나눠 뒀다."""

    @pytest.fixture()
    def running(self, db: Session, application: Application, admin_user: User):
        s = _session(
            db,
            application,
            admin_user,
            status="in_progress",
            consented_at=datetime.now(UTC),
        )
        db.commit()
        return s

    def test_음성_형식이면_발급된다(self, public, running):
        with patch("app.shared.s3.presign_put", return_value="https://s3.example/put"):
            res = public.post(
                "/api/v1/public/interview/tok-test/audio-upload-url",
                json={
                    "filename": "answer.webm",
                    "content_type": "audio/webm;codecs=opus",
                    "size_bytes": 500_000,
                },
            )
        assert res.status_code == 200
        # 키는 서버가 만든다 — 클라이언트가 경로를 고르면 임의 위치 쓰기가 된다
        assert res.json()["s3_key"].startswith("interviews/")
        assert res.json()["s3_key"].endswith("/answer.webm")

    def test_이력서_형식은_거절한다(self, public, running):
        """음성 목록에 pdf 를 얹지 않았다 — 쓰이는 곳이 다르면 목록도 따로다."""
        res = public.post(
            "/api/v1/public/interview/tok-test/audio-upload-url",
            json={
                "filename": "resume.pdf",
                "content_type": "application/pdf",
                "size_bytes": 500_000,
            },
        )
        assert res.status_code == 422

    def test_시작_전에는_발급하지_않는다(
        self, public, db: Session, application: Application, admin_user: User
    ):
        _session(db, application, admin_user, status="pending")
        db.commit()
        res = public.post(
            "/api/v1/public/interview/tok-test/audio-upload-url",
            json={
                "filename": "answer.webm",
                "content_type": "audio/webm",
                "size_bytes": 100,
            },
        )
        assert res.status_code == 409


class TestActiveSessions:
    """대시보드가 **한 번에** 실시간 분석으로 들어가기 위한 목록.

    이게 없으면 담당자는 지원자 목록 → 상세 → 세션 → 링크 넷을 거쳐야 한다.
    면접이 시작되는 순간에 그걸 찾아 들어갈 수는 없다 (2026-09-09 실측).
    """

    def test_진행_중인_것만_온다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        going = _session(db, application, admin_user, token="a", status="in_progress")
        # 안 시작한 것은 지금 볼 게 없고, 끝난 것은 들어가도 방이 안 열린다
        _session(db, application, admin_user, token="b", status="pending")
        _session(db, application, admin_user, token="c", status="done")
        _session(db, application, admin_user, token="d", status="expired")
        db.commit()

        rows = as_user(admin_user).get("/api/v1/interview-sessions/active").json()

        assert [r["id"] for r in rows] == [going.id]

    def test_누구의_어느_면접인지_같이_온다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """세션 번호만 있으면 담당자가 고를 수 없다 — 화면이 지원서·공고를
        따로 더 부르게 하지 않는다."""
        _session(db, application, admin_user, token="a", status="in_progress")
        db.commit()

        row = as_user(admin_user).get("/api/v1/interview-sessions/active").json()[0]

        assert row["applicant_name"] == application.name
        assert row["posting_title"]
        assert row["application_id"] == application.id

    def test_없으면_빈_목록이다(self, as_user, db: Session, admin_user: User):
        got = as_user(admin_user).get("/api/v1/interview-sessions/active")
        assert got.json() == []

    def test_로그인이_없으면_거절한다(self, public):
        assert public.get("/api/v1/interview-sessions/active").status_code == 401

    def test_active_가_세션_번호로_읽히지_않는다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        """경로 순서가 뒤집히면 `active` 를 id 로 읽어 422 가 난다.

        상세 라우트(`/interview-sessions/{id}`)보다 **위에** 있어야 한다.
        """
        r = as_user(admin_user).get("/api/v1/interview-sessions/active")

        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestAnsweredBeforeTranscript:
    """'답했다' 와 '받아썼다' 를 나눈다 (0018, 2026-09-11).

    **시연에서 겪은 것**: Q1~Q8 을 답했는데 Q9 에서 Q1 로 돌아갔고, 그 뒤 어떤 답도
    저장되지 않았다. 전사는 워커가 뒤에서 한 번에 하나씩(최대 180초) 돌리는데,
    "지금 질문" 을 `transcript IS NULL` 로 정하면 그 사이 재접속이 **아직 전사가 안
    끝난 가장 앞 질문** 으로 되돌렸고, 다시 한 답은 원래 답과 부딪혀 409 로 버려졌다.
    """

    SVC = {"X-Service-Token": "svc-test"}

    @pytest.fixture()
    def running(self, db: Session, application: Application, admin_user: User, monkeypatch):
        monkeypatch.setenv("ARDA_SERVICE_TOKEN", "svc-test")
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

    def _mark(self, public, seq: int):
        r = public.post(
            f"/api/v1/internal/interview/tok-test/turns/{seq}/answered", headers=self.SVC
        )
        assert r.status_code == 200

    def _turn(self, db: Session, s: InterviewSession, seq: int) -> InterviewTurn:
        db.expire_all()
        return db.scalar(
            select(InterviewTurn).where(InterviewTurn.session_id == s.id, InterviewTurn.seq == seq)
        )

    def test_전사가_밀려도_이미_답한_질문으로_되돌아가지_않는다(self, public, running):
        """이 시험이 이 변경의 전부다. 1·2번을 답했는데 전사는 아직 하나도 안 왔다 —
        재접속한 워커·앱이 보는 '지금 질문' 은 1번이 아니라 3번이어야 한다."""
        self._mark(public, 1)
        self._mark(public, 2)
        state = public.get("/api/v1/public/interview/tok-test").json()
        assert state["question_seq"] == 3
        assert state["current_question"] == "질문3"

    def test_늦게_온_전사는_답한_칸에_들어간다(self, public, db, running):
        """답한 칸이라고 409 로 막으면 전사가 영영 안 들어간다."""
        self._mark(public, 1)
        res = public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "늦은 전사", "seq": 1}
        )
        assert res.status_code == 200
        assert self._turn(db, running, 1).transcript == "늦은 전사"

    def test_번호_없는_답은_답한_칸을_건너뛴다(self, public, db, running):
        """글로 답하기처럼 번호 없이 오는 답은 '지금 질문' 에 들어가야 한다 —
        전사를 기다리는 1번 칸을 가로채면 안 된다."""
        self._mark(public, 1)
        res = public.post("/api/v1/public/interview/tok-test/answer", json={"transcript": "글 답"})
        assert res.status_code == 200
        assert self._turn(db, running, 1).transcript is None
        assert self._turn(db, running, 2).transcript == "글 답"

    def test_워커를_안_거친_답도_답한_것이_된다(self, public, db, running):
        public.post("/api/v1/public/interview/tok-test/answer", json={"transcript": "네"})
        assert self._turn(db, running, 1).answered_at is not None
        assert public.get("/api/v1/public/interview/tok-test").json()["question_seq"] == 2

    def test_전사가_비어도_되돌아가지_않는다(self, public, running):
        """전사가 빈 결과면 워커는 저장을 안 한다 — 예전에는 그 칸이 영원히 '지금
        질문' 이라 지원자가 거기로 계속 돌아갔다. 답한 것은 답한 것이다."""
        self._mark(public, 1)            # 말은 했는데 전사는 끝내 안 온다
        assert public.get("/api/v1/public/interview/tok-test").json()["question_seq"] == 2


class TestLateTranscript:
    """[면접 종료] 뒤에 늦게 온 전사도 받는다 (2026-09-11).

    워커 받아쓰기는 CPU 한 대에서 줄을 서 몇 분씩 늦는다. 세션 59 에서 지원자가
    먼저 끝내자 3초 뒤 온 전사가 409 로 버려졌다(수택님 로그). 새 답이 아니라
    **이미 한 답의 글이 늦게 온 것**이라 받는다 — 조건을 좁혀서.
    """

    @pytest.fixture()
    def ended(self, db: Session, application: Application, admin_user: User):
        now = datetime.now(UTC)
        s = _session(
            db, application, admin_user,
            status="done", consented_at=now, started_at=now, ended_at=now,
        )
        db.add(InterviewTurn(session_id=s.id, seq=1, question="질문1", answered_at=now))
        db.add(InterviewTurn(session_id=s.id, seq=2, question="질문2"))   # 답 안 한 칸
        db.commit()
        return s

    def _turn(self, db: Session, s: InterviewSession, seq: int) -> InterviewTurn:
        db.expire_all()
        return db.scalar(
            select(InterviewTurn).where(InterviewTurn.session_id == s.id, InterviewTurn.seq == seq)
        )

    def test_답한_칸의_늦은_전사는_받고_다시_채점한다(self, public, db, ended):
        with patch("app.interview.scoring.score_interview_bg") as rescore, patch(
            "app.interview.api.interviews._generate_followup_bg"
        ) as followup:
            res = public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={"transcript": "늦게 온 글", "seq": 1},
            )
        assert res.status_code == 200
        assert self._turn(db, ended, 1).transcript == "늦게 온 글"
        rescore.assert_called_once_with(ended.id)
        followup.assert_not_called()   # 끝난 면접에 꼬리질문을 붙이지 않는다

    def test_답하지_않은_칸은_끝난_뒤에_채우지_못한다(self, public, db, ended):
        res = public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "새 답", "seq": 2}
        )
        assert res.status_code == 409
        assert self._turn(db, ended, 2).transcript is None

    def test_번호가_없으면_받지_않는다(self, public, ended):
        res = public.post("/api/v1/public/interview/tok-test/answer", json={"transcript": "글"})
        assert res.status_code == 409

    def test_유예가_지나면_받지_않는다(self, public, db, ended):
        ended.ended_at = datetime.now(UTC) - timedelta(minutes=11)
        db.commit()
        res = public.post(
            "/api/v1/public/interview/tok-test/answer", json={"transcript": "늦은 글", "seq": 1}
        )
        assert res.status_code == 409


class TestTurnFindingsHook:
    """답변을 저장하면 그 답변 하나의 서류 대조가 뒤에서 돈다 (2026-09-11).

    담당자 화상 방이 대조를 **그 답변 밑에** 띄우는 근거다. 끝날 때만 돌면 면접
    도중에는 아무것도 볼 수 없다.
    """

    @pytest.fixture()
    def running(self, db: Session, application: Application, admin_user: User):
        s = _session(
            db, application, admin_user, status="in_progress", consented_at=datetime.now(UTC)
        )
        _question(db, s, seq=1)
        db.commit()
        return s

    def test_답을_저장하면_그_답변의_대조를_건다(self, public, db, running):
        with patch("app.agent.interview_findings.generate_turn_findings_bg") as bg:
            res = public.post(
                "/api/v1/public/interview/tok-test/answer",
                json={"transcript": "네 했습니다", "seq": 1},
            )
        assert res.status_code == 200
        turn = db.scalar(select(InterviewTurn).where(InterviewTurn.session_id == running.id))
        bg.assert_called_once_with(running.id, turn.id)

    def test_상세에_스위치_상태와_답변_번호가_실린다(
        self, as_user, admin_user, db, running, monkeypatch
    ):
        """스위치가 꺼져 있으면 대조가 비어 보인다 — 꺼진 것과 아직 없는 것을 화면이
        가를 수 있어야 한다(2026-09-11: 운영에서 꺼져 있었다)."""
        from app.models import InterviewFinding

        turn = db.scalar(select(InterviewTurn).where(InterviewTurn.session_id == running.id))
        db.add(
            InterviewFinding(
                session_id=running.id,
                turn_id=turn.id,
                claim_source="resume",
                claim_text="주장",
                answer_text="답",
                verdict="consistent",
            )
        )
        db.commit()
        client = as_user(admin_user)

        monkeypatch.delenv("AGENT_FINDINGS_BACKEND", raising=False)
        body = client.get(f"/api/v1/interview-sessions/{running.id}").json()
        assert body["findings_enabled"] is False
        assert body["findings"][0]["turn_seq"] == 1

        monkeypatch.setenv("AGENT_FINDINGS_BACKEND", "ollama")
        body = client.get(f"/api/v1/interview-sessions/{running.id}").json()
        assert body["findings_enabled"] is True


class _SameSession:
    """배경 태스크가 **테스트 세션을 그대로 쓰게** 한다.

    `seed_questions_bg` · `generate_followup_bg` 는 자기 `SessionLocal()` 을 연다.
    테스트 픽스처의 트랜잭션은 커밋되지 않으므로 새 연결에서는 방금 만든 세션이
    보이지 않고, 배경 함수가 "세션 없음" 으로 조용히 빠져나간다 — 그러면 상한
    검증이 **거짓 통과**한다 (실제로 그렇게 통과했다). 닫지도 않는다: 닫으면
    이후 단정에서 쓸 세션이 사라진다.
    """

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc):
        return False


class TestQuestionCounts:
    """질문 수 상한 — 사전 4개 · 꼬리 3개 (2026-09-12 팀장 요청).

    **왜 상한이 필요한가**: 사전 질문 10개 + 답변마다 붙는 꼬리질문이면 한 면접이
    20문항을 넘어간다. 지원자가 지치고 시연에서는 끝까지 못 간다. 상한이 조용히
    풀리면 그대로 재발하므로 숫자를 테스트로 못 박는다.
    """

    def test_사전_질문은_4개까지(self, db: Session, application, admin_user, monkeypatch):
        from app.interview import session_service

        s = _session(db, application, admin_user, token="tok-seed")
        monkeypatch.setattr("app.db.SessionLocal", lambda: _SameSession(db))

        # 주장 5개 × 질문 2개 = 10개를 주더라도 4개로 잘려야 한다
        claims = [
            {"claim": f"주장 {i}", "type": "역할", "questions": [f"질문 {i}-1", f"질문 {i}-2"]}
            for i in range(5)
        ]
        monkeypatch.setattr(
            "app.agent.interview_probe.sources_of",
            lambda app, db=None: {"cover_letter": "글이 있다", "resume": "", "requirements": ""},
        )
        monkeypatch.setattr("app.agent.interview_probe.generate_probes", lambda s: claims)

        session_service.seed_questions_bg(s.id)

        rows = (
            db.query(InterviewTurn)
            .filter(InterviewTurn.session_id == s.id)
            .order_by(InterviewTurn.seq)
            .all()
        )
        assert len(rows) == session_service.MAX_SEED_QUESTIONS == 4, [r.question for r in rows]
        # 주장별 첫 질문이 먼저 채워진다 — 같은 주장을 두 번 묻지 않는다
        assert [r.question for r in rows] == ["질문 0-1", "질문 1-1", "질문 2-1", "질문 3-1"]

    def test_꼬리질문은_3개까지(self, db: Session, application, admin_user, monkeypatch):
        from app.interview import session_service

        s = _session(db, application, admin_user, token="tok-follow", status="in_progress")
        base = _question(db, s, seq=1)
        base.transcript = "결제 정산 API 를 맡아 응답 시간을 절반으로 줄였습니다"
        # 이미 상한만큼 꼬리질문이 있다
        for i in range(session_service.MAX_FOLLOWUPS_PER_SESSION):
            db.add(InterviewTurn(
                session_id=s.id, seq=10 + i, question=f"꼬리 {i}",
                generated_from_turn_id=base.id,
            ))
        db.flush()
        monkeypatch.setattr("app.db.SessionLocal", lambda: _SameSession(db))

        called: list[str] = []
        monkeypatch.setattr(
            "app.agent.interview_probe.probe_from_answer",
            lambda **kw: called.append("x") or "새 꼬리질문",
        )
        session_service.generate_followup_bg(s.id, base.id)

        assert called == [], "상한을 넘었는데 LLM 을 불렀다"
        n = (
            db.query(InterviewTurn)
            .filter(
                InterviewTurn.session_id == s.id,
                InterviewTurn.generated_from_turn_id.is_not(None),
            )
            .count()
        )
        assert n == session_service.MAX_FOLLOWUPS_PER_SESSION == 3


class TestSeedFallbackFirst:
    """폴백을 세션과 같이 넣고, 맞춤 질문은 시작 전에만 바꿔 넣는다 (2026-09-17, 수택님 B2).

    맞춤 질문은 뒤에서 LLM 으로 몇 초 걸린다. 그 사이 「시작」 하면 질문이 0개라
    422 였다 — 시연처럼 링크를 만들자마자 누르는 자리에서 난다.
    """

    def _turns(self, db: Session, s: InterviewSession) -> list[str]:
        db.expire_all()
        return [
            t.question
            for t in db.scalars(
                select(InterviewTurn)
                .where(InterviewTurn.session_id == s.id)
                .order_by(InterviewTurn.seq)
            )
        ]

    def _claims(self, monkeypatch, n: int = 2):
        monkeypatch.setattr(
            "app.agent.interview_probe.sources_of",
            lambda app, db=None: {"cover_letter": "글이 있다", "resume": "", "requirements": ""},
        )
        monkeypatch.setattr(
            "app.agent.interview_probe.generate_probes",
            lambda s: [{"claim": f"주장 {i}", "questions": [f"맞춤 {i}"]} for i in range(n)],
        )

    def test_뒤_작업이_안_끝나도_바로_시작할_수_있다(
        self, as_user, public, db: Session, application: Application, admin_user: User
    ):
        from app.interview.session_service import DEFAULT_QUESTIONS

        # 뒤 작업이 아직 안 돈 상태 — LLM 이 도는 중인 것과 같다
        with patch("app.interview.api.interviews._seed_questions_bg"):
            body = as_user(admin_user).post(
                f"/api/v1/applications/{application.id}/interview-sessions", json={}
            ).json()
        token = body["token"]

        assert public.post(
            f"/api/v1/public/interview/{token}/consent", json={"agreed": True}
        ).status_code == 200
        res = public.post(f"/api/v1/public/interview/{token}/start")

        assert res.status_code == 200, res.text
        assert res.json()["status"] == "in_progress"
        assert res.json()["current_question"] == DEFAULT_QUESTIONS[0]

    def test_시작_전이면_맞춤_질문으로_바꾼다(
        self, db: Session, application: Application, admin_user: User, monkeypatch
    ):
        from app.interview import session_service

        s = _session(db, application, admin_user, token="tok-swap")
        session_service.add_default_questions(db, s.id)
        db.flush()
        monkeypatch.setattr("app.db.SessionLocal", lambda: _SameSession(db))
        self._claims(monkeypatch)

        session_service.seed_questions_bg(s.id)

        assert self._turns(db, s) == ["맞춤 0", "맞춤 1"]

    def test_이미_시작했으면_폴백을_그대로_둔다(
        self, db: Session, application: Application, admin_user: User, monkeypatch
    ):
        """진행 중에 질문이 바뀌면 지원자가 본 질문과 저장된 질문이 어긋난다."""
        from app.interview import session_service

        s = _session(db, application, admin_user, token="tok-started", status="in_progress")
        session_service.add_default_questions(db, s.id)
        db.flush()
        monkeypatch.setattr("app.db.SessionLocal", lambda: _SameSession(db))
        self._claims(monkeypatch)

        session_service.seed_questions_bg(s.id)

        assert self._turns(db, s) == list(session_service.DEFAULT_QUESTIONS)

    def test_담당자가_고친_질문은_덮지_않는다(
        self, db: Session, application: Application, admin_user: User, monkeypatch
    ):
        from app.interview import session_service

        s = _session(db, application, admin_user, token="tok-edited")
        _question(db, s)  # 담당자가 편집기로 넣은 질문
        monkeypatch.setattr("app.db.SessionLocal", lambda: _SameSession(db))
        self._claims(monkeypatch)

        session_service.seed_questions_bg(s.id)

        assert self._turns(db, s) == ["자기소개 부탁드립니다"]

    def test_맞춤_질문이_없으면_폴백이_겹치지_않는다(
        self, db: Session, application: Application, admin_user: User, monkeypatch
    ):
        from app.interview import session_service

        s = _session(db, application, admin_user, token="tok-none")
        session_service.add_default_questions(db, s.id)
        db.flush()
        monkeypatch.setattr("app.db.SessionLocal", lambda: _SameSession(db))
        # 자료는 있는데 뽑힌 질문이 없다
        monkeypatch.setattr("app.agent.interview_probe.generate_probes", lambda s: [])
        monkeypatch.setattr(
            "app.agent.interview_probe.sources_of",
            lambda app, db=None: {"cover_letter": "글이 있다", "resume": "", "requirements": ""},
        )

        session_service.seed_questions_bg(s.id)

        assert self._turns(db, s) == list(session_service.DEFAULT_QUESTIONS)


class TestRetranscribe:
    """자리표시자로 남은 답변을 음성으로 다시 채운다 (2026-09-16).

    2026-09-15 세션 75 에서 전사가 상한(180초)을 넘겨 `[전사 지연 · 발화 43.9초]`
    가 저장됐고 되살릴 길이 없었다([ADR-0038](../../docs/03_decision/0038-실시간-전사-OpenAI-API.md)).
    **지원자가 한 말이 사라지는 자리**라 규칙마다 테스트를 붙인다.
    """

    @pytest.fixture()
    def ended(self, db: Session, application: Application, admin_user: User):
        s = _session(
            db,
            application,
            admin_user,
            token="tok-retry",
            status="done",
            consented_at=datetime.now(UTC),
        )
        db.add_all(
            [
                # 1 — 전사를 못 했고 음성은 남아 있다 (되살릴 수 있다)
                InterviewTurn(
                    session_id=s.id, seq=1, question="질문1",
                    transcript="[전사 지연 · 발화 43.9초]",
                    audio_s3_key=_AUDIO_KEY, answered_at=datetime.now(UTC),
                ),
                # 2 — 멀쩡히 들어간 답
                InterviewTurn(
                    session_id=s.id, seq=2, question="질문2",
                    transcript="제대로 들어간 답입니다",
                    audio_s3_key=_AUDIO_KEY, answered_at=datetime.now(UTC),
                ),
                # 3 — 실시간 소켓 경로라 음성이 없다 (못 살린다)
                InterviewTurn(
                    session_id=s.id, seq=3, question="질문3",
                    transcript="[전사 불가 · 발화 8.9초]",
                    answered_at=datetime.now(UTC),
                ),
            ]
        )
        db.commit()
        return s

    def _turn(self, db: Session, s: InterviewSession, seq: int) -> InterviewTurn:
        db.expire_all()
        return db.scalar(
            select(InterviewTurn).where(
                InterviewTurn.session_id == s.id, InterviewTurn.seq == seq
            )
        )

    def test_자리표시자를_음성으로_다시_채우고_채점을_다시_돌린다(
        self, as_user, admin_user: User, db: Session, ended
    ):
        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", return_value=_stt_result()),
            patch("app.interview.scoring.score_interview_bg") as rescore,
            patch("app.agent.interview_findings.generate_turn_findings_bg") as findings,
        ):
            res = as_user(admin_user).post(
                f"/api/v1/interview-sessions/{ended.id}/retranscribe"
            )

        assert res.status_code == 200
        body = res.json()
        assert body["filled"] == [1]
        assert body["no_audio"] == [3], "음성이 없어 못 살리는 칸을 그대로 알려줘야 한다"
        assert self._turn(db, ended, 1).transcript.startswith("결제 정산 API")
        # 빈 답변으로 매긴 점수가 그대로 남으면 담당자가 그 점수를 보고 판단한다
        rescore.assert_called_once_with(ended.id)
        findings.assert_called_once()

    def test_멀쩡한_답변은_건드리지_않는다(
        self, as_user, admin_user: User, db: Session, ended
    ):
        """몇 번을 눌러도 안전해야 한다 — 실패한 칸만 다시 시도한다."""
        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", return_value=_stt_result()) as stt,
            patch("app.interview.scoring.score_interview_bg"),
            patch("app.agent.interview_findings.generate_turn_findings_bg"),
        ):
            as_user(admin_user).post(f"/api/v1/interview-sessions/{ended.id}/retranscribe")

        assert self._turn(db, ended, 2).transcript == "제대로 들어간 답입니다"
        assert stt.call_count == 1, "이미 글이 있는 칸까지 전사하면 돈이 두 번 나간다"

    def test_이번에도_못_받아쓰면_자리표시자를_그대로_둔다(
        self, as_user, admin_user: User, db: Session, ended
    ):
        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", side_effect=RuntimeError("STT 죽음")),
            patch("app.interview.scoring.score_interview_bg") as rescore,
        ):
            res = as_user(admin_user).post(
                f"/api/v1/interview-sessions/{ended.id}/retranscribe"
            )

        assert res.status_code == 200
        assert res.json()["failed"] == [1]
        assert self._turn(db, ended, 1).transcript == "[전사 지연 · 발화 43.9초]"
        rescore.assert_not_called()  # 바뀐 게 없으면 다시 매기지 않는다

    def test_로그인_없이는_부를_수_없다(self, public, ended):
        """지원자 목소리를 다시 읽는 경로다. 토큰만으로 열면 안 된다."""
        res = public.post(f"/api/v1/interview-sessions/{ended.id}/retranscribe")
        assert res.status_code in (401, 403)

    def test_없는_세션이면_404(self, as_user, admin_user: User):
        res = as_user(admin_user).post("/api/v1/interview-sessions/999999/retranscribe")
        assert res.status_code == 404

    def test_전사가_실패해도_음성_키는_남는다(
        self, as_user, admin_user: User, public, db: Session,
        application: Application,
    ):
        """**이게 되살리기의 전제다.** 키가 안 남으면 S3 에 음성이 있어도 어느
        회차의 것인지 모른다 — 세션 75 가 그랬다."""
        s = _session(
            db, application, admin_user, token="tok-keep-key",
            status="in_progress", consented_at=datetime.now(UTC),
        )
        db.add(InterviewTurn(session_id=s.id, seq=1, question="질문1"))
        db.commit()

        with (
            patch("app.shared.s3.read_object", return_value=b"fake-audio"),
            patch("app.agent.stt.transcribe", side_effect=RuntimeError("STT 죽음")),
        ):
            res = public.post(
                "/api/v1/public/interview/tok-keep-key/answer",
                json={"audio_s3_key": _AUDIO_KEY},
            )

        assert res.status_code == 502
        turn = self._turn(db, s, 1)
        assert turn.audio_s3_key == _AUDIO_KEY, "다시 받아쓸 실마리가 사라졌다"
        assert turn.transcript is None, "실패한 전사를 답변으로 저장하면 안 된다"
        assert turn.answered_at is None, "지원자는 같은 질문에 다시 답할 수 있어야 한다"
