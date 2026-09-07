"""거짓말 탐지 서비스.

두 가지를 낸다.
- `POST /analyze`            영상 파일 하나 → 판정 (담당자 확인·데모용)
- `WS  /ws/interview/{token}` 실시간 면접 (지원자용, ADR-0029)

Flask 가 아니라 FastAPI 인 이유는 WebSocket 때문이다. Flask 로 WS 를 하려면
gevent 계열 워커가 필요하고, 그러면 gunicorn 설정과 배포가 같이 복잡해진다.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import tempfile
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
    fetch_state,
    submit_answer,
    transcribe,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
model = pickle.load(open(_HERE / "model.pkl", "rb"))
DEMO_HTML = (_HERE / "demo.html").read_text(encoding="utf-8")

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
    pred = int(model.predict(feat2d)[0])
    proba = model.predict_proba(feat2d)[0]

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
    transcript = transcribe(pcm)

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
        await ws.send_json({"type": "done"})


async def _on_text(ws, session: InterviewSession, text: str) -> None:
    try:
        msg = json.loads(text)
    except json.JSONDecodeError:
        return
    if msg.get("type") == "ping":
        await ws.send_json({"type": "pong"})
