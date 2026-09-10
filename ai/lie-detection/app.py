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
from feature_extractor import analyze_timeseries, extract_features
from interview_ws import (
    SERVICE_TOKEN,
    STT_MODEL,
    InterviewSession,
    LiveScorer,
    _SpeechDetector,
    face_row_of_jpeg,
    fetch_state,
    finish_interview,
    push_verdict,
    model,
    score,
    submit_answer,
    transcribe_async,
    warm_stt,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            row = await asyncio.to_thread(face_row_of_jpeg, jpeg)
            if row is not None:
                scorer.add_face(row, at)
        except Exception:
            logger.exception("얼굴 추출 실패")
        finally:
            face_busy = False

    async def run_score() -> None:
        nonlocal busy
        try:
            pcm, rows = scorer.snapshot()
            # 판정은 CPU 로 약 185ms 걸린다. 여기서 그냥 부르면 그 동안 이 워커의
            # **모든 연결**이 멈춘다 — 워커가 하나뿐이라 더 그렇다.
            result = await asyncio.to_thread(score, pcm, rows, scorer.window_sec)
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


@app.websocket("/ws/interview/{token}")
async def interview(ws: WebSocket, token: str):
    """지원자 화면과 이어지는 연결. 프로토콜은 PROTOCOL.md 가 원본이다.

    **미디어를 파일로 만들지 않는다.** 오디오는 발화 한 번 동안만 메모리에 있다가
    전사된 뒤 버려지고, 영상 프레임은 받는 즉시 신호로 바뀌고 사라진다.
    """
    await ws.accept()
    session = InterviewSession(token)

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

        await ws.send_json(
            {
                "type": "question",
                "seq": state.get("question_seq"),
                "text": state.get("current_question"),
            }
        )

        try:
            while True:
                msg = await ws.receive()

                if msg.get("type") == "websocket.disconnect":
                    break

                data = msg.get("bytes")
                if data:
                    await _on_binary(ws, client, session, data)
                    continue

                text = msg.get("text")
                if text:
                    await _on_text(ws, client, session, text)

        except WebSocketDisconnect:
            # 연결이 끊긴 것 자체는 오류가 아니다. 답변은 백엔드에 이미 저장돼 있고,
            # 지원자가 다시 들어오면 안 한 질문부터 이어진다.
            logger.info("면접 연결 종료: token=%s", token[:8])
        except Exception:
            logger.exception("면접 처리 중 오류: token=%s", token[:8])


async def _on_binary(ws, client, session: InterviewSession, data: bytes) -> None:
    kind, payload = data[0], data[1:]

    if kind == KIND_VIDEO:
        # `/ws/live` 와 같은 이유로 스레드에서, 도는 중이면 버린다 (`add_frame` 의
        # FRAME_STRIDE 는 그 안에서 그대로 적용된다).
        if not session.face_busy:
            session.face_busy = True

            async def extract() -> None:
                try:
                    await asyncio.to_thread(session.add_frame, payload)
                except Exception:
                    logger.exception("얼굴 추출 실패: token=%s", session.token[:8])
                finally:
                    session.face_busy = False

            asyncio.create_task(extract())
        return

    if kind != KIND_AUDIO:
        return

    event = session.add_audio(payload)

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
    if event != "end":
        return
    await _finish_answer(ws, client, session)


async def _finish_answer(ws, client, session: InterviewSession) -> None:
    """말이 끝났다 — 전사하고 다음 질문을 받아 온다.

    침묵 감지(`feed` 의 `end`)와 지원자의 [답변 완료](`{"type":"end"}`, 2026-09-09)
    가 같은 길을 탄다 — 끝을 누가 정했든 그 뒤는 같아야 한다.
    """
    await ws.send_json({"type": "processing"})
    pcm, rows = session.take_answer()
    # 전사는 CPU 로 발화 길이의 절반쯤 걸린다. 이벤트 루프에서 부르면 그 동안
    # 이 워커의 모든 면접이 멈춘다 — 워커가 하나뿐이라 더 그렇다.
    #
    # **전사가 도는 동안에는 판정을 쉰다** (2026-09-10 실측). 판정은 한 번에
    # 185ms 를 쓰는데 초당 한 번 돌아, 8.9초 발화의 전사가 45초 제한
    # (`STT_TIMEOUT_SEC`)을 넘겨 `[전사 지연]` 자리표시자가 저장됐다. 답변이
    # 통째로 날아가는 것보다 그 몇 초 판정을 거르는 편이 낫다 — 판정은 곁들이고
    # 답변은 면접 그 자체다. 지금 창에 든 것은 어차피 답변이 끝난 뒤의 방이다.
    session.transcribing = True
    try:
        transcript = await transcribe_async(pcm)
    finally:
        session.transcribing = False

    if not transcript:
        # 말이 안 담긴 것을 답변으로 저장하면 그 질문은 "답한 것"이 되어
        # 다시 물어볼 길이 없어진다. 저장하지 않고 같은 질문을 계속 듣는다.
        logger.info("전사 결과가 비어 답변으로 세지 않는다: token=%s", session.token[:8])
        await ws.send_json(
            {"type": "retry", "message": "말이 들리지 않았어요. 다시 답변해 주세요"}
        )
        return

    signal = session.signal(rows)
    if signal:
        # 신호는 로그로만 남긴다. 저장 자리(ADR-0029 결과 절)는 아직 스키마가 없다.
        logger.info("표정 신호: token=%s %s", session.token[:8], signal)

    try:
        state = await submit_answer(client, session.token, transcript)
    except Exception:
        logger.exception("답변 저장 실패: token=%s", session.token[:8])
        await ws.send_json({"type": "error", "message": "답변을 저장하지 못했습니다"})
        return

    if state.get("current_question"):
        await ws.send_json(
            {
                "type": "question",
                "seq": state.get("question_seq"),
                "text": state.get("current_question"),
            }
        )
    else:
        # **질문이 떨어졌으면 세션도 닫는다.** 안 닫으면 `in_progress` 로 남아
        # 담당자 화면에서 "아직 보는 중"과 "끝난 것"이 구별되지 않는다.
        try:
            await finish_interview(client, session.token)
        except Exception:
            # 지원자는 이미 다 답했다. 닫기에 실패했다고 화면에 오류를 띄우지 않는다.
            logger.exception("면접 종료 처리 실패: token=%s", session.token[:8])
        await ws.send_json({"type": "done"})


async def _live_verdict(client, session: InterviewSession) -> None:
    """최근 4초를 판정해 백엔드로 민다. 실패해도 면접에는 영향이 없다."""
    try:
        _live_stats["scored"] += 1
        pcm, rows = session.scorer.snapshot()
        # 판정은 CPU 로 약 185ms 걸린다. 이벤트 루프에서 부르면 그 동안 이 워커의
        # **모든 면접**이 멈춘다 — 워커가 하나뿐이라 더 그렇다.
        result = await asyncio.to_thread(score, pcm, rows, session.scorer.window_sec)
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
        await push_verdict(
            client,
            session.token,
            {
                "truth_pct": result["truth_pct"],
                "lie_pct": result["lie_pct"],
                "window_sec": session.scorer.window_sec,
                "signals": result.get("signals", []),
            },
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
        # 지원자가 [답변 완료] 를 눌렀다 (PROTOCOL.md). 침묵 3초를 기다리지 않는다 —
        # 바닥 소음이 높은 환경(WebRTC 가 마이크를 같이 잡는 앱)에선 그 3초가 거의
        # 안 나와 답변이 영영 안 넘어갔다(2026-09-09 실기기).
        if session.force_end():
            await _finish_answer(ws, client, session)
        else:
            await ws.send_json(
                {"type": "retry", "message": "말이 들리지 않았어요. 다시 답변해 주세요"}
            )
