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
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import InterviewSession, User
from app.adapter.outbound.pg.interview_pg_repository import PgInterviewRepository

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["interview-rtc"])

# 연결을 맺는 데 쓰는 서버 목록. **클라이언트가 박아 두지 않고 서버가 알려준다** —
# TURN 이 나중에 생겨도 앱·웹을 다시 배포하지 않아도 되게.
#
# STUN 은 "내 공인 IP 가 뭔지" 알려주는 것뿐이라 공용 서버로 충분하다. 서로 다른 망
# (LTE ↔ 사무실)이면 그것만으로는 못 붙고 **TURN**(실제 중계)이 필요하다.
# 형식은 JSON 배열 그대로 — `[{"urls":"turn:…","username":"…","credential":"…"}]`
_DEFAULT_ICE = '[{"urls": "stun:stun.l.google.com:19302"}]'


def _static_ice_servers() -> list[dict]:
    """환경변수에 박힌 목록. TURN 자동 발급이 없거나 실패했을 때의 바닥."""
    raw = os.getenv("RTC_ICE_SERVERS", "").strip() or _DEFAULT_ICE
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # 설정이 깨졌다고 면접을 못 하게 만들지 않는다. 같은 망이면 STUN 만으로 붙는다.
        log.warning("RTC_ICE_SERVERS 파싱 실패 — 기본 STUN 으로 간다")
        return json.loads(_DEFAULT_ICE)
    return parsed if isinstance(parsed, list) else json.loads(_DEFAULT_ICE)


# Cloudflare TURN 자동 발급 (2026-09-08, 이슈 #70). Cloudflare 의 TURN credential 은
# **최대 24시간**짜리라 손으로 갱신하면 매일 만료된다. 서버가 필요할 때 키로 발급받아
# 캐시하고, 만료 4시간 전에 새로 받는다 — Cloudflare 가 권하는 방식(세션마다 단기 자격)
# 을 하루 단위로 굵게 자른 것. 부르는 쪽(입장권·WebSocket hello)은 바뀌지 않는다.
#
# 실패 정책: 발급이 안 되면 (키 없음·네트워크·400) **정적 RTC_ICE_SERVERS → 기본 STUN**
# 으로 내려간다. 캐시가 아직 유효하면 그것을 계속 쓴다. 면접이 설정 때문에 멈추지 않게.
_CF_TURN_URL = "https://rtc.live.cloudflare.com/v1/turn/keys/{key_id}/credentials/generate-ice-servers"
_TURN_TTL_DEFAULT = 86400          # Cloudflare 상한. 넘기면 400 invalid argument (2026-09-08 실측)
_TURN_REFRESH_MARGIN = 4 * 3600    # 만료 4시간 전부터 갱신
_turn_cache: dict = {"servers": None, "expires_at": 0.0}
_turn_lock = threading.Lock()


def _cloudflare_ice_servers() -> list[dict] | None:
    key_id = os.getenv("TURN_KEY_ID", "").strip()
    token = os.getenv("TURN_KEY_API_TOKEN", "").strip()
    if not key_id or not token:
        return None

    now = time.time()
    if _turn_cache["servers"] and now < _turn_cache["expires_at"] - _TURN_REFRESH_MARGIN:
        return _turn_cache["servers"]

    with _turn_lock:
        if _turn_cache["servers"] and now < _turn_cache["expires_at"] - _TURN_REFRESH_MARGIN:
            return _turn_cache["servers"]
        try:
            ttl = int(os.getenv("TURN_CREDENTIAL_TTL", "").strip() or _TURN_TTL_DEFAULT)
        except ValueError:
            ttl = _TURN_TTL_DEFAULT
        try:
            import httpx  # 지연 임포트 — 키가 없는 배포는 이 경로를 안 탄다

            resp = httpx.post(
                _CF_TURN_URL.format(key_id=key_id),
                json={"ttl": ttl},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5.0,
            )
            resp.raise_for_status()
            servers = resp.json().get("iceServers")
            if not isinstance(servers, list) or not servers:
                raise ValueError("응답에 iceServers 배열이 없다")
        except Exception:
            log.warning(
                "Cloudflare TURN credential 발급 실패 — 정적 RTC_ICE_SERVERS/STUN 으로 간다",
                exc_info=True,
            )
            if _turn_cache["servers"] and now < _turn_cache["expires_at"]:
                return _turn_cache["servers"]  # 아직 안 죽은 캐시는 계속 쓴다
            return None
        _turn_cache["servers"] = servers
        _turn_cache["expires_at"] = now + ttl
        log.info("Cloudflare TURN credential 발급 ttl=%ss", ttl)
        return servers


def ice_servers() -> list[dict]:
    """클라이언트에 줄 ICE 서버 목록. Cloudflare 자동 발급 → 정적 설정 → 기본 STUN."""
    return _cloudflare_ice_servers() or _static_ice_servers()


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
    # 이 방을 만든 이벤트 루프. **동기 라우터(다른 스레드)에서 방을 닫으려면**
    # 루프를 알아야 한다 — FastAPI 는 `def` 엔드포인트를 스레드풀에서 돌리므로
    # 그 스레드에는 실행 중인 루프가 없다. 방은 WS 핸들러(=루프 안)에서만
    # 만들어지니 그때 붙여 둔다. `close_room_from_thread` 가 쓴다.
    loop: asyncio.AbstractEventLoop | None = None


_ROOMS: dict[str, Room] = {}

ROLES = ("applicant", "recruiter")

# 상대에게 **그대로 넘기는** 것들. 서버는 내용을 들여다보지 않는다 —
# SDP 는 WebRTC 가 읽을 것이지 우리가 해석할 것이 아니다.
#
# `verdict` 는 2026-09-08 에 붙었다 — **AI 면접의 실시간 판정을 담당자 화면으로
# 나르는 길**이다. 판정은 지원자 기기에서 `/ai/ws/live` 로 받는데, 서버에는
# 그것을 담당자에게 보낼 통로가 따로 없었다. 이미 있는 방을 쓴다.
#
# **지원자 화면에는 이 값을 띄우지 않는다** (ADR-0029, `ai/lie-detection/app.py`
# 주석): 판정을 실시간으로 보여 주면 그 자체가 답변을 바꾼다. 서버는 그저
# 나르기만 하고, 안 띄우는 것은 화면 쪽 약속이다.
RELAY_TYPES = frozenset({"offer", "answer", "ice", "bye", "verdict"})

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
    session = PgInterviewRepository(db).get_session(session_id)
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
    room.loop = asyncio.get_running_loop()  # 동기 라우터가 방을 닫을 때 쓴다
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


async def close_room(token: str, *, code: str, message: str) -> int:
    """방을 닫고 앉아 있던 사람 전원에게 이유를 알린다. 닫은 연결 수.

    **왜 필요한가** (2026-09-12): 담당자가 면접 세션을 지워도 그 방에 붙어 있던
    WebSocket 은 그대로 남았다. `delete_session` 독스트링은 "지원자가 접속 중이어도
    방이 닫힐 뿐"이라고 적어 뒀지만 **닫는 코드가 없었다.**

    실제로 09-12 시연 테스트에서: 담당자가 62번 방을 열어 둔 채 다른 탭에서 62번을
    지우고 63번을 새로 만들었다. 방 키가 세션 토큰이라 담당자는 사라진 62번 방에,
    지원자는 63번 방에 앉아 서로를 못 봤다. 담당자 화면에는 "연결 안 됨" 만 떴고
    원인을 알 길이 없었다 — 이제 그 순간 방이 닫히며 이유가 전달된다.
    """
    room = _ROOMS.pop(token, None)
    if room is None:
        return 0
    async with room.lock:
        peers = list(room.peers.values())
        room.peers.clear()
    for ws in peers:
        await _send(ws, {"type": "error", "code": code, "message": message})
        try:
            await ws.close(code=4404)
        except RuntimeError:
            pass
    return len(peers)


def close_room_from_thread(token: str, *, code: str, message: str) -> bool:
    """동기 라우터에서 방을 닫는다. 예약했으면 True.

    `def` 엔드포인트는 스레드풀에서 돌아 실행 중인 루프가 없다. 그래서 방을 만든
    루프(`Room.loop`)에 코루틴을 던진다. 닫을 방이 없으면(아무도 안 붙어 있으면)
    그냥 False — **그것 때문에 삭제가 실패하면 안 된다.**
    """
    room = _ROOMS.get(token)
    if room is None or room.loop is None:
        return False
    try:
        asyncio.run_coroutine_threadsafe(
            close_room(token, code=code, message=message), room.loop
        )
    except RuntimeError:  # 루프가 이미 닫혔다 — 서버가 내려가는 중
        return False
    return True


async def push_to_recruiter(token: str, payload: dict) -> bool:
    """방에 앉아 있는 **채용자에게만** 한 줄 민다. 보냈으면 True.

    거짓말 탐지 워커가 실시간 판정을 흘려보내는 자리다 (`api/internal.py`).
    지원자에게는 보내지 않는다 — ADR-0029 의 "판정을 지원자에게 보여 주지
    않는다"가 여기서 지켜진다. **지원자 기기를 아예 지나가지 않는다.**

    담당자가 화면을 안 열었으면 조용히 False 다. 그것 때문에 면접이 멈추거나
    워커가 재시도하면 안 된다.
    """
    room = _ROOMS.get(token)
    target = room.peers.get("recruiter") if room else None
    if target is None:
        return False
    await _send(target, payload)
    return True
