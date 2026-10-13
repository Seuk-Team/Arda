"""거짓말 탐지 서비스.

두 가지를 낸다.
- `POST /analyze`            영상 파일 하나 → 판정 (담당자 확인·데모용)
- `WS  /ws/interview/{token}` 실시간 면접 (지원자용, ADR-0029)

Flask 가 아니라 FastAPI 인 이유는 WebSocket 때문이다. Flask 로 WS 를 하려면
gevent 계열 워커가 필요하고, 그러면 gunicorn 설정과 배포가 같이 복잡해진다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import httpx
import numpy as np
from fastapi import FastAPI, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

import interview_ws as iw
import speaker_match
from feature_extractor import analyze_timeseries, extract_features
from interview_ws import (
    SERVICE_TOKEN,
    STT_MODEL,
    InterviewSession,
    LiveScorer,
    _SpeechDetector,
    fetch_questions,
    fetch_reference,
    fetch_state,
    finish_interview,
    hint_of,
    mark_answered,
    push_identity,
    push_verdict,
    model,
    score,
    submit_answer,
    transcribe_async,
    strip_end_phrase,
    warm_stt,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _face_and_bgr(jpeg: bytes):
    """JPEG 한 장 → (얼굴 특징 7개, BGR 이미지). 얼굴이 없으면 (None, bgr).

    /ws/live 데모 소켓용 (2026-09-10). 표정 판정을 붙이려면 얼굴 있는 BGR 을
    scorer 에 남겨야 하는데, face_row_of_jpeg 는 row 만 돌려주고 BGR 을 버린다.
    같은 이미지를 두 번 디코드하지 않도록 한 곳에서 처리한다.
    """
    import cv2

    from feature_extractor import face_row

    buf = np.frombuffer(jpeg, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return None, None
    return face_row(img), img

_HERE = Path(__file__).parent
DEMO_HTML = (_HERE / "demo.html").read_text(encoding="utf-8")

# 뜰 때 한 번 읽어 둔다. 모델이 없거나 깨졌으면 첫 요청이 아니라 지금 죽는 편이 낫다.
model()

app = FastAPI(title="Arda 거짓말 탐지")


@app.on_event("startup")
async def _warm() -> None:
    """전사 모델을 뒤에서 미리 올린다.

    **기다리지 않는다.** 여기서 await 하면 26초 동안 헬스체크가 안 뜨고 배포가
    실패한 것처럼 보인다. 그 사이에 들어온 첫 면접은 로딩을 물지만, 예열이 없을
    때처럼 **매 면접이** 무는 것보다는 낫다.
    """
    asyncio.create_task(asyncio.to_thread(warm_stt))


# 실시간 판정이 어디까지 갔는지 세는 자리 (2026-09-09).
#
# **왜 필요한가**: 판정이 담당자 화면에 안 뜰 때, 밖에서는 어디서 멈췄는지 알 길이
# 없었다. 설정이 없어 안 부른 것인지, 얼굴이 모자라 판정을 못 낸 것인지, 백엔드가
# 거절한 것인지가 전부 조용한 실패다. 숫자 네 개면 그 자리에서 갈린다.
#
# **비밀은 안 낸다** — 토큰이 있는지(true/false)만 낸다.
_live_stats = {
    "scored": 0,
    "ok": 0,
    "pushed": 0,
    "push_failed": 0,
    # 판정을 못 낸 이유. `scored - ok` 를 이 둘이 나눠 갖는다.
    "no_face": 0,
    "short_audio": 0,
}


@app.get("/health")
def health():
    return {
        "status": "ok",
        # 전사가 켜져 있는가 · 모델이 올라와 있는가
        "stt_on": bool(STT_MODEL),
        "stt_loaded": iw._stt is not None,
        # 판정을 백엔드로 밀 수 있는가 (토큰 값은 안 낸다)
        "verdict_push_configured": bool(SERVICE_TOKEN),
        # 면접이 도는 동안 실제로 몇 번이나 갔는지
        "live": dict(_live_stats),
        # 가장 최근 면접에서 프레임이 몇 도 누워 있었나 (`face_row_search`).
        # null 이면 얼굴을 한 번도 못 찾은 것이다 — 방향 말고 다른 문제다.
        "frame_rotation": iw.LAST_ROTATION,
        # 프레임이 어디까지 갔는가. 셋을 나눠 봐야 "안 보낸다"와 "못 찾는다"가 갈린다.
        "frames": dict(iw.FRAME_STATS),
        # "답변 끝" 이 몇 번 답변으로 인정됐나 (2026-09-11). `rejected` 는 목소리가
        # 없어 질문을 넘기지 않은 횟수 — 질문이 안 넘어간다는 말이 나오면 여기부터.
        "answers": dict(iw.ANSWER_STATS),
    }


@app.get("/", response_class=HTMLResponse)
def index():
    return DEMO_HTML


@app.post("/analyze")
async def analyze(video: UploadFile | None = None):
    """영상 파일 하나를 판정한다. 데모 화면과 담당자 확인용."""
    if video is None:
        return JSONResponse({"error": "파일 없음"}, status_code=400)

    suffix = os.path.splitext(video.filename or "")[1] or ".mp4"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(await video.read())
    tmp.close()

    try:
        feat = extract_features(tmp.name)
        observations = analyze_timeseries(tmp.name)
    finally:
        os.remove(tmp.name)

    if feat is None:
        return JSONResponse(
            {"error": "얼굴 또는 음성을 감지하지 못했습니다."}, status_code=422
        )

    feat2d = feat.reshape(1, -1)
    m = model()
    pred = int(m.predict(feat2d)[0])
    proba = m.predict_proba(feat2d)[0]

    return {
        "pred": pred,
        "truth_pct": round(float(proba[0]) * 100, 1),
        "lie_pct": round(float(proba[1]) * 100, 1),
        "observations": observations,
    }


# ── 실시간 면접 ────────────────────────────────────────────────

# 바이너리 프레임의 첫 바이트가 무엇인지 알려 준다. 오디오와 영상을 한 연결로
# 보내면서 매번 JSON 머리말을 붙이는 것보다 싸다.
KIND_AUDIO = 0x01
KIND_VIDEO = 0x02

# 목소리 대조를 끄는 스위치. **켜는 스위치가 아니다** — 모델 파일이 있으면 돈다.
# 이건 잘못 잘랐다는 신고가 들어왔을 때 배포를 기다리지 않고 끌 자리다.
# 세션 59("첫 문장이 빠졌다")처럼 잘린 말은 어디에도 안 남아서, 의심되는
# 순간 바로 멈출 수 있어야 한다. `VOICE_GATE=0` → 자르지 않는다.
VOICE_GATE = os.getenv("VOICE_GATE", "1").strip() not in ("0", "false", "")

# 답변이 통째로 남의 목소리로 보인 것이 몇 번 이어지면 지문을 다시 뜨나.
# 1 이면 한 번 어긋난 것만으로 지문을 갈아 끼워 오히려 잡음을 등록하게 된다.
VOICE_STRIKES = 2


@app.websocket("/ws/live")
async def live(ws: WebSocket):
    """카메라를 켠 채 **말하는 동안** 계속 판정한다. 데모 화면 전용.

    면접이 아니다 — 토큰도, 백엔드 연동도, 저장도 없다. 만든 사람이 "이 숫자가
    말이 되나"를 눈으로 보는 자리다. 실제 면접에서 이 값을 지원자 화면으로
    내려보내지 않는다(ADR-0029): 판정을 실시간으로 보여 주면 그 자체가 답변을
    바꾼다.

    프레임 형식은 `/ws/interview` 와 같다(PROTOCOL.md).
    """
    await ws.accept()
    detector = _SpeechDetector()
    scorer = LiveScorer()
    busy = False
    # 얼굴 추출(mediapipe, 프레임당 수십 ms)이 도는 중이면 그 사이 온 프레임은
    # 버린다. 초당 5장을 전부 스레드에 넣으면 큐만 쌓이고, 판정은 4초 창의 5장이면
    # 충분하다(`score`).
    face_busy = False

    async def extract_face(jpeg: bytes, at: float) -> None:
        nonlocal face_busy
        try:
            # **이벤트 루프에서 부르지 않는다** (2026-09-09 실측). 워커가 하나라 이게
            # 루프를 잡으면 같은 프로세스의 면접 소켓 전사가 GIL 을 못 얻어 8초 발화에
            # 36초 걸리고, uvicorn 은 ping 응답을 못 넘겨 40초에 소켓을 닫았다.
            #
            # 얼굴이 있는 프레임의 BGR 도 함께 잡아 표정 판정에 넘긴다 (2026-09-10,
            # ADR-0032 §6 시연 자리). VIT_MODEL 이 꺼져 있으면 저장만 되고 미사용.
            row, bgr = await asyncio.to_thread(_face_and_bgr, jpeg)
            if row is not None:
                scorer.add_face(row, at)
                if bgr is not None:
                    scorer.add_frame(bgr)
        except Exception:
            logger.exception("얼굴 추출 실패")
        finally:
            face_busy = False

    async def run_score() -> None:
        nonlocal busy
        try:
            pcm, rows, frame = scorer.snapshot()
            # 판정은 CPU 로 약 185ms 걸린다. 여기서 그냥 부르면 그 동안 이 워커의
            # **모든 연결**이 멈춘다 — 워커가 하나뿐이라 더 그렇다.
            # frame 이 있고 VIT_MODEL 이 켜져 있으면 표정 top-3 도 붙는다.
            result = await asyncio.to_thread(
                score, pcm, rows, scorer.window_sec, frame
            )
            await ws.send_json({"type": "live", **result})
        except Exception:
            logger.exception("실시간 판정 실패")
        finally:
            busy = False

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break

            data = msg.get("bytes")
            if not data:
                continue

            kind, payload, now = data[0], data[1:], time.monotonic()

            if kind == KIND_VIDEO:
                if not face_busy:
                    face_busy = True
                    asyncio.create_task(extract_face(payload, now))
                continue

            if kind != KIND_AUDIO:
                continue

            scorer.add_audio(payload)
            was_speaking = detector.speaking
            detector.feed(payload)
            # `feed` 의 반환값이 아니라 상태로 본다 — 너무 짧은 발화는 'end' 를
            # 내지 않고 조용히 끝나서, 반환값만 보면 화면이 계속 "말하는 중"이다.
            if detector.speaking != was_speaking:
                await ws.send_json(
                    {"type": "speaking" if detector.speaking else "quiet"}
                )

            if detector.speaking and not busy and scorer.due(now):
                busy = True
                asyncio.create_task(run_score())

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("실시간 데모 처리 중 오류")


# 면접 하나에 소켓이 둘 붙을 수 있다 (2026-09-16, 앱 오너 요청).
#
# **왜 필요한가**: 앱은 2026-09-09 개편에서 영상을 WebRTC 로 보내게 바뀌어 얼굴
# JPEG 을 한 장도 안 보낸다. 서버는 WebRTC 미디어 경로에 없어서(백엔드는 신호만
# 중계한다) 그 영상을 볼 수 없다. 그런데 **담당자 방은 그 영상을 이미 받아 그리고
# 있다** — 거기서 프레임을 떠 보내면 서버 변경 없이 얼굴 신호가 살아난다.
#
# 문제는 소리다. 앱이 WebRTC 를 `audio: false` 로 열기 때문에(안드로이드가
# AudioRecord 를 하나만 준다) **담당자가 받는 스트림에는 소리가 없다.** 그래서
# 소리는 원본을 가진 앱이, 얼굴은 이미 받은 담당자가 보내야 한다.
#
# 소켓마다 `InterviewSession` 을 새로 만들면 그 둘이 **각자 반쪽만** 쥐게 된다 —
# 소리만 가진 세션은 `no_face`, 얼굴만 가진 세션은 `short_audio` 로 판정이 안 난다.
# 그래서 토큰 하나에 세션 하나를 두고 **둘이 같은 장부에 기여**하게 한다.
_SESSIONS: dict[str, InterviewSession] = {}
_SESSION_REFS: dict[str, int] = {}


def _acquire_session(token: str) -> InterviewSession:
    """이 토큰의 세션을 가져오거나 만든다. 붙은 소켓 수를 센다."""
    session = _SESSIONS.get(token)
    if session is None:
        session = InterviewSession(token)
        _SESSIONS[token] = session
    _SESSION_REFS[token] = _SESSION_REFS.get(token, 0) + 1
    return session


def _release_session(token: str) -> int:
    """소켓 하나가 빠졌다. **마지막 하나가 빠질 때만** 세션을 버린다.

    담당자가 방을 닫아도 지원자 면접은 계속돼야 하고, 그 반대도 마찬가지다.
    """
    left = _SESSION_REFS.get(token, 1) - 1
    if left <= 0:
        _SESSION_REFS.pop(token, None)
        _SESSIONS.pop(token, None)
        return 0
    _SESSION_REFS[token] = left
    return left


@app.websocket("/ws/interview/{token}")
async def interview(ws: WebSocket, token: str, role: str = "applicant"):
    """면접 소켓. 프로토콜은 PROTOCOL.md 가 원본이다.

    `role` 로 두 갈래다 (2026-09-16).

    - `applicant` (기본) — 지원자 기기. 소리를 보내고 질문을 받는다. 예전과 같다.
    - `recruiter` — 담당자 방. **얼굴 프레임만 보낸다.** 질문·답변 흐름에는
      끼지 않는다: 질문을 두 벌 보내면 담당자 화면이 지원자 화면 행세를 하게 되고,
      [답변 완료] 가 두 곳에서 눌리면 답변이 엉킨다.

    **미디어를 파일로 만들지 않는다.** 오디오는 발화 한 번 동안만 메모리에 있다가
    전사된 뒤 버려지고, 영상 프레임은 받는 즉시 신호로 바뀌고 사라진다.
    """
    await ws.accept()
    is_recruiter = role == "recruiter"
    session = _acquire_session(token)

    async with httpx.AsyncClient() as client:
        try:
            state = await fetch_state(client, token)
        except Exception:
            logger.exception("면접 상태 조회 실패: token=%s", token[:8])
            await ws.send_json({"type": "error", "message": "면접을 불러오지 못했습니다"})
            await ws.close()
            return

        if state.get("status") != "in_progress":
            # 시작·동의는 지원자 화면이 기존 REST 로 먼저 끝낸다. 여기서 또 하지 않는다 —
            # 규칙이 두 곳에 생기면 갈린다.
            await ws.send_json(
                {"type": "error", "message": "진행 중인 면접이 아닙니다", "status": state.get("status")}
            )
            await ws.close()
            return

        if is_recruiter:
            # 담당자 방은 **얼굴만 보낸다.** 질문 목록도, 이력서 사진도, 첫 질문도
            # 필요 없다 — 지원자 소켓이 이미 쥐고 있다. 여기서 또 받으면 같은 세션에
            # 두 번 써 넣는 꼴이고, 질문을 보내면 담당자 화면이 지원자 행세를 한다.
            logger.info(
                "면접 연결(담당자 얼굴): token=%s 붙은 소켓 %s개",
                token[:8], _SESSION_REFS.get(token, 1),
            )
            await ws.send_json({"type": "ready", "role": "recruiter"})
            await _pump(ws, client, session, token, is_recruiter=True)
            return

        # 질문 전체를 먼저 받아 둔다. 이게 있어야 전사를 안 기다리고 다음 질문을
        # 보낼 수 있다. 못 받으면 예전 방식(기다림)으로 돈다 — 면접은 어느 쪽이든 돈다.
        session.questions = await fetch_questions(client, token)
        # 이어서 들어온 경우 답한 데까지 건너뛴다 — 목록에는 답한 질문도 들어 있다.
        seq_now = state.get("question_seq")
        session.cursor = _cursor_of(session.questions, seq_now)
        logger.info(
            "면접 연결: token=%s 질문 %d개 · 지금 %s번",
            token[:8], len(session.questions), seq_now,
        )

        # 이력서 사진을 한 번 받아 둔다. **대조는 프레임이 들어올 때** 하고,
        # 실패하면 그냥 넘어간다 — 사진이 없다고 면접을 막지 않는다.
        session.reference = await fetch_reference(client, token)

        await ws.send_json(
            {
                "type": "question",
                "seq": state.get("question_seq"),
                "text": state.get("current_question"),
            }
        )

        await _pump(ws, client, session, token, is_recruiter=False)


async def _pump(
    ws, client, session: InterviewSession, token: str, *, is_recruiter: bool
) -> None:
    """소켓 하나에서 오는 것을 받아 넘긴다. 끝나면 세션 참조를 놓는다."""
    who = "담당자" if is_recruiter else "지원자"
    try:
        while True:
            msg = await ws.receive()

            if msg.get("type") == "websocket.disconnect":
                # **끊김을 남긴다** (2026-09-11). 세션 59 에서 폰에 "연결이 끊겨 다시
                # 잇는 중" 이 반복됐는데 서버 로그에 아무것도 없어 누가 끊었는지 못 갈랐다.
                # 1000·1001 은 앱이 닫은 것, 1006 은 망이 끊긴 것, 1011 은 서버가 버거운 것
                logger.info(
                    "면접 연결 끊김(%s): token=%s code=%s %s",
                    who, token[:8], msg.get("code"), _frame_tally(session),
                )
                break

            data = msg.get("bytes")
            if data:
                await _on_binary(ws, client, session, data, is_recruiter=is_recruiter)
                continue

            text = msg.get("text")
            if text:
                if is_recruiter:
                    # 담당자 방은 답변 흐름에 끼지 않는다 — [답변 완료] 가 두 곳에서
                    # 눌리면 같은 답변이 두 번 끝난다. ping 만 받아 준다.
                    if text.strip().startswith("{") and '"ping"' in text:
                        await ws.send_json({"type": "pong"})
                    continue
                await _on_text(ws, client, session, text)

    except WebSocketDisconnect:
        # 연결이 끊긴 것 자체는 오류가 아니다. 답변은 백엔드에 이미 저장돼 있고,
        # 지원자가 다시 들어오면 안 한 질문부터 이어진다.
        logger.info("면접 연결 종료(%s): token=%s %s", who, token[:8], _frame_tally(session))
    except Exception:
        logger.exception("면접 처리 중 오류(%s): token=%s", who, token[:8])
    finally:
        if not is_recruiter:
            # 전사 중에 나갔어도 **답변은 저장하고** 세션을 놓는다 — 여기는 아직
            # `interview` 의 `async with httpx.AsyncClient()` 안이라 클라이언트가 살아 있다.
            await wait_finish(session)
        left = _release_session(token)
        if left:
            logger.info("소켓 하나가 빠졌다 — 남은 %s개: token=%s", left, token[:8])


def _frame_tally(session: InterviewSession) -> str:
    """이 면접 하나의 프레임 장부를 로그 한 줄로 (2026-09-16, 앱 오너 요청).

    `/health` 의 `frames` 는 **프로세스 전역 누적**이라 면접이 겹치거나 컨테이너가
    다시 뜨면 어느 면접의 숫자인지 알 수 없다. 앱 화면의 「얼굴 N · 실패 M」 과
    나란히 놓고 **「앱이 안 보낸 것」과 「서버가 못 찾은 것」을 가르려면** 한 면접
    안의 숫자여야 한다. 토큰 앞 8자가 같은 줄에 있어 세션과 바로 짝지어진다.

    읽는 법: `recv` 는 소켓이 받은 장수(앱의 전송 수와 맞춰 본다) · `dropped_busy`
    는 서버가 앞 장을 보는 중이라 버린 것 · `in` 은 분석에 들어간 것 · `face` 는
    얼굴을 찾은 것. `recv=0` 이면 앱, `face=0` 인데 `in>0` 이면 서버 쪽이다.
    """
    s = session.frame_stats
    return (
        f"프레임 recv={s['recv']} 버림={s['dropped_busy']} "
        f"분석={s['in']} 얼굴={s['face']} 담당자중복버림={s.get('dropped_recruiter', 0)}"
    )


async def _on_binary(
    ws, client, session: InterviewSession, data: bytes, *, is_recruiter: bool = False
) -> None:
    kind, payload = data[0], data[1:]

    if is_recruiter and kind != KIND_VIDEO:
        # 담당자 방이 보내는 소리는 **무음이다.** 앱이 WebRTC 를 `audio: false` 로
        # 열어(안드로이드가 AudioRecord 를 하나만 준다) 담당자가 받는 스트림에는
        # 소리 트랙이 없다. 그걸 받아 두면 지원자 목소리에 무음이 섞여 전사가
        # 망가진다 — 얼굴만 받는다.
        return

    if kind == KIND_VIDEO:
        # **얼굴 출처는 한 면접에 하나** (2026-09-17, 민아님 제안 (가)). 웹 지원자
        # 면접에서는 지원자 페이지와 담당자 방이 같은 얼굴을 둘 다 보낸다 — 받으면
        # `recv` 가 두 배가 되고 같은 순간이 판정 창에 두 번 들어간다. 지원자 것이
        # 원본이라 그쪽이 살아 있으면 담당자 것은 버리고, 따로 센다(`recv` 에 안 든다).
        now = time.monotonic()
        if not is_recruiter:
            session.applicant_video_at = now
        elif now - session.applicant_video_at < iw.APPLICANT_VIDEO_FRESH_SEC:
            iw.FRAME_STATS["dropped_recruiter"] += 1
            session.frame_stats["dropped_recruiter"] += 1
            return

        # **받은 즉시 센다.** `add_frame` 안에서 세면 아래 `face_busy` 로 버린 것이
        # "안 온 것"과 구별되지 않는다 — 2026-09-10 실측에서 `in=0` 을 보고도
        # 앱이 안 보낸 것인지 서버가 버린 것인지 갈리지 않았다.
        iw.FRAME_STATS["recv"] += 1
        session.frame_stats["recv"] += 1

        # `/ws/live` 와 같은 이유로 스레드에서, 도는 중이면 버린다 (`add_frame` 의
        # FRAME_STRIDE 는 그 안에서 그대로 적용된다). 프레임 하나가 mediapipe 를
        # 두 번(특징 + 얼굴 대조) 타므로 이벤트 루프에서 부르면 오디오까지 늦는다.
        if session.face_busy:
            iw.FRAME_STATS["dropped_busy"] += 1
            session.frame_stats["dropped_busy"] += 1
        if not session.face_busy:
            session.face_busy = True

            async def extract() -> None:
                try:
                    identity = await asyncio.to_thread(session.add_frame, payload)
                    # 동일인 판단이 방금 정해졌으면 담당자에게 민다 (면접당 한 번)
                    if identity is not None:
                        await push_identity(client, session.token, identity)
                except Exception:
                    logger.exception("얼굴 추출 실패: token=%s", session.token[:8])
                finally:
                    session.face_busy = False

            asyncio.create_task(extract())
        return

    if kind != KIND_AUDIO:
        return

    # **끝난 면접은 더 듣지 않는다** (2026-09-16, 앱 오너 보고). 지원자 쪽이 소켓을
    # 안 닫으면 — 앱이 「면접 종료」 뒤에도 마이크를 놓지 않거나, 웹 탭을 그냥
    # 열어 두면 — 서버가 끝난 세션을 계속 판정한다. 실측에서 `scored` 가 10초에
    # 하나씩 올랐고 그 전부가 `no_face` 라 통계까지 흐려졌다.
    #
    # **소켓만 믿지 않는다.** 지원자 화면이 종료를 백엔드로 직접 보내는 경로도
    # 있어서(면접 종료 버튼), 이쪽은 아무 통지를 못 받는다. 그래서 주기적으로
    # 백엔드에 상태를 물어 스스로 닫는다.
    if session.done:
        return
    _schedule_done_check(client, session)

    event = session.add_audio(payload)

    # 끝내는 중(전사 대기)에는 소리를 **버퍼에만 쌓는다** — 다음 답변의 앞부분이다.
    # `listening` 을 보내면 화면이 "정리하는 중" 에서 "듣고 있습니다" 로 튀고, 상한도
    # 이미 끝내는 중이라 다시 끊을 것이 없다. 전에는 소켓이 막혀 있어 이 조각들이
    # 전사 뒤에야 처리됐다 — 이제 바로 받으니 여기서 같은 결과로 맞춘다.
    if session.finishing:
        return

    # 말하는 동안 판정을 굴려 담당자에게 민다. 답변이 끝날 때까지 기다리지 않는다 —
    # 담당자는 **면접 중에** 봐야 한다. 지원자 소켓으로는 보내지 않는다(ADR-0029).
    if (
        not session.scoring
        and not session.transcribing
        and session.due_for_verdict(time.monotonic())
    ):
        session.scoring = True
        asyncio.create_task(_live_verdict(client, session))

    if event == "begin":
        await ws.send_json({"type": "listening"})
        return
    if event == "limit":
        # 답변 하나가 상한(MAX_ANSWER_SEC)을 넘었다 — 버튼 없이 이어지니 여기서 끊는다
        if not session.finishing:
            iw.ANSWER_STATS["by_limit"] += 1
            await _finish_answer(ws, client, session)
        return
    # 멈춤('end')으로는 아무것도 하지 않는다 (2026-09-15). 09-11 판은 여기서 끝부분을
    # 받아써 "이상입니다" 를 찾았는데, 그 전사가 무음에 "이상입니다" 를 지어내 답변을
    # 강제로 끊었다(세션 77). 답변 끝은 [답변 완료](`_on_text` 의 "end")와 상한뿐이다.



def _cursor_of(questions: list[dict], seq: int | None) -> int:
    """`seq` 번 질문의 자리. 번호가 없거나 목록에 없으면 **끝**으로 둔다.

    예전에는 못 찾으면 0(첫 질문)으로 갔다. 그러면 지원자가 이미 답한 1번을 다시
    보고, 다시 한 답은 원래 답과 부딪혀 버려졌다(2026-09-11). 끝에 두면 번호 없이
    저장돼 백엔드가 "지금 질문" 에 넣고, 다음 차례에 목록을 다시 받아 맞춘다.
    """
    if seq is None:
        return len(questions)
    return next((i for i, q in enumerate(questions) if q["seq"] == seq), len(questions))


async def _refresh_questions(client, session: InterviewSession) -> dict | None:
    """질문 목록과 "지금 질문" 을 다시 받아 맞춘다. 남은 질문이 없으면 None."""
    try:
        questions = await fetch_questions(client, session.token)
        if not questions:
            return None
        state = await fetch_state(client, session.token)
    except Exception:
        logger.exception("질문 목록 다시 받기 실패: token=%s", session.token[:8])
        return None
    if state.get("status") != "in_progress":
        return None
    session.questions = questions
    session.cursor = _cursor_of(questions, state.get("question_seq"))
    if session.cursor < len(questions):
        return questions[session.cursor]
    return None


async def _finish_answer(ws, client, session: InterviewSession) -> None:
    """답변 하나를 끝낸다 — **한 번만, 그리고 소켓을 막지 않고.**

    끝내는 길이 둘이라(버튼 · 상한) 겹칠 수 있고, 끝내는 동안 전사를 기다리므로
    그 사이 버튼 연타도 여기로 온다. 두 번째는 버린다 — 그렇지 않으면 방금 비운
    버퍼의 몇 조각이 같은 질문의 두 번째 답이 되어 "말이 들리지 않았어요" 가 뜬다.

    **전사는 뒤에서 돌리고 이 함수는 바로 돌아간다** (2026-10-13). 전에는 여기서
    전사를 기다렸는데, 그동안 `_pump` 가 `receive()` 를 못 부른다. uvicorn
    (websockets-sansio) 은 앱이 읽지 않는 동안 소켓 읽기를 멈추므로 브라우저가
    보내는 keepalive pong 도 못 읽고, `ws_ping_timeout`(20초) 뒤 `1011 keepalive
    ping timeout` 으로 끊는다. 운영 서버는 2 vCPU 로컬 전사라 답변 하나에 30~100초
    — [답변 완료] 뒤 20~40초에 지원자 소켓이 죽고, 웹은 "정리하는 중" 에 멈춰
    있었다(10-13 실측 5건 전부 · 다음 질문을 보내려다 `WebSocketDisconnect`).
    같은 uvicorn 으로 재현: 읽기를 멈추면 38초에 1011, 태스크로 돌리면 45초 뒤 정상.

    소리는 **버튼 시점까지** 를 이 답변으로 잡는다(`take_answer` 를 여기서 바로
    부른다). 태스크가 도는 동안 들어오는 소리는 버퍼에 쌓여 다음 답변이 된다 —
    전에 전사 뒤에 처리되던 조각과 같은 운명이다.
    """
    if session.finishing:
        return
    session.finishing = True
    pcm, rows = session.take_answer()
    seq = session.current_seq()
    session.finish_task = asyncio.create_task(
        _finish_in_background(ws, client, session, pcm, rows, seq)
    )


async def _finish_in_background(
    ws, client, session: InterviewSession, pcm: bytes, rows: list, seq: int | None
) -> None:
    """`_end_answer` 를 태스크로 감싼다 — 예외를 삼키되 로그로 남기고 표시를 푼다."""
    try:
        await _end_answer(ws, client, session, pcm, rows, seq)
    except WebSocketDisconnect:
        # 전사하는 사이 지원자가 나갔다. 저장은 보내기 전에 끝나므로 답변은 남아
        # 있고, 다시 들어오면 안 한 질문부터 이어진다.
        logger.info(
            "답변을 끝내는 사이 지원자 소켓이 닫혔다: token=%s seq=%s",
            session.token[:8], seq,
        )
    except Exception:
        logger.exception("답변 끝내기 실패: token=%s seq=%s", session.token[:8], seq)
    finally:
        session.finishing = False
        session.finish_task = None


async def wait_finish(session: InterviewSession) -> None:
    """돌고 있는 끝내기가 있으면 기다린다.

    소켓이 빠질 때 `_pump` 가 부른다 — 지원자가 전사 중에 나가도 **답변은
    저장돼야** 하고, 그 저장이 쓰는 `httpx` 클라이언트는 `interview` 핸들러가
    돌아가면 닫히기 때문이다(10-11 운영 로그의 "client has been closed" 가 그 꼴).
    테스트도 같은 이유로 쓴다.
    """
    task = session.finish_task
    if task is not None and task is not asyncio.current_task():
        await task


async def _end_answer(
    ws, client, session: InterviewSession, pcm: bytes, rows: list, seq: int | None
) -> None:
    """말이 끝났다 — **받아쓴 뒤에** 넘긴다 (2026-09-15 개정).

    09-11 판은 "답했다" 부터 찍고 다음 질문을 먼저 보낸 뒤 전사를 뒤에서 돌렸다.
    CPU whisper 가 45~180초라 지원자를 못 기다리게 한 것인데, 그 순서에서는 전사가
    비면 그 칸이 빈칸으로 남고 질문은 이미 소비돼 있어 앞에서 VAD 로 걸러야 했다 —
    그 VAD 가 앱 소리를 자주 "목소리 0초" 로 봐서 실제 답변이 계속 튕겼다(09-15).

    전사가 API 로 옮겨(ADR-0038) 짧은 답은 1~3초, 3분 답도 ~20초라 기다릴 만하다.
    그래서 **판단은 받아쓴 글 하나로** 한다: 글이 있으면 저장하고 넘기고, 없으면
    같은 질문에 다시 답하게 한다. 소리를 재는 게이트는 두지 않는다.

    `pcm`·`rows`·`seq` 는 `_finish_answer` 가 버튼 시점에 떼어 준 것이다.
    """
    seconds = len(pcm) / (iw.SAMPLE_RATE * iw.SAMPLE_WIDTH)

    await ws.send_json({"type": "processing"})
    # 전사가 도는 동안 판정을 쉰다 (`InterviewSession.transcribing` 주석)
    session.transcribing = True
    try:
        pcm = await _drop_other_voice(session, pcm)
        transcript = strip_end_phrase(
            await transcribe_async(pcm, hint_of(session.questions))
        )
    finally:
        session.transcribing = False

    if not transcript:
        iw.ANSWER_STATS["empty"] += 1
        logger.info(
            "전사가 비어 답변으로 세지 않는다: token=%s seq=%s 소리 %.1f초",
            session.token[:8], seq, seconds,
        )
        # **거른 소리를 버리지 않는다** (소연님 지적, 2026-09-11). 작게라도 말했다면
        # 다시 말한 것과 합쳐 한 답이 되게 버퍼 앞에 되돌린다. 확인하는 사이 새로
        # 들어온 소리가 있으면 그 앞에 붙는다.
        session.audio[:0] = [pcm]
        session.frames[:0] = rows
        await ws.send_json(
            {"type": "retry", "message": "말이 들리지 않았어요. 다시 답변해 주세요"}
        )
        return

    iw.ANSWER_STATS["saved"] += 1
    logger.info(
        "전사 끝: token=%s seq=%s 소리 %.1f초 · %d자",
        session.token[:8], seq, seconds, len(transcript),
    )

    # **받아쓰지 못했으면 음성이라도 남긴다** (2026-09-16). 자리표시자만 저장하면
    # 지원자가 한 말이 어디에도 없다 — 세션 75 가 그랬다(ADR-0038). 담당자가
    # 나중에 「다시 받아쓰기」를 누르면 이 음성으로 글을 채운다.
    #
    # **실패해도 면접은 그대로 간다** — 못 남기면 지금까지와 같은 상태일 뿐이라
    # 여기서 답변 저장을 막으면 잃는 것이 오히려 커진다.
    if iw.is_placeholder(transcript):
        try:
            key = await iw.preserve_audio(client, session.token, seq, pcm)
            logger.info(
                "전사 실패 — 음성을 남겼다: token=%s seq=%s key=%s",
                session.token[:8], seq, key,
            )
        except Exception:
            logger.exception(
                "음성 보존 실패: token=%s seq=%s — 자리표시자만 남는다",
                session.token[:8], seq,
            )
    signal = session.signal(rows)
    if signal:
        logger.info("표정 신호: token=%s %s", session.token[:8], signal)

    # "답했다" 표시를 저장보다 먼저 남긴다 (2026-09-11 d960f9f) — 재접속이 그 사이
    # 지원자를 이미 답한 질문으로 되돌리지 않게. 못 남겨도 저장되면 답한 것이 된다.
    if seq is not None:
        try:
            await mark_answered(client, session.token, seq)
        except Exception:
            logger.exception("답함 표시 실패: token=%s seq=%s", session.token[:8], seq)
    try:
        state = await submit_answer(client, session.token, transcript, seq)
    except Exception:
        # 저장이 안 됐으면 넘기지 않는다 — 소리를 되돌리고 다시 답하게 한다.
        # 넘겨 버리면 그 답은 어디에도 없다.
        logger.exception("답변 저장 실패: token=%s seq=%s", session.token[:8], seq)
        session.audio[:0] = [pcm]
        session.frames[:0] = rows
        await ws.send_json(
            {"type": "retry", "message": "답변을 저장하지 못했어요. 다시 답변해 주세요"}
        )
        return

    if not session.questions:
        # 질문 목록을 못 받은 경우(서비스 토큰 없음·조회 실패) — 백엔드가 준
        # "지금 질문" 을 그대로 쓴다
        if isinstance(state, dict) and state.get("current_question"):
            await ws.send_json(
                {
                    "type": "question",
                    "seq": state.get("question_seq"),
                    "text": state.get("current_question"),
                }
            )
            return
        await _close(ws, client, session)
        return

    nxt = session.advance()
    if nxt is None:
        # 꼬리질문은 전사가 저장된 뒤에야 백엔드가 만들어 붙이므로 시작 때 받아 둔
        # 목록에는 없다 — 목록을 다시 본다
        nxt = await _refresh_questions(client, session)
    if nxt:
        await ws.send_json(
            {"type": "question", "seq": nxt["seq"], "text": nxt["question"]}
        )
        return
    await _close(ws, client, session)


async def _close(ws, client, session: InterviewSession) -> None:
    """남은 질문이 없다 — 세션을 닫고 지원자에게 알린다."""
    try:
        await finish_interview(client, session.token)
    except Exception:
        logger.exception("면접 종료 처리 실패: token=%s", session.token[:8])
    # **여기서부터는 더 듣지 않는다** (2026-09-16). 지원자 쪽이 소켓을 안 닫아도
    # 판정이 계속 돌지 않게 표시부터 남긴다 — 소켓을 닫는 것은 클라이언트 몫이라
    # 우리가 기다릴 수 없다.
    session.done = True
    await ws.send_json({"type": "done"})


# 끝났는지 백엔드에 다시 물어보는 간격. 면접 하나가 보통 10~20분이라 1분이면
# 늦어도 1분 안에 멈춘다. 공개 조회 경로라 가볍다.
DONE_CHECK_SEC = 60.0


def _schedule_done_check(client, session: InterviewSession) -> None:
    """끝났는지 확인을 **뒤에서** 돌린다. 소리 처리를 막지 않는다.

    이 확인은 HTTP 한 번이라 최악이면 10초를 기다린다. 소리 경로에서 그대로
    기다리면 그동안 들어온 조각이 밀려 답변이 늦게 끝난다.
    """
    now = time.monotonic()
    if now - session.last_done_check < DONE_CHECK_SEC:
        return
    session.last_done_check = now
    asyncio.create_task(_check_done(client, session))


async def _check_done(client, session: InterviewSession) -> None:
    """이 면접이 **다른 경로로** 끝났으면 `session.done` 을 세운다 (2026-09-16).

    지원자 화면의 [면접 종료] 는 백엔드로 바로 간다 — 이 소켓은 통지를 못 받는다.
    그 뒤에도 마이크가 흐르면 서버는 끝난 세션을 계속 판정한다(앱 오너 실측:
    종료 뒤에도 `scored` 가 10초에 하나씩, 전부 `no_face`).

    **못 물어보면 계속 듣는다.** 망이 흔들린다고 면접을 끊으면 잃는 것이 더 크다.
    """
    try:
        r = await client.get(
            f"{iw.BACKEND_URL}/api/v1/public/interview/{session.token}", timeout=10
        )
        r.raise_for_status()
        status = (r.json() or {}).get("status")
    except Exception:
        logger.warning("면접 상태 확인 실패: token=%s", session.token[:8])
        return

    if status == "in_progress":
        return

    session.done = True
    logger.info(
        "다른 경로로 끝난 면접이라 판정을 멈춘다: token=%s status=%s %s",
        session.token[:8], status, _frame_tally(session),
    )


async def _drop_other_voice(session: InterviewSession, pcm: bytes) -> bytes:
    """등록한 지원자 목소리가 **아닌** 구간을 전사에서 뺀다 (2026-09-11).

    "말을 했는데 인식을 못 하고, 주변 소음이 텍스트로 들어간다" 는 신고에서 왔다.
    방마다 조용한 정도가 달라 소리 크기로는 가를 수 없으니 주인으로 가른다.

    **전사 대기줄 안에서 돈다.** 지원자는 이미 다음 질문을 받은 뒤라 여기서 몇 초
    더 써도 기다리지 않는다 — 답변이 끝나는 자리(`_end_answer`)에 두면 #138 로
    없앤 기다림이 그대로 돌아온다.

    잘못될 때는 **아무것도 안 자른 상태로** 떨어지게 돼 있다. 모델이 없어도,
    지문을 못 떠도, 답변이 통째로 남처럼 보여도 원본을 그대로 돌려준다.
    """
    # 모델이 있나는 여기서 안 본다 — 처음 보는 순간 84MB 를 읽느라 1초쯤 멈추는데,
    # 이 대기줄은 이벤트 루프 위라 그동안 이 워커의 **다른 면접까지** 같이 멈춘다.
    # 없으면 `enroll` 이 None 을 내고 아래로 안 내려간다.
    if not VOICE_GATE or session.voice_off:
        return pcm

    if session.voiceprint is None:
        # 첫 등록. 3초 넘게 이어 말한 대목이 나올 때까지 답변마다 다시 시도한다.
        session.voiceprint = await asyncio.to_thread(speaker_match.enroll, pcm)
        if session.voiceprint is not None:
            iw.ANSWER_STATS["voice_enrolled"] += 1
            logger.info("목소리 등록: token=%s", session.token[:8])
        return pcm

    kept, dropped, all_other = await asyncio.to_thread(
        speaker_match.filter_other, pcm, session.voiceprint
    )

    if all_other:
        # 답변 하나가 통째로 남의 것일 리는 드물다 — 등록이 잘못됐을 때가 더 흔하다
        # (첫 답변에 담당자 목소리나 TV 가 섞여 그게 지문이 된 경우). 연달아 나오면
        # 지금 답변으로 다시 뜬다. 다시 떠도 또 어긋나면 그때는 접는다.
        session.voice_strikes += 1
        if session.voice_strikes < VOICE_STRIKES:
            return pcm
        session.voice_strikes = 0
        fresh = None if session.voice_reenrolled else (
            await asyncio.to_thread(speaker_match.enroll, pcm)
        )
        if fresh is None:
            session.voice_off = True
            iw.ANSWER_STATS["voice_disabled"] += 1
            logger.warning("목소리 대조를 접는다: token=%s", session.token[:8])
        else:
            session.voiceprint = fresh
            session.voice_reenrolled = True
            iw.ANSWER_STATS["voice_reenrolled"] += 1
            logger.info("목소리를 다시 등록했다: token=%s", session.token[:8])
        return pcm

    session.voice_strikes = 0
    if dropped:
        iw.ANSWER_STATS["other_voice"] += 1
        logger.info("남의 목소리 %.1f초를 뺐다: token=%s", dropped, session.token[:8])
    return kept


async def _live_verdict(client, session: InterviewSession) -> None:
    """최근 4초를 판정해 백엔드로 민다. 실패해도 면접에는 영향이 없다."""
    try:
        _live_stats["scored"] += 1
        pcm, rows, frame = session.scorer.snapshot()
        # 판정은 CPU 로 약 185ms 걸린다. 이벤트 루프에서 부르면 그 동안 이 워커의
        # **모든 면접**이 멈춘다 — 워커가 하나뿐이라 더 그렇다.
        # frame 이 있고 VIT_MODEL 이 켜져 있으면 표정 top-3 도 붙는다.
        result = await asyncio.to_thread(
            score, pcm, rows, session.scorer.window_sec, frame
        )
        if not result.get("ok"):
            # 얼굴이 모자라거나 소리가 짧다. **조용히 넘어가되 세어는 둔다** —
            # 담당자 화면이 비어 있을 때 여기가 원인인지 알아야 한다
            #
            # **이유별로 나눠 센다** (2026-09-10). `ok` 가 0 이라는 것만으로는
            # 얼굴 문제인지 소리 문제인지 밖에서 못 갈라, 앱 프레임이 누워 있던
            # 진짜 원인을 찾는 데 실측 두 번이 들었다. 서버 로그를 볼 수 없는
            # 사람이 `/ai/health` 만으로 갈릴 수 있어야 한다.
            reason = result.get("reason") or ""
            if "얼굴" in reason:
                _live_stats["no_face"] += 1
            else:
                _live_stats["short_audio"] += 1
            logger.info("판정 못 냄: token=%s %s", session.token[:8], reason)
            return
        _live_stats["ok"] += 1
        payload = {
            "truth_pct": result["truth_pct"],
            "lie_pct": result["lie_pct"],
            "window_sec": session.scorer.window_sec,
            "signals": result.get("signals", []),
        }
        if result.get("expressions"):
            payload["expressions"] = result["expressions"]
        # 목소리 지표 (2026-09-11). 백엔드 `VerdictIn` 이 extra 를 허용해 그대로 넘어간다
        if result.get("voice"):
            payload["voice"] = result["voice"]
        await push_verdict(
            client,
            session.token,
            payload,
        )
        _live_stats["pushed"] += 1
    except Exception:
        _live_stats["push_failed"] += 1
        logger.exception("실시간 판정 전송 실패: token=%s", session.token[:8])
    finally:
        session.scoring = False


async def _on_text(ws, client, session: InterviewSession, text: str) -> None:
    try:
        msg = json.loads(text)
    except json.JSONDecodeError:
        return
    kind = msg.get("type")
    if kind == "ping":
        await ws.send_json({"type": "pong"})
    elif kind == "end":
        # 지원자가 [답변 완료] 를 눌렀다 (PROTOCOL.md). 2026-09-15 부터 답변을 끝내는
        # 길은 이것(과 상한)뿐이다 — 침묵으로도 "이상입니다" 로도 넘어가지 않는다.
        if session.finishing:
            return  # 이미 끝내는 중(전사 대기 포함) — 버튼을 연타한 것
        if session.force_end():
            iw.ANSWER_STATS["by_button"] += 1
            await _finish_answer(ws, client, session)
        else:
            await ws.send_json(
                {"type": "retry", "message": "말이 들리지 않았어요. 다시 답변해 주세요"}
            )
