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
import threading
import time
from collections import deque

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
# 배경 소음에서 기준을 잡는다(`_SpeechDetector`).
NOISE_MARGIN = 2.5
# 보정에 쓸 조각 수(50ms 단위). 0.5초쯤이면 방 소음의 중앙값이 잡힌다.
CALIB_CHUNKS = 10
# **이보다 작은 값은 소리로 세지 않는다.** 폰은 `getUserMedia` 직후 첫 버퍼들을
# 0 으로 주는데, 그것으로 바닥값을 잡으면 임계값이 125 로 앉아 생활 소음에도
# 계속 "말하는 중"이 된다(2026-09-08 운영 실측).
MIN_NOISE = 50.0
# 바닥값을 다시 잡을 때 보는 최근 조각 수(50ms × 40 = 2초)와 백분위.
# 하위 백분위라 창에 말소리가 섞여도 조용한 쪽이 바닥으로 남는다.
NOISE_WINDOW = 40
NOISE_PERCENTILE = 25
# 소리가 한 번도 안 내려갈 때 바닥값을 조각마다 올리는 비율(50ms 당 0.4% = 초당 8%).
# 진짜 말은 낱말 사이에서 내려가 이 값이 쌓이지 않는다. 쌓이는 것은 바닥값이
# 잘못 잡혀 생활 소음을 말로 보고 있을 때뿐이고, 그때 몇 초 만에 빠져나온다.
NOISE_CREEP = 1.004
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

# ── 전사 (ADR-0032) ──────────────────────────────────────────
# **비어 있으면 꺼진 채로 돈다.** 설정을 넣어야 켜지는 것이 팀 방식이고, GPU 가
# 꺼져 있는 대부분의 시간에 1GB 짜리 모델을 물고 있을 이유가 없다.
#   켤 때: STT_MODEL=large-v3-turbo  (GPU 면 STT_DEVICE=cuda STT_COMPUTE_TYPE=float16)
STT_MODEL = os.getenv("STT_MODEL", "").strip()
# **`auto` 로 두지 않는다.** GPU 가 보이면 CUDA 를 고르는데, CUDA 런타임이 없는
# 기계에서는 모델을 올린 뒤 첫 전사에서야 `cublas64_12.dll not found` 로 터진다.
# 켜야 할 곳에서 명시하는 편이 낫다.
STT_DEVICE = os.getenv("STT_DEVICE", "cpu")
STT_COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", "default")
# 면접은 한국어다. 빈 값이면 whisper 가 스스로 알아내지만 그만큼 느리고, 짧은
# 발화에서는 엉뚱한 언어로 새기도 한다.
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "ko")
# 1 이면 탐색을 안 한다. 실시간이라 정확도보다 지연이 중요하다.
STT_BEAM_SIZE = int(os.getenv("STT_BEAM_SIZE", "1"))


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

    임계값을 고정하지 않는 이유: 지원자마다 마이크와 방 소음이 다르다. 그래서
    배경 소음을 재서 그 몇 배를 넘으면 말하는 것으로 본다.

    ## 접속 초반만 재면 안 된다 (2026-09-08 운영 실측)

    폰으로 돌렸더니 **질문 1에서 안 넘어갔다.** 화면이 "듣고 있습니다"에 멈추고
    `transcript` 가 전부 `null` 이었다(woojeongalex 보고, 세션 4).

    원인은 **보정 구간이 마이크 예열에 걸린 것**이다. `getUserMedia` 직후 첫
    버퍼들이 0 으로 오는 일이 폰에서 흔한데, 그 0 들만 보고 바닥값을 잡으면
    `max(50, 0) = 50` 이 되어 임계값이 **125** 로 앉는다. 그 뒤 진짜 생활 소음
    (int16 기준 수백)이 들어오면 **`loud` 가 영영 참**이라 침묵 판정이 시작조차
    되지 않는다. 상한(180초)으로만 끊긴다.

    그래서 두 가지를 바꿨다.

    1. **무음 조각은 보정에 넣지 않는다** — 예열 버퍼에 걸리지 않게
    2. **바닥값을 계속 따라가게 한다** — 조용한 구간이 나올 때마다 갱신하므로
       방 소음이 달라져도, 처음 보정이 틀렸어도 스스로 회복한다

    임계값 숫자를 올려서 해결하지 않은 이유: 그러면 이번엔 목소리가 작은
    지원자를 못 잡는다. 어느 쪽으로도 짐작하지 않으려면 바닥값이 따라가야 한다.
    """

    def __init__(self) -> None:
        self._noise: float | None = None
        self._calib: list[float] = []
        self._recent: deque[float] = deque(maxlen=NOISE_WINDOW)
        self._speaking = False
        self._silence_started: float | None = None
        self._speech_started: float | None = None
        self._logged = 0.0

    @property
    def speaking(self) -> bool:
        return self._speaking

    @property
    def noise(self) -> float | None:
        """지금 바닥값. 로그·시험에서 본다."""
        return self._noise

    def _relevel(self, level: float, now: float) -> None:
        """조용한 값들로 바닥값을 다시 잡는다.

        하위 백분위를 쓴다 — 창 안에 말소리가 섞여 있어도 조용한 쪽이 바닥이다.
        """
        self._recent.append(level)
        if len(self._recent) < NOISE_WINDOW:
            return
        floor = float(np.percentile(self._recent, NOISE_PERCENTILE))
        # 예열 무음(0 근처)만 담긴 창으로 바닥을 내리지 않는다
        if floor >= MIN_NOISE:
            self._noise = floor
        if now - self._logged >= 10:
            self._logged = now
            logger.debug("소리 기준: 바닥 %.0f · 임계 %.0f", self._noise, self._noise * NOISE_MARGIN)

    def feed(self, pcm: bytes) -> str | None:
        """오디오 조각 하나. 반환: 'begin' · 'end' · None."""
        if not pcm:
            return None
        level = _rms(pcm)
        now = time.monotonic()

        # 접속 초반. **무음은 세지 않는다** — 마이크가 아직 안 켜진 구간이다.
        if self._noise is None:
            if level >= MIN_NOISE:
                self._calib.append(level)
            if len(self._calib) < CALIB_CHUNKS:
                return None
            self._noise = max(MIN_NOISE, float(np.median(self._calib)))
            logger.info("소리 기준 잡음: 바닥 %.0f · 임계 %.0f",
                        self._noise, self._noise * NOISE_MARGIN)
            return None

        loud = level > self._noise * NOISE_MARGIN

        # 말하고 있지 않은 동안의 값이 곧 배경 소음이다. 이것이 처음 보정이
        # 틀렸을 때의 회복 경로다.
        if not loud and not self._speaking:
            self._relevel(level, now)

        if loud:
            # **갇힘 탈출.** 소리가 한 번도 내려가지 않으면 그건 말이 아니라
            # 바닥값이 낮게 잡힌 것이다 — 진짜 말은 낱말 사이에서 반드시 내려간다.
            # 조용해질 때까지 기다리는 위 갱신은 이 상태에서 영영 돌지 않으므로,
            # 여기서 바닥값을 조금씩 올려 스스로 빠져나온다. `level / NOISE_MARGIN`
            # 로 상한을 두어 지나치게 올라가지 않는다(올린 순간 조용으로 바뀐다).
            if self._speaking:
                self._noise = min(self._noise * NOISE_CREEP, level / NOISE_MARGIN)

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


async def finish_interview(client, token: str) -> None:
    """면접을 닫는다. **`done` 을 보내는 쪽이 부른다.**

    안 부르면 세션이 `in_progress` 로 남아 담당자 화면에서 "아직 보는 중"과
    "끝난 것"이 구별되지 않는다(2026-09-08 woojeongalex 보고, 세션 4).
    질문이 떨어진 것을 아는 쪽이 여기이므로 여기서 닫는 것이 자연스럽다.

    실패해도 면접 진행에는 영향이 없다 — 지원자는 이미 다 답했다.
    """
    r = await client.post(
        f"{BACKEND_URL}/api/v1/public/interview/{token}/finish", timeout=10
    )
    r.raise_for_status()


async def submit_answer(client, token: str, transcript: str) -> dict:
    r = await client.post(
        f"{BACKEND_URL}/api/v1/public/interview/{token}/answer",
        json={"transcript": transcript},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


_stt = None
_stt_lock = threading.Lock()


def _stt_model():
    """faster-whisper 모델. 처음 부를 때 한 번만 올린다(수십 초 · ~1GB).

    락은 로드 구간만 감싼다 — 두 요청이 동시에 들어와 모델을 두 번 올리면
    메모리가 두 배로 든다.
    """
    global _stt
    if _stt is None:
        with _stt_lock:
            if _stt is None:
                from faster_whisper import WhisperModel

                logger.info("전사 모델 로딩: %s (%s)", STT_MODEL, STT_DEVICE)
                _stt = WhisperModel(
                    STT_MODEL, device=STT_DEVICE, compute_type=STT_COMPUTE_TYPE
                )
    return _stt


def transcribe(pcm: bytes) -> str:
    """음성 → 글. **CPU 로 약 0.55배**(35초 음성에 19초) 걸리므로 스레드에서 부른다.

    `STT_MODEL` 이 비어 있으면 꺼진 채로 자리표시자를 돌려준다 — 팀이 쓰는 방식
    그대로다(설정을 안 넣으면 켜지지 않는다). GPU 가 꺼져 있는 대부분의 시간에
    1GB 를 물고 있을 이유가 없다(ADR-0032).

    **말이 안 담겼으면 빈 문자열을 돌려준다.** 기침이나 잡음을 답변으로 저장하면
    그 질문은 답한 것이 되어 다시 물어볼 길이 없어진다.
    """
    seconds = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)
    if not STT_MODEL:
        return f"[전사 꺼짐 · 발화 {seconds:.1f}초]"

    usable = len(pcm) - (len(pcm) % SAMPLE_WIDTH)
    audio = np.frombuffer(pcm[:usable], dtype=np.int16).astype(np.float32) / 32768.0

    segments, _ = _stt_model().transcribe(
        audio,
        language=STT_LANGUAGE or None,
        beam_size=STT_BEAM_SIZE,
        # **whisper 는 무음에 말을 지어낸다.** 실측: 무음 3초·잡음 3초 모두
        # "감사합니다." 를 냈다. 그대로 두면 기침이 답변으로 저장되고 그 질문은
        # 답한 것이 되어 다시 물어볼 길이 없어진다. VAD 로 말이 없는 구간을
        # 먼저 잘라내면 낼 조각 자체가 없어진다.
        vad_filter=True,
        # 앞 조각을 참고하면 한 번 지어낸 말이 뒤로 번진다. 답변마다 새로 시작한다.
        condition_on_previous_text=False,
    )
    return " ".join(s.text.strip() for s in segments).strip()
