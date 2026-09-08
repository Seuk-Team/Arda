"""실시간 면접 시그널링 — 지원자(폰) ⟷ 채용자(PC) 1:1 WebRTC.

프로토콜 원본은 [docs/02_tasks/실시간-면접-시그널링.md]. 값을 바꾸면 같이 고친다.

**여기는 신호만 나른다.** 영상·음성은 두 브라우저가 서로 직접 주고받고
(WebRTC), 서버는 그 연결을 맺는 데 필요한 쪽지(SDP·ICE)만 상대에게 넘긴다.
그래서 이 파일에는 미디어 코드가 한 줄도 없고, 사람이 늘어도 서버 대역폭이
늘지 않는다.

**왜 SFU 를 안 만드는가.** 00-overview 가 실시간 화상면접을 제외하며 든 근거는
"3인 이상 동시 접속은 시그널링 + TURN + SFU 까지 필요해 1명의 4주"였다.
**1:1 은 SFU 가 필요 없다** — 중계 서버 없이 두 끝점이 직접 붙는다. 그 견적은
이 범위에 그대로 적용되지 않으므로 00-overview 의 제외 문구를 같이 고쳤다.

**한 프로세스를 전제로 한다.** 방(_ROOMS)이 파이썬 딕셔너리라 uvicorn 워커가
2개 이상이면 지원자와 채용자가 다른 프로세스에 붙어 서로를 못 본다. 운영은
지금 `--workers` 없이(1개) 돈다. **워커를 늘리려면 여기부터 Redis pub/sub 으로
바꿔야 한다** — 늘린 사람이 알 수 있게 시작 로그에 남긴다.
"""

import asyncio
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import InterviewSession, User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["interview-rtc"])

# 연결을 맺는 데 쓰는 서버 목록. **클라이언트가 박아 두지 않고 서버가 알려준다** —
# TURN 이 나중에 생겨도 앱·웹을 다시 배포하지 않아도 되게.
#
# STUN 은 "내 공인 IP 가 뭔지" 알려주는 것뿐이라 공용 서버로 충분하다. 서로 다른 망
# (LTE ↔ 사무실)이면 그것만으로는 못 붙고 **TURN**(실제 중계)이 필요하다.
# 형식은 JSON 배열 그대로 — `[{"urls":"turn:…","username":"…","credential":"…"}]`
_DEFAULT_ICE = '[{"urls": "stun:stun.l.google.com:19302"}]'


def ice_servers() -> list[dict]:
    raw = os.getenv("RTC_ICE_SERVERS", "").strip() or _DEFAULT_ICE
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # 설정이 깨졌다고 면접을 못 하게 만들지 않는다. 같은 망이면 STUN 만으로 붙는다.
        log.warning("RTC_ICE_SERVERS 파싱 실패 — 기본 STUN 으로 간다")
        return json.loads(_DEFAULT_ICE)
    return parsed if isinstance(parsed, list) else json.loads(_DEFAULT_ICE)


# ── 채용자 입장권 ────────────────────────────────────────────────────────────
#
# 브라우저의 WebSocket 은 **헤더를 붙일 수 없다.** 그래서 평소 쓰는
# `Authorization: Bearer` 를 못 싣는다. JWT 를 그냥 쿼리스트링에 넣으면 접속
# 로그·리퍼러에 장기 토큰이 그대로 남으므로, **한 번 쓰고 버리는 짧은 입장권**을
# REST 로 먼저 받아 온다.
TICKET_TTL_SEC = 60

# ticket → (session_id, user_id, 발급시각)
_TICKETS: dict[str, tuple[int, int, float]] = {}


def _sweep_tickets(now: float) -> None:
    for t in [t for t, (_, _, at) in _TICKETS.items() if now - at > TICKET_TTL_SEC]:
        _TICKETS.pop(t, None)


def issue_ticket(session_id: int, user_id: int) -> str:
    now = time.time()
    _sweep_tickets(now)
    ticket = secrets.token_urlsafe(24)
    _TICKETS[ticket] = (session_id, user_id, now)
    return ticket


def redeem_ticket(ticket: str, session_id: int) -> int | None:
    """쓰면 사라진다. 맞으면 user_id, 아니면 None."""
    entry = _TICKETS.pop(ticket, None)
    if entry is None:
        return None
    sid, user_id, at = entry
    if sid != session_id or time.time() - at > TICKET_TTL_SEC:
        return None
    return user_id


# ── 방 ───────────────────────────────────────────────────────────────────────


@dataclass
class Room:
    """면접 한 건. 자리가 둘뿐이다 — 지원자 하나, 채용자 하나."""

    peers: dict[str, WebSocket] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


_ROOMS: dict[str, Room] = {}

ROLES = ("applicant", "recruiter")

# 상대에게 **그대로 넘기는** 것들. 서버는 내용을 들여다보지 않는다 —
# SDP 는 WebRTC 가 읽을 것이지 우리가 해석할 것이 아니다.
RELAY_TYPES = frozenset({"offer", "answer", "ice", "bye"})

# 한 쪽지의 상한. SDP 는 보통 5KB 안쪽이고 ICE 는 훨씬 작다. 상한이 없으면
# 방에 붙은 것만으로 메모리를 밀어 넣을 수 있다.
MAX_MESSAGE_BYTES = 128 * 1024


def _find_session(db: Session, token: str) -> InterviewSession | None:
    return db.query(InterviewSession).filter(InterviewSession.token == token).one_or_none()


@router.post("/interview-sessions/{session_id}/rtc-ticket")
def create_rtc_ticket(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """채용자용 시그널링 입장권. **로그인 필요.**

    지원자는 이게 필요 없다 — 메일 링크의 토큰이 곧 자격이다. 채용자에게만
    따로 두는 이유는 **토큰을 아는 사람 아무나 면접관 자리에 앉으면 안 되기**
    때문이다. 링크가 한 번 전달되면 그 사람도 지원자의 영상을 보게 된다.
    """
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "면접 세션을 찾을 수 없습니다")

    return {
        "ticket": issue_ticket(session_id, user.id),
        "token": session.token,
        "expires_in": TICKET_TTL_SEC,
        "ice_servers": ice_servers(),
    }


async def _send(ws: WebSocket, payload: dict) -> None:
    try:
        await ws.send_text(json.dumps(payload, ensure_ascii=False))
    except (WebSocketDisconnect, RuntimeError):
        # 상대가 이미 끊었다. 끊긴 것은 오류가 아니다 — 다시 붙으면 된다.
        pass


@router.websocket("/ws/interview/{token}/rtc")
async def interview_rtc(
    websocket: WebSocket,
    token: str,
    ticket: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """1:1 시그널링. 지원자는 토큰만으로, 채용자는 입장권까지 있어야 한다.

    붙는 순간 `hello` 를 받고, 상대가 들어오면 `peer-join` 을 받는다.
    **offer 는 항상 채용자가 만든다** — 양쪽이 동시에 offer 를 내면
    (glare) 협상이 꼬이므로 거는 쪽을 하나로 고정한다.
    """
    # DB 는 붙는 순간에만 본다. **연결이 사는 동안 세션을 붙들지 않는다** —
    # 면접은 몇십 분이고 커넥션 풀은 그보다 훨씬 귀하다.
    session = _find_session(db, token)
    if session is None:
        await websocket.close(code=4404)
        return
    session_id = session.id
    session_status = session.status
    db.close()

    role = "applicant"
    if ticket:
        if redeem_ticket(ticket, session_id) is None:
            await websocket.close(code=4401)
            return
        role = "recruiter"

    if session_status in ("done", "expired"):
        await websocket.accept()
        await _send(websocket, {
            "type": "error",
            "code": "session_closed",
            "message": "이미 끝났거나 만료된 면접입니다",
        })
        await websocket.close(code=4409)
        return

    await websocket.accept()

    room = _ROOMS.setdefault(token, Room())
    async with room.lock:
        old = room.peers.get(role)
        room.peers[role] = websocket
    if old is not None:
        # 같은 자리에 새로 붙었다 — 새로고침이 보통이다. 옛 연결은 조용히 닫는다.
        await _send(old, {"type": "error", "code": "replaced",
                          "message": "다른 곳에서 접속해 이 연결을 닫습니다"})
        try:
            await old.close(code=4409)
        except RuntimeError:
            pass

    peer_role = "recruiter" if role == "applicant" else "applicant"
    await _send(websocket, {
        "type": "hello",
        "role": role,
        "peer_present": peer_role in room.peers,
        "ice_servers": ice_servers(),
        # 거는 쪽을 서버가 정해 준다. 클라이언트가 각자 판단하면 둘 다 걸거나
        # 둘 다 안 거는 경우가 생긴다.
        "should_offer": role == "recruiter" and peer_role in room.peers,
    })

    peer = room.peers.get(peer_role)
    if peer is not None:
        await _send(peer, {"type": "peer-join", "role": role})

    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_MESSAGE_BYTES:
                await _send(websocket, {"type": "error", "code": "too_large",
                                        "message": "메시지가 너무 큽니다"})
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue

            kind = msg.get("type")
            if kind == "ping":
                await _send(websocket, {"type": "pong"})
                continue
            if kind not in RELAY_TYPES:
                continue

            target = room.peers.get(peer_role)
            if target is None:
                await _send(websocket, {"type": "error", "code": "no_peer",
                                        "message": "상대가 아직 들어오지 않았습니다"})
                continue
            # **내용을 고치지 않고 그대로 넘긴다.** 보낸 쪽이 누구인지만 덧붙인다.
            await _send(target, {**msg, "from": role})
    except WebSocketDisconnect:
        pass
    finally:
        async with room.lock:
            if room.peers.get(role) is websocket:
                room.peers.pop(role, None)
            empty = not room.peers
            if empty:
                _ROOMS.pop(token, None)
        remaining = room.peers.get(peer_role)
        if remaining is not None:
            await _send(remaining, {"type": "peer-leave", "role": role})
