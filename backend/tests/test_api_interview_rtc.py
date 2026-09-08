"""실시간 면접 시그널링 (1:1 WebRTC) — 방·역할·중계.

프로토콜 원본은 docs/02_tasks/실시간-면접-시그널링.md.

**틀렸을 때 지원자의 얼굴이 엉뚱한 사람에게 간다.** 그래서 규칙 하나에 테스트
하나를 붙인다. 특히 아래 셋은 무너지면 바로 사고다:

- 입장권 없이 붙은 사람은 **절대 채용자가 되지 않는다**
- 입장권은 한 번만 쓸 수 있고, 다른 세션의 것으로는 못 들어온다
- 끝났거나 만료된 면접에는 방이 열리지 않는다

나머지(중계·ping·재접속)는 흐름이 도는지를 본다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import interview_rtc
from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import Application, InterviewSession, User


@pytest.fixture()
def client(db: Session):
    """공개 접근용. WebSocket 도 이걸로 연다."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def as_user(db: Session):
    def make(user: User) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clean_rooms():
    """방과 입장권은 프로세스 메모리에 산다 — 테스트끼리 새게 두지 않는다."""
    interview_rtc._ROOMS.clear()
    interview_rtc._TICKETS.clear()
    yield
    interview_rtc._ROOMS.clear()
    interview_rtc._TICKETS.clear()


def _session(db: Session, application: Application, admin_user: User, **kw) -> InterviewSession:
    row = InterviewSession(
        application_id=application.id,
        token=kw.pop("token", "tok-rtc"),
        status=kw.pop("status", "in_progress"),
        expires_at=kw.pop("expires_at", datetime.now(UTC) + timedelta(days=7)),
        created_by=admin_user.id,
        **kw,
    )
    db.add(row)
    db.flush()
    return row


class TestTicket:
    def test_입장권을_발급하면_토큰과_ICE_목록이_같이_온다(
        self, as_user, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        res = as_user(admin_user).post(f"/api/v1/interview-sessions/{s.id}/rtc-ticket")

        assert res.status_code == 200
        body = res.json()
        assert body["ticket"]
        # 채용자는 이 토큰으로 같은 방에 들어간다 — 화면이 조립하지 않는다
        assert body["token"] == s.token
        # 연결 서버 목록도 서버가 준다. TURN 이 생겨도 클라이언트 재배포가 없다
        assert isinstance(body["ice_servers"], list) and body["ice_servers"]

    def test_없는_세션이면_404(self, as_user, admin_user: User):
        res = as_user(admin_user).post("/api/v1/interview-sessions/999999/rtc-ticket")
        assert res.status_code == 404

    def test_로그인_없이는_발급되지_않는다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        assert client.post(f"/api/v1/interview-sessions/{s.id}/rtc-ticket").status_code == 401


class TestJoin:
    def test_토큰만_있으면_지원자로_들어간다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        with client.websocket_connect(f"/api/v1/ws/interview/{s.token}/rtc") as ws:
            hello = ws.receive_json()

        assert hello["type"] == "hello"
        assert hello["role"] == "applicant"
        assert hello["peer_present"] is False
        # 혼자 있을 때는 아무도 offer 를 걸지 않는다
        assert hello["should_offer"] is False

    def test_입장권이_있어야_채용자가_된다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        ticket = interview_rtc.issue_ticket(s.id, admin_user.id)

        with client.websocket_connect(
            f"/api/v1/ws/interview/{s.token}/rtc?ticket={ticket}"
        ) as ws:
            assert ws.receive_json()["role"] == "recruiter"

    def test_틀린_입장권은_지원자로_강등되지_않고_끊긴다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        """**이게 무너지면 조용히 통과한다.** 거절 대신 지원자로 붙여 주면
        채용자 자리가 빈 채로 면접이 도는 것처럼 보인다."""
        s = _session(db, application, admin_user)

        from starlette.websockets import WebSocketDisconnect as WSD

        with pytest.raises(WSD):
            with client.websocket_connect(
                f"/api/v1/ws/interview/{s.token}/rtc?ticket=아무거나"
            ) as ws:
                ws.receive_json()

    def test_입장권은_한_번만_쓴다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        ticket = interview_rtc.issue_ticket(s.id, admin_user.id)

        assert interview_rtc.redeem_ticket(ticket, s.id) == admin_user.id
        assert interview_rtc.redeem_ticket(ticket, s.id) is None

    def test_다른_세션의_입장권으로는_못_들어간다(
        self, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        ticket = interview_rtc.issue_ticket(s.id, admin_user.id)
        assert interview_rtc.redeem_ticket(ticket, s.id + 1) is None

    def test_없는_토큰이면_붙지_못한다(self, client):
        from starlette.websockets import WebSocketDisconnect as WSD

        with pytest.raises(WSD):
            with client.websocket_connect("/api/v1/ws/interview/없는토큰/rtc") as ws:
                ws.receive_json()

    def test_끝난_면접에는_방이_열리지_않는다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user, status="done")
        with client.websocket_connect(f"/api/v1/ws/interview/{s.token}/rtc") as ws:
            msg = ws.receive_json()

        assert msg["type"] == "error"
        assert msg["code"] == "session_closed"


class TestRelay:
    """서버는 쪽지를 **고치지 않고** 상대에게 넘긴다."""

    def test_둘이_붙으면_서로를_알게_된다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        ticket = interview_rtc.issue_ticket(s.id, admin_user.id)

        with client.websocket_connect(f"/api/v1/ws/interview/{s.token}/rtc") as applicant:
            applicant.receive_json()  # hello

            with client.websocket_connect(
                f"/api/v1/ws/interview/{s.token}/rtc?ticket={ticket}"
            ) as recruiter:
                hello = recruiter.receive_json()
                # 나중에 들어온 채용자가 offer 를 건다 — glare 방지
                assert hello["peer_present"] is True
                assert hello["should_offer"] is True

                joined = applicant.receive_json()
                assert joined == {"type": "peer-join", "role": "recruiter"}

    def test_offer_가_상대에게_그대로_간다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        ticket = interview_rtc.issue_ticket(s.id, admin_user.id)

        with client.websocket_connect(f"/api/v1/ws/interview/{s.token}/rtc") as applicant:
            applicant.receive_json()
            with client.websocket_connect(
                f"/api/v1/ws/interview/{s.token}/rtc?ticket={ticket}"
            ) as recruiter:
                recruiter.receive_json()
                applicant.receive_json()  # peer-join

                recruiter.send_json({"type": "offer", "sdp": "v=0 …"})
                got = applicant.receive_json()

        assert got["type"] == "offer"
        # 내용은 그대로. 보낸 쪽만 덧붙는다
        assert got["sdp"] == "v=0 …"
        assert got["from"] == "recruiter"

    def test_상대가_없으면_알려준다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        with client.websocket_connect(f"/api/v1/ws/interview/{s.token}/rtc") as ws:
            ws.receive_json()
            ws.send_json({"type": "offer", "sdp": "x"})
            got = ws.receive_json()

        assert got["type"] == "error"
        assert got["code"] == "no_peer"

    def test_모르는_type_은_무시한다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        """서버가 늘어난 메시지에 놀라 연결을 끊으면 안 된다."""
        s = _session(db, application, admin_user)
        with client.websocket_connect(f"/api/v1/ws/interview/{s.token}/rtc") as ws:
            ws.receive_json()
            ws.send_json({"type": "무슨말", "x": 1})
            ws.send_json({"type": "ping"})
            assert ws.receive_json() == {"type": "pong"}

    def test_상대가_나가면_알려준다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        s = _session(db, application, admin_user)
        ticket = interview_rtc.issue_ticket(s.id, admin_user.id)

        with client.websocket_connect(f"/api/v1/ws/interview/{s.token}/rtc") as applicant:
            applicant.receive_json()
            with client.websocket_connect(
                f"/api/v1/ws/interview/{s.token}/rtc?ticket={ticket}"
            ) as recruiter:
                recruiter.receive_json()
                applicant.receive_json()  # peer-join
            left = applicant.receive_json()

        assert left == {"type": "peer-leave", "role": "recruiter"}

    def test_방은_아무도_없으면_치워진다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        """면접이 끝날 때마다 방이 쌓이면 오래 뜬 서버에서 새는 자리가 된다."""
        s = _session(db, application, admin_user)
        with client.websocket_connect(f"/api/v1/ws/interview/{s.token}/rtc") as ws:
            ws.receive_json()
            assert s.token in interview_rtc._ROOMS

        assert s.token not in interview_rtc._ROOMS
