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

from feature_extractor import analyze_timeseries, extract_features
from interview_ws import (
    InterviewSession,
    LiveScorer,
    _SpeechDetector,
    face_row_of_jpeg,
    fetch_state,
    finish_interview,
    model,
    score,
    submit_answer,
    transcribe,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
DEMO_HTML = (_HERE / "demo.html").read_text(encoding="utf-8")

# 뜰 때 한 번 읽어 둔다. 모델이 없거나 깨졌으면 첫 요청이 아니라 지금 죽는 편이 낫다.
model()

app = FastAPI(title="Arda 거짓말 탐지")


@app.get("/health")
def health():
    return {"status": "ok"}


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
                row = face_row_of_jpeg(payload)
                if row is not None:
                    scorer.add_face(row, now)
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
                    await _on_text(ws, session, text)

        except WebSocketDisconnect:
            # 연결이 끊긴 것 자체는 오류가 아니다. 답변은 백엔드에 이미 저장돼 있고,
            # 지원자가 다시 들어오면 안 한 질문부터 이어진다.
            logger.info("면접 연결 종료: token=%s", token[:8])
        except Exception:
            logger.exception("면접 처리 중 오류: token=%s", token[:8])


async def _on_binary(ws, client, session: InterviewSession, data: bytes) -> None:
    kind, payload = data[0], data[1:]

    if kind == KIND_VIDEO:
        session.add_frame(payload)
        return

    if kind != KIND_AUDIO:
        return

    event = session.add_audio(payload)
    if event == "begin":
        await ws.send_json({"type": "listening"})
        return
    if event != "end":
        return

    # 말이 끝났다 — 전사하고 다음 질문을 받아 온다
    await ws.send_json({"type": "processing"})
    pcm, rows = session.take_answer()
    # 전사는 CPU 로 발화 길이의 절반쯤 걸린다. 이벤트 루프에서 부르면 그 동안
    # 이 워커의 모든 면접이 멈춘다 — 워커가 하나뿐이라 더 그렇다.
    transcript = await asyncio.to_thread(transcribe, pcm)

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


async def _on_text(ws, session: InterviewSession, text: str) -> None:
    try:
        msg = json.loads(text)
    except json.JSONDecodeError:
        return
    if msg.get("type") == "ping":
        await ws.send_json({"type": "pong"})
