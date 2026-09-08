"""실시간 면접 — 지원자 화면과 이 워커를 잇는 WebSocket (AI면접 설계 §5-4 개정판).

**녹음해서 올리는 방식이 아니다.** 카메라·마이크가 면접 내내 켜진 채로 흐르고,
지원자가 말을 마치면 워커가 그것을 알아채 다음 질문을 보낸다. 그래야
다시 찍기가 없고(그 자리의 반응), 본인 확인이 끊기지 않는다(ADR-0029).

## 왜 오디오를 PCM 으로 받는가

브라우저의 `MediaRecorder` 는 webm/opus 를 낸다. 그것으로 발화 끝을 알아내려면
매번 디코딩해야 하고, 디코딩은 실시간 예산(1.5초)을 갉아먹는다. Web Audio API 로
**16kHz 16-bit mono PCM** 을 그대로 보내면 발화 감지가 산술만으로 끝난다.

## 왜 백엔드 API 를 그대로 쓰는가

세션 상태·질문·전사는 이미 백엔드에 있다(`/public/interview/{token}`).
워커가 DB 를 직접 보면 같은 규칙이 두 곳에 생긴다 — 만료 판정, 순서 규칙,
동의 검사가 갈린다. 워커는 **미디어만 맡고** 나머지는 백엔드에 묻는다.
"""

from __future__ import annotations

import json
import logging
import os
import time

import numpy as np

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("ARDA_BACKEND_URL", "http://api:8000").rstrip("/")

# 지원자가 보내는 오디오 형식. 클라이언트와 맞춰야 하는 값이라 바꾸면 프로토콜 문서도 같이 고친다.
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # 16-bit

# ── 발화 끝 판정 ──────────────────────────────────────────────
# 사람이 문장 중간에 쉬는 시간과 말을 마친 시간을 가르는 값이다. 짧게 잡으면 말하는
# 도중에 끊고 들어가고, 길게 잡으면 대화가 늘어진다. 0.8초는 사람 면접관이 다음을
# 묻기 시작하는 감각에 맞춘 값이고, 실측으로 조정할 자리다.
SILENCE_END_SEC = 0.8
# 이보다 조용하면 무음으로 본다. 마이크·환경에 따라 달라서 절대값으로 두지 않고
# 접속 초반의 배경 소음에서 기준을 잡는다(`_SpeechDetector`).
NOISE_MARGIN = 2.5
# 이 길이 아래는 답변으로 보지 않는다 — 기침·문 닫는 소리로 질문이 넘어가면 안 된다.
MIN_SPEECH_SEC = 0.7
# 아무리 길어도 여기서 끊는다. 무제한이면 워커 한 자리가 영영 잡힌다.
MAX_SPEECH_SEC = 180

# 표정은 매 프레임 보지 않는다. 초당 몇 장이면 신호가 충분하고, 그 이상은 CPU 만 쓴다.
FRAME_STRIDE = 3

# ── 말하는 동안 굴러가는 판정 ──────────────────────────────────
# 한 번 판정할 때 보는 최근 구간. 짧으면 피치·MFCC 통계가 표본 부족으로 튀고,
# 길면 방금 한 말이 앞의 말에 묻힌다. 4초는 문장 하나가 대체로 들어가는 길이다.
LIVE_WINDOW_SEC = 4.0
# 갱신 주기. 창 4초를 1초마다 보므로 같은 소리를 네 번 겹쳐 보는 셈이고,
# 그래서 값이 한 프레임에 튀지 않는다. 측정상 한 번에 약 185ms 걸린다.
LIVE_EVERY_SEC = 1.0
# 모델을 학습시킬 때 쓴 표본율. 마이크는 16kHz 로 보내므로 판정 직전에 맞춘다 —
# 어긋난 채로 MFCC 를 뽑으면 모델이 통째로 다른 값을 보게 된다.
TRAIN_SR = 22_050


def _rms(pcm: bytes) -> float:
    """조각의 소리 크기. `audioop` 은 Python 3.13 에서 빠졌고, numpy 로 같은 값을 낸다."""
    if len(pcm) < SAMPLE_WIDTH:
        return 0.0
    # 홀수 바이트로 잘려 오면 마지막 반 샘플을 버린다
    usable = len(pcm) - (len(pcm) % SAMPLE_WIDTH)
    samples = np.frombuffer(pcm[:usable], dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


class _SpeechDetector:
    """말이 끝났는지 판정한다.

    임계값을 고정하지 않는 이유: 지원자마다 마이크와 방 소음이 다르다. 접속 직후
    조용한 구간에서 배경 소음을 재고, 그 몇 배를 넘으면 말하는 것으로 본다.
    """

    def __init__(self) -> None:
        self._noise = None
        self._calib: list[float] = []
        self._speaking = False
        self._silence_started: float | None = None
        self._speech_started: float | None = None

    @property
    def speaking(self) -> bool:
        return self._speaking

    def feed(self, pcm: bytes) -> str | None:
        """오디오 조각 하나. 반환: 'begin' · 'end' · None."""
        if not pcm:
            return None
        level = _rms(pcm)
        now = time.monotonic()

        # 접속 초반 0.5초쯤을 배경 소음으로 삼는다
        if self._noise is None:
            self._calib.append(level)
            if len(self._calib) < 8:
                return None
            self._noise = max(50.0, float(np.median(self._calib)))
            return None

        loud = level > self._noise * NOISE_MARGIN

        if loud:
            self._silence_started = None
            if not self._speaking:
                self._speaking = True
                self._speech_started = now
                return "begin"
            if now - (self._speech_started or now) > MAX_SPEECH_SEC:
                return self._finish()
            return None

        if not self._speaking:
            return None
        if self._silence_started is None:
            self._silence_started = now
            return None
        if now - self._silence_started >= SILENCE_END_SEC:
            return self._finish()
        return None

    def _finish(self) -> str | None:
        # **말이 멈춘 시점까지만 잰다.** `now` 로 재면 뒤따른 침묵이 발화 길이에
        # 섞여, 기침 0.1초 + 침묵 0.9초가 1초짜리 답변으로 둔갑한다.
        # 상한(MAX_SPEECH_SEC)으로 끊는 경우는 아직 말하는 중이라 침묵 시작이 없다.
        ended = self._silence_started or time.monotonic()
        spoke = ended - (self._speech_started or ended)
        self._speaking = False
        self._silence_started = None
        self._speech_started = None
        # 너무 짧으면 답변으로 세지 않는다. 잡음이었다고 보고 계속 듣는다.
        return "end" if spoke >= MIN_SPEECH_SEC else None


def face_row_of_jpeg(jpeg: bytes) -> list | None:
    """JPEG 한 장 → 얼굴 특징 7개. 얼굴이 없거나 못 읽으면 None. 약 2ms."""
    import cv2

    buf = np.frombuffer(jpeg, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return None
    from feature_extractor import face_row

    return face_row(img)


class InterviewSession:
    """연결 하나. 미디어를 받아 신호를 만들고, 질문은 백엔드에서 가져온다."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.detector = _SpeechDetector()
        self.audio: list[bytes] = []
        self.frames: list = []
        self._frame_count = 0

    # ── 받기 ────────────────────────────────────────────────
    def add_audio(self, pcm: bytes) -> str | None:
        self.audio.append(pcm)
        return self.detector.feed(pcm)

    def add_frame(self, jpeg: bytes) -> None:
        """영상 프레임. **모으지 않고 그때그때 본다** — 쌓아 두면 그게 곧 저장이다."""
        self._frame_count += 1
        if self._frame_count % FRAME_STRIDE:
            return
        row = face_row_of_jpeg(jpeg)
        if row is not None:
            self.frames.append(row)

    # ── 답변 하나가 끝났을 때 ─────────────────────────────────
    def take_answer(self) -> tuple[bytes, list]:
        """모아 둔 것을 꺼내고 비운다. 다음 답변은 처음부터 다시 센다."""
        pcm = b"".join(self.audio)
        rows = self.frames
        self.audio = []
        self.frames = []
        return pcm, rows

    def signal(self, rows: list) -> dict | None:
        """표정 신호. 프레임이 너무 적으면 내지 않는다 — 없는 것이 틀린 것보다 낫다."""
        if len(rows) < 5:
            return None
        arr = np.array(rows)
        return {
            "frames": len(rows),
            "eye_openness": round(float(arr[:, :2].mean()), 4),
            "blink_variation": round(float(arr[:, :2].std()), 4),
            "head_movement": round(float(arr[:, 6].std()), 4),
            "asymmetry": round(float(arr[:, 5].mean()), 4),
        }


_model = None


def model():
    """`model.pkl` 을 한 번만 읽는다. 파일 분석(`/analyze`)과 실시간이 같은 것을 본다."""
    global _model
    if _model is None:
        import pathlib
        import pickle

        _model = pickle.loads(
            (pathlib.Path(__file__).parent / "model.pkl").read_bytes()
        )
    return _model


def score(pcm: bytes, rows: list, seconds: float) -> dict:
    """음성 조각 + 얼굴 행들 → 판정.

    **모자란 재료를 0 으로 채우지 않는다.** 파일 경로는 음성이 없으면 `zeros(86)`
    을 넣는데, 그건 "분석 못 했다"를 "특징이 전부 0 인 사람"으로 바꿔 놓는 짓이다.
    실시간에서는 판정을 미루는 편이 틀린 숫자를 내는 것보다 낫다 — 그래서
    안 되는 이유를 그대로 돌려준다.
    """
    import librosa

    from feature_extractor import extract_audio_from_array, face_signals

    if len(rows) < 5:
        return {"ok": False, "reason": "얼굴이 잘 안 보여요"}

    usable = len(pcm) - (len(pcm) % SAMPLE_WIDTH)
    y16 = np.frombuffer(pcm[:usable], dtype=np.int16).astype(np.float32) / 32768.0
    if y16.size < SAMPLE_RATE:
        return {"ok": False, "reason": "소리가 아직 짧아요"}

    y = librosa.resample(y16, orig_sr=SAMPLE_RATE, target_sr=TRAIN_SR)
    audio = extract_audio_from_array(y, TRAIN_SR)
    if audio is None:
        return {"ok": False, "reason": "소리가 아직 짧아요"}

    arr = np.array(rows)
    visual = np.concatenate([arr.mean(axis=0), arr.std(axis=0)])
    feat = np.concatenate([audio, visual]).reshape(1, -1)

    m = model()
    proba = m.predict_proba(feat)[0]
    return {
        "ok": True,
        "pred": int(m.predict(feat)[0]),
        "truth_pct": round(float(proba[0]) * 100, 1),
        "lie_pct": round(float(proba[1]) * 100, 1),
        "signals": face_signals(arr, seconds),
    }


class LiveScorer:
    """최근 몇 초만 들고 있다가 주기적으로 판정한다.

    **쌓아 두지 않는다** — 창 밖으로 나간 소리와 얼굴은 버린다. 면접 하나가 끝날
    때까지 모아 두면 그게 곧 녹화이고, ADR-0029 는 영상을 저장하지 않기로 했다.
    """

    def __init__(self, window_sec: float = LIVE_WINDOW_SEC) -> None:
        self.window_sec = window_sec
        self._max_bytes = int(window_sec * SAMPLE_RATE * SAMPLE_WIDTH)
        self._pcm = bytearray()
        self._rows: list[tuple[float, list]] = []
        self._last_scored = 0.0

    def add_audio(self, pcm: bytes) -> None:
        self._pcm += pcm
        if len(self._pcm) > self._max_bytes:
            del self._pcm[: len(self._pcm) - self._max_bytes]

    def add_face(self, row: list, now: float) -> None:
        self._rows.append((now, row))
        cutoff = now - self.window_sec
        self._rows = [r for r in self._rows if r[0] >= cutoff]

    def due(self, now: float) -> bool:
        if now - self._last_scored < LIVE_EVERY_SEC:
            return False
        self._last_scored = now
        return True

    def snapshot(self) -> tuple[bytes, list]:
        return bytes(self._pcm), [row for _, row in self._rows]


async def fetch_state(client, token: str) -> dict:
    r = await client.get(f"{BACKEND_URL}/api/v1/public/interview/{token}", timeout=10)
    r.raise_for_status()
    return r.json()


async def submit_answer(client, token: str, transcript: str) -> dict:
    r = await client.post(
        f"{BACKEND_URL}/api/v1/public/interview/{token}/answer",
        json={"transcript": transcript},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def transcribe(pcm: bytes) -> str:
    """음성 → 글.

    **아직 비어 있다.** faster-whisper 는 백엔드 `app/agent/stt.py` 에 이미 있고
    모델이 1.5GB 라 이 이미지에 또 넣으면 같은 것이 두 곳에 생긴다. GPU 서버가
    준비되면 그쪽에서 채운다 — 그때까지 이 함수만 갈아 끼우면 된다.

    빈 문자열을 돌려주면 백엔드가 답변을 저장하지 못하므로, 지금은 자리표시자를
    보내 흐름(질문 → 답변 → 다음 질문)이 도는지 확인할 수 있게 한다.
    """
    seconds = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)
    return f"[전사 미구현 · 발화 {seconds:.1f}초]"
