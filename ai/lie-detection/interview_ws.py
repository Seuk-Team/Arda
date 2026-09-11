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

import asyncio
import json
import logging
import os
import threading
import time
from collections import deque

import numpy as np

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("ARDA_BACKEND_URL", "http://api:8000").rstrip("/")
# 백엔드의 `/internal/*` 을 부를 때 쓰는 토큰. **없으면 판정을 안 보낸다** —
# 백엔드가 401 로 막으므로 부르면 매초 실패 로그만 쌓인다.
SERVICE_TOKEN = os.getenv("ARDA_SERVICE_TOKEN", "").strip()

# 지원자가 보내는 오디오 형식. 클라이언트와 맞춰야 하는 값이라 바꾸면 프로토콜 문서도 같이 고친다.
SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2  # 16-bit

# ── 발화 끝 판정 ──────────────────────────────────────────────
# 사람이 문장 중간에 쉬는 시간과 말을 마친 시간을 가르는 값이다.
#
# **손해가 한쪽으로만 크다.** 길게 잡으면 답을 마친 지원자가 그만큼 기다릴 뿐이지만,
# 짧게 잡으면 생각하느라 쉬는 도중에 끊고 들어가 **답변이 반토막으로 저장되고 되돌릴
# 수 없다.** 그래서 안전한 쪽으로 길게 잡는다.
#
# 처음 0.8초로 잡았던 것은 사람 면접관의 감각에 맞춘 짐작이었다. 면접에서 긴장한
# 사람이 "음…" 하고 쉬는 시간은 1~3초라 그 안에 잘린다. 3초는 그것을 덮는다.
#
# 실제 값은 폰 실측으로 정한다. 재배포 없이 바꿀 수 있게 환경변수로 열어 둔다.
SILENCE_END_SEC = float(os.getenv("SILENCE_END_SEC", "3.0"))
# 이보다 조용하면 무음으로 본다. 마이크·환경에 따라 달라서 절대값으로 두지 않고
# 배경 소음에서 기준을 잡는다(`_SpeechDetector`).
NOISE_MARGIN = 2.5
# 보정에 쓸 시간. 0.5초쯤이면 방 소음의 중앙값이 잡힌다.
#
# **조각 수가 아니라 초로 센다.** 전에는 "50ms 조각 10개"로 세어, 클라이언트가
# 다른 크기로 보내면 기준이 통째로 어긋났다. 실제로 앱(#104)이 이 값에 맞추려고
# 1600바이트로 다시 잘라 보내고 있었다 — 맞춰야 하는 쪽은 서버다.
CALIB_SEC = 0.5
# **이보다 작은 값은 소리로 세지 않는다.** 폰은 `getUserMedia` 직후 첫 버퍼들을
# 0 으로 주는데, 그것으로 바닥값을 잡으면 임계값이 125 로 앉아 생활 소음에도
# 계속 "말하는 중"이 된다(2026-09-08 운영 실측).
MIN_NOISE = 50.0
# 바닥값을 다시 잡을 때 보는 최근 구간과 백분위.
# 하위 백분위라 창에 말소리가 섞여도 조용한 쪽이 바닥으로 남는다.
NOISE_WINDOW_SEC = 2.0
NOISE_PERCENTILE = 25
# 소리가 한 번도 안 내려갈 때 바닥값을 올리는 비율(초당 8%).
# 진짜 말은 낱말 사이에서 내려가 이 값이 쌓이지 않는다. 쌓이는 것은 바닥값이
# 잘못 잡혀 생활 소음을 말로 보고 있을 때뿐이고, 그때 몇 초 만에 빠져나온다.
NOISE_CREEP_PER_SEC = 1.08
# 이 길이 아래는 답변으로 보지 않는다 — 기침·문 닫는 소리로 질문이 넘어가면 안 된다.
MIN_SPEECH_SEC = 0.7
# 아무리 길어도 여기서 끊는다. 무제한이면 워커 한 자리가 영영 잡힌다.
MAX_SPEECH_SEC = 180

# 표정은 매 프레임 보지 않는다. 초당 몇 장이면 신호가 충분하고, 그 이상은 CPU 만 쓴다.
FRAME_STRIDE = 3

# 이력서 사진과 대조할 때 볼 장 수. 한 장으로 정하지 않는다 — 눈 감은 장·흔들린 장이
# 걸리면 멀쩡한 지원자가 낮게 나온다. 다 보고 **가장 잘 맞은 값**으로 한 번만 정한다.
IDENTITY_FRAMES = 5

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
#   켤 때: STT_MODEL=large-v3-turbo
#   CPU (지금 프로덕션): STT_DEVICE 안 넣거나 cpu, STT_COMPUTE_TYPE 도 안 넣으면 int8 자동 (아래).
#   GPU 로 옮기면: STT_DEVICE=cuda · STT_COMPUTE_TYPE=float16
STT_MODEL = os.getenv("STT_MODEL", "").strip()
# **`auto` 로 두지 않는다.** GPU 가 보이면 CUDA 를 고르는데, CUDA 런타임이 없는
# 기계에서는 모델을 올린 뒤 첫 전사에서야 `cublas64_12.dll not found` 로 터진다.
# 켜야 할 곳에서 명시하는 편이 낫다.
STT_DEVICE = os.getenv("STT_DEVICE", "cpu")
# CPU 에서는 int8 로 간다. faster-whisper 의 "default" 는 CPU 에서 float32 라
# large-v3-turbo (809M) 로드 순간 3.0-3.8GB 를 잡아먹어 컨테이너를 죽인다
# (2026-09-09 dmesg OOM 실측·서버 5회 재현). int8 은 CT2 의 AVX-VNNI 최적화로
# 메모리 1/4, 속도 2.3배(로컬 실측), 한국어 정확도 손실은 무시할 수준(공식 WER
# 0.1-0.5%p·짧은 발화 육안 비교 0). GPU 로 옮길 때만 STT_COMPUTE_TYPE=float16
# 를 명시하면 되고, 그 외에는 이 자동값이 정답이다.
_default_compute_type = "int8" if STT_DEVICE == "cpu" else "default"
STT_COMPUTE_TYPE = os.getenv("STT_COMPUTE_TYPE", _default_compute_type)
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
        # (소리 크기, 그 조각의 길이[초]). 조각 크기가 달라도 창이 2초로 유지된다.
        self._recent: deque[tuple[float, float]] = deque()
        self._recent_sec = 0.0
        self._calib_sec = 0.0
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

    def _relevel(self, level: float, secs: float, now: float) -> None:
        """조용한 값들로 바닥값을 다시 잡는다.

        하위 백분위를 쓴다 — 창 안에 말소리가 섞여 있어도 조용한 쪽이 바닥이다.
        창은 **조각 수가 아니라 초**로 잡는다(`NOISE_WINDOW_SEC`).
        """
        self._recent.append((level, secs))
        self._recent_sec += secs
        while self._recent_sec > NOISE_WINDOW_SEC and len(self._recent) > 1:
            self._recent_sec -= self._recent.popleft()[1]
        if self._recent_sec < NOISE_WINDOW_SEC:
            return
        floor = float(np.percentile([lv for lv, _ in self._recent], NOISE_PERCENTILE))
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
        secs = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)
        now = time.monotonic()

        # 접속 초반. **무음은 세지 않는다** — 마이크가 아직 안 켜진 구간이다.
        if self._noise is None:
            if level >= MIN_NOISE:
                self._calib.append(level)
                self._calib_sec += secs
            if self._calib_sec < CALIB_SEC:
                return None
            self._noise = max(MIN_NOISE, float(np.median(self._calib)))
            logger.info("소리 기준 잡음: 바닥 %.0f · 임계 %.0f",
                        self._noise, self._noise * NOISE_MARGIN)
            return None

        loud = level > self._noise * NOISE_MARGIN

        # 말하고 있지 않은 동안의 값이 곧 배경 소음이다. 이것이 처음 보정이
        # 틀렸을 때의 회복 경로다.
        if not loud and not self._speaking:
            self._relevel(level, secs, now)

        if loud:
            # **갇힘 탈출.** 소리가 한 번도 내려가지 않으면 그건 말이 아니라
            # 바닥값이 낮게 잡힌 것이다 — 진짜 말은 낱말 사이에서 반드시 내려간다.
            # 조용해질 때까지 기다리는 위 갱신은 이 상태에서 영영 돌지 않으므로,
            # 여기서 바닥값을 조금씩 올려 스스로 빠져나온다. `level / NOISE_MARGIN`
            # 로 상한을 두어 지나치게 올라가지 않는다(올린 순간 조용으로 바뀐다).
            if self._speaking:
                self._noise = min(
                    self._noise * NOISE_CREEP_PER_SEC**secs, level / NOISE_MARGIN
                )

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

    def reset(self) -> None:
        """말 상태만 지운다 — 바닥값·보정은 그대로 (`InterviewSession.force_end`)."""
        self._speaking = False
        self._silence_started = None
        self._speech_started = None


def face_row_of_jpeg(jpeg: bytes) -> list | None:
    """JPEG 한 장 → 얼굴 특징 7개. 얼굴이 없거나 못 읽으면 None. 약 2ms."""
    import cv2

    buf = np.frombuffer(jpeg, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return None
    from feature_extractor import face_row

    return face_row(img)


# ── 프레임 방향 ────────────────────────────────────────────────
# **누운 얼굴은 못 찾는다.** 폰 카메라의 *스트림* 프레임은 센서 방향 그대로
# 나오는데(세로로 들면 90° 누움), 그 각도가 기기마다 다르고 앞 카메라는 좌우가
# 뒤집혀 있어 공식이 또 다르다. 2026-09-10 실측에서 앱 면접의 판정이 세 번에 걸쳐
# 전부 실패했고(`no_face`), 클라이언트에서 각도를 맞추려던 시도도 한 번 빗나갔다.
#
# **그래서 맞추는 쪽을 서버로 옮긴다.** 첫 얼굴을 찾을 때만 네 방향을 뒤져 보고,
# 찾은 각도를 그 면접 내내 쓴다. 기기가 바뀌어도 앱을 다시 굽지 않는다.
# (같은 판단을 소연님이 오디오 조각 크기에서 먼저 했다 — "맞춰야 하는 쪽은 서버".)
_ROTATIONS = (0, 270, 90, 180)

# 가장 최근에 확정된 각도. `/ai/health` 가 이 값을 낸다 — 앱을 영구히 고칠 때
# 짐작이 아니라 실측값으로 고치기 위한 것이다.
LAST_ROTATION: int | None = None

# 프레임이 어디까지 갔는가 (2026-09-10).
#
# **`no_face` 만으로는 두 가지가 구별되지 않는다** — 앱이 프레임을 안 보내는
# 것과, 보내는데 얼굴을 못 찾는 것. 오늘 그 둘을 못 갈라 회전 가설을 붙들고
# 두 번 헛돌았다. 도착·해독·검출을 따로 세면 그 자리에서 갈린다.
#
#   recv=0                 → 앱이 아예 안 보낸다 (카메라·구독 문제)
#   recv>0, in=0           → 다 버려졌다 (`face_busy` 가 안 풀린다)
#   in>0, decoded=0        → JPEG 이 깨졌다 (앱의 변환 문제)
#   decoded>0, face=0      → 그림은 멀쩡한데 얼굴을 못 찾는다 (흑백·크기·화질)
#
# `recv` 는 소켓이 받은 즉시(app.py `_on_binary`), `in` 은 분석에 들어간 것만 센다.
FRAME_STATS = {"recv": 0, "dropped_busy": 0, "in": 0, "decoded": 0, "face": 0}


def _rotated(img, degrees: int):
    """시계 방향으로 돌린다. 0 이면 원본 그대로 (복사도 하지 않는다)."""
    if not degrees:
        return img
    import cv2

    return cv2.rotate(
        img,
        {
            90: cv2.ROTATE_90_CLOCKWISE,
            180: cv2.ROTATE_180,
            270: cv2.ROTATE_90_COUNTERCLOCKWISE,
        }[degrees],
    )


def face_row_search(jpeg: bytes, known: int | None) -> tuple[list | None, int | None]:
    """얼굴을 찾을 때까지 방향을 바꿔 본다. 반환: (특징 7개, 그때 쓴 각도).

    **이미 찾은 각도가 있으면 그것만 본다.** 매 프레임 네 방향을 다 보면 CPU 가
    네 배로 들고, 그 CPU 는 전사가 써야 하는 것이다. 눈을 감았거나 흔들려서
    한 장이 실패하는 것은 흔한 일이라 그때마다 다시 뒤지지 않는다.
    """
    row, rot, _ = face_row_search_full(jpeg, known)
    return row, rot


def face_row_search_full(
    jpeg: bytes, known: int | None
) -> tuple[list | None, int | None, "np.ndarray | None"]:
    """`face_row_search` + 얼굴이 찾힌 회전 완료 BGR. 표정 판정용 (2026-09-10).

    성공 시 세 번째 값은 회전된 BGR 이미지 — feature_extractor 의 `_detect`·
    `expressions_from_frame` 이 그대로 받아서 쓸 수 있다. 실패 시 None.
    """
    import cv2

    buf = np.frombuffer(jpeg, dtype=np.uint8)
    img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if img is None:
        return None, known, None
    FRAME_STATS["decoded"] += 1
    from feature_extractor import face_row

    for rot in (known,) if known is not None else _ROTATIONS:
        rotated = _rotated(img, rot)
        row = face_row(rotated)
        if row is not None:
            FRAME_STATS["face"] += 1
            return row, rot, rotated
    return None, known, None


class InterviewSession:
    """연결 하나. 미디어를 받아 신호를 만들고, 질문은 백엔드에서 가져온다."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.detector = _SpeechDetector()
        self.audio: list[bytes] = []
        self.frames: list = []
        self._frame_count = 0
        # 말하는 동안 굴러가는 판정용. 답변이 끝날 때까지 기다리지 않는다 —
        # 담당자가 **면접 중에** 봐야 의미가 있다.
        self.scorer = LiveScorer()
        # 판정 하나가 도는 동안 또 시작하지 않게. 겹치면 CPU 만 쓰고 값은 같다.
        self.scoring = False
        # 이력서 사진의 얼굴 지문. 없으면 동일인 확인을 통째로 건너뛴다 —
        # 서식에 사진이 빠졌다고 지원자가 불이익을 받으면 안 된다.
        self.reference = None
        self._identity_scores: list[float] = []
        # 한 번 정해지면 안 바뀐다. 면접 내내 흔들리는 값이면 담당자가 못 읽는다.
        self.identity: dict | None = None
        # 얼굴 추출 하나가 스레드에서 도는 동안 또 시작하지 않게 (app.py `_on_binary`)
        self.face_busy = False
        # 이 면접의 프레임이 몇 도 누워 있는가. **처음 얼굴을 찾을 때 정해진다**
        # (`face_row_search`). None 이면 아직 안 정해진 것이고, 그동안만 네 방향을
        # 뒤진다.
        self.frame_rotation: int | None = None
        # 전사가 도는 동안 판정을 쉬게 하는 표시 (app.py `_transcribe_pump`).
        # 둘이 같은 CPU 를 다투면 전사가 45초 제한을 넘긴다 — 2026-09-10 실측.
        #
        # **#138 로 오히려 더 필요해졌다.** 전사가 대기줄로 빠지면서 지원자가
        # 다음 질문에 답하는 **동안** 뒤에서 돌기 때문에, 초당 판정과 겹치는
        # 시간이 예전보다 길다.
        self.transcribing = False
        # 질문 전체와 지금 몇 번째인가. 비어 있으면 예전 방식(전사를 기다림)으로 돈다.
        self.questions: list[dict] = []
        self.cursor = 0
        # 전사 대기줄. **지원자를 기다리게 하지 않으려고** 여기에 넣고 다음 질문을
        # 먼저 보낸다. 세션마다 하나라 한 사람의 답변은 낸 순서대로 저장된다.
        self.pending: asyncio.Queue = asyncio.Queue()

    # ── 받기 ────────────────────────────────────────────────
    def add_audio(self, pcm: bytes) -> str | None:
        self.audio.append(pcm)
        self.scorer.add_audio(pcm)
        return self.detector.feed(pcm)

    def add_frame(self, jpeg: bytes) -> dict | None:
        """영상 프레임. **모으지 않고 그때그때 본다** — 쌓아 두면 그게 곧 저장이다.

        동일인 판단이 이 프레임에서 정해졌으면 그것을 돌려준다(대개 None).
        """
        global LAST_ROTATION

        FRAME_STATS["in"] += 1
        self._frame_count += 1
        if self._frame_count % FRAME_STRIDE:
            return None
        row, rot, rotated_bgr = face_row_search_full(jpeg, self.frame_rotation)
        if row is not None:
            if self.frame_rotation is None:
                # 이 면접에서 처음 얼굴을 찾았다. 각도를 굳히고 밖에도 남긴다 —
                # 담당자 화면이 비어 있을 때 방향 탓인지 알 수 있어야 한다.
                self.frame_rotation = rot
                LAST_ROTATION = rot
                logger.info("프레임 방향 %s° 로 확정: token=%s", rot, self.token[:8])
            self.frames.append(row)
            now = time.monotonic()
            self.scorer.add_face(row, now)
            # 표정 판정용 BGR 도 남긴다 (2026-09-10, ADR-0032). VIT_MODEL 이 꺼져
            # 있으면 score() 가 무시하므로 남겨 두는 자체는 무해.
            if rotated_bgr is not None:
                self.scorer.add_frame(rotated_bgr)
        return self.check_identity(jpeg)

    def check_identity(self, jpeg: bytes) -> dict | None:
        """이력서 사진과 대조. 판단이 방금 정해졌으면 그것을 돌려준다.

        **가장 잘 맞은 장을 쓴다.** 낮게 나온 장을 골라 쓰면 각도·조명이 나쁜
        지원자가 의심받는데, 여기서 틀리면 되돌릴 데가 없다.

        판정(`verdict`)과 달리 **한 번만** 낸다. 신원은 면접 중에 바뀌는 값이
        아니고, 매초 흔들리면 담당자가 뭘 봐야 할지 알 수 없다.
        """
        if self.reference is None or self.identity is not None:
            return None

        import cv2

        import face_match

        img = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
        vec = face_match.embed(img) if img is not None else None
        if vec is None:
            return None

        self._identity_scores.append(face_match.similarity(self.reference, vec))
        if len(self._identity_scores) < IDENTITY_FRAMES:
            return None

        best = max(self._identity_scores)
        self.identity = {"match": face_match.verdict(best), "score": round(best, 3)}
        return self.identity

    # ── 질문 진행 ────────────────────────────────────────────
    def current_seq(self) -> int | None:
        """지금 답하고 있는 질문 번호. 목록이 없으면 None(번호 없이 저장한다)."""
        if self.cursor < len(self.questions):
            return self.questions[self.cursor]["seq"]
        return None

    def advance(self) -> dict | None:
        """다음 질문으로 넘긴다. 더 없으면 None.

        **전사를 기다리지 않는다.** 질문은 면접 시작 때 이미 다 받아 뒀고, 다음
        질문을 고르는 데 방금 한 말이 필요하지 않다 — 백엔드도 "아직 답 안 한
        가장 앞 질문"을 꺼내 줄 뿐이었다.
        """
        self.cursor += 1
        if self.cursor < len(self.questions):
            return self.questions[self.cursor]
        return None

    def due_for_verdict(self, now: float) -> bool:
        """지금 판정을 낼 때인가. **말하는 동안에만** 낸다 — 조용할 때 낸 값은
        지원자가 아니라 방을 보고 있는 것이다."""
        return self.detector.speaking and self.scorer.due(now)

    # ── 답변 하나가 끝났을 때 ─────────────────────────────────
    def take_answer(self) -> tuple[bytes, list]:
        """모아 둔 것을 꺼내고 비운다. 다음 답변은 처음부터 다시 센다."""
        pcm = b"".join(self.audio)
        rows = self.frames
        self.audio = []
        self.frames = []
        return pcm, rows

    def force_end(self) -> bool:
        """지원자가 [답변 완료] 를 눌렀다 — 침묵을 기다리지 않고 여기까지를 답변으로 끊는다.

        감지기 상태와 무관하다: 목소리가 작아 '말' 로 안 잡혔어도 버퍼에 소리가
        있으면 전사로 넘긴다(비면 전사가 빈 문자열을 내고 서버가 `retry` 를 보낸다).
        붙자마자 눌러 [MIN_SPEECH_SEC] 도 안 쌓였으면 답변으로 세지 않는다.
        바닥값은 남긴다 — 다음 답변도 같은 방이다.
        """
        seconds = sum(len(p) for p in self.audio) / (SAMPLE_RATE * SAMPLE_WIDTH)
        self.detector.reset()
        return seconds >= MIN_SPEECH_SEC

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


def score(pcm: bytes, rows: list, seconds: float, latest_frame=None) -> dict:
    """음성 조각 + 얼굴 행들 → 판정. 프레임이 있으면 표정 top-3 도 붙인다.

    **모자란 재료를 0 으로 채우지 않는다.** 파일 경로는 음성이 없으면 `zeros(86)`
    을 넣는데, 그건 "분석 못 했다"를 "특징이 전부 0 인 사람"으로 바꿔 놓는 짓이다.
    실시간에서는 판정을 미루는 편이 틀린 숫자를 내는 것보다 낫다 — 그래서
    안 되는 이유를 그대로 돌려준다.

    표정(`expressions`)은 판정 벡터에 들어가지 않는다. 판정 모델(`model.pkl`)이
    아직 100차원이라(ADR-0032 §정하지 못한 것 ③) 표정 7개는 지금 담당자 화면의
    라벨로만 흐른다 — 우리가 학습한 ViT 가 뭘 보고 있는지 근거를 남기는 자리다.

    목소리 지표(`voice`, 2026-09-11)는 판정 벡터 100개 중 86개인 목소리 특징을 사람이
    읽을 수 있게 다시 잰 것이다 — 벡터를 만든 같은 계산에서 나와 비용이 더 들지 않는다.
    """
    import librosa

    from feature_extractor import (
        expressions_from_frame,
        extract_audio_with_voice,
        face_signals,
    )

    if len(rows) < 5:
        return {"ok": False, "reason": "얼굴이 잘 안 보여요"}

    usable = len(pcm) - (len(pcm) % SAMPLE_WIDTH)
    y16 = np.frombuffer(pcm[:usable], dtype=np.int16).astype(np.float32) / 32768.0
    if y16.size < SAMPLE_RATE:
        return {"ok": False, "reason": "소리가 아직 짧아요"}

    y = librosa.resample(y16, orig_sr=SAMPLE_RATE, target_sr=TRAIN_SR)
    audio, voice = extract_audio_with_voice(y, TRAIN_SR)
    if audio is None:
        return {"ok": False, "reason": "소리가 아직 짧아요"}

    arr = np.array(rows)
    visual = np.concatenate([arr.mean(axis=0), arr.std(axis=0)])
    feat = np.concatenate([audio, visual]).reshape(1, -1)

    m = model()
    proba = m.predict_proba(feat)[0]

    # 표정: 프레임이 있고 VIT_MODEL 이 켜져 있을 때만. 실패해도 판정은 그대로 낸다.
    expressions: list | None = None
    if latest_frame is not None:
        try:
            expressions = expressions_from_frame(latest_frame, top_k=3)
        except Exception:
            logger.exception("표정 판정 실패 — 판정은 그대로 낸다")
            expressions = None

    out = {
        "ok": True,
        "pred": int(m.predict(feat)[0]),
        "truth_pct": round(float(proba[0]) * 100, 1),
        "lie_pct": round(float(proba[1]) * 100, 1),
        "signals": face_signals(arr, seconds),
        "voice": voice or {},
    }
    if expressions:
        out["expressions"] = expressions
    return out


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
        # ViT 표정용 최근 프레임 하나 (2026-09-10). 하나만 든다 — 쌓으면 그게 곧
        # 저장이고 ADR-0029 취지에 어긋난다. 매 판정마다 갱신되므로 오래 남지도 않는다.
        self._latest_frame: "np.ndarray | None" = None

    def add_audio(self, pcm: bytes) -> None:
        self._pcm += pcm
        if len(self._pcm) > self._max_bytes:
            del self._pcm[: len(self._pcm) - self._max_bytes]

    def add_face(self, row: list, now: float) -> None:
        self._rows.append((now, row))
        cutoff = now - self.window_sec
        self._rows = [r for r in self._rows if r[0] >= cutoff]

    def add_frame(self, bgr) -> None:
        """표정 판정용. 얼굴이 들어 있던 회전 완료 프레임만 넣는다."""
        self._latest_frame = bgr

    def due(self, now: float) -> bool:
        if now - self._last_scored < LIVE_EVERY_SEC:
            return False
        self._last_scored = now
        return True

    def snapshot(self):
        """(pcm, rows, latest_frame). 세 번째는 표정 판정에 쓰이고 없으면 None."""
        return bytes(self._pcm), [row for _, row in self._rows], self._latest_frame


async def fetch_state(client, token: str) -> dict:
    r = await client.get(f"{BACKEND_URL}/api/v1/public/interview/{token}", timeout=10)
    r.raise_for_status()
    return r.json()


async def push_verdict(client, token: str, verdict: dict) -> None:
    """실시간 판정을 백엔드로 민다. 백엔드가 담당자 화면에 나른다(#97 계약).

    **지원자 기기를 거치지 않는다.** 지원자 소켓으로 내려보내면 화면에 안 그려도
    개발자 도구를 열면 보이고, 거기서 ADR-0029 의 "지원자에게 판정을 보여 주지
    않는다"가 깨진다.

    `ARDA_SERVICE_TOKEN` 이 없으면 **부르지 않는다.** 백엔드가 401 로 막으므로
    부르면 매초 실패 로그만 쌓인다. 설정을 넣어야 켜지는 것이 팀 방식이다.

    받는 담당자가 없어도 백엔드는 204 로 조용히 끝낸다 — 재시도하지 않는다.
    """
    if not SERVICE_TOKEN:
        return
    r = await client.post(
        f"{BACKEND_URL}/api/v1/internal/interview/{token}/verdict",
        json=verdict,
        headers={"X-Service-Token": SERVICE_TOKEN},
        timeout=5,
    )
    r.raise_for_status()


async def fetch_reference(client, token: str):
    """이력서 사진 → 얼굴 지문. 없거나 못 가져오면 None (확인을 건너뛴다).

    **면접 시작 때 한 번만 받고 저장하지 않는다.** 지문은 메모리에만 두고 연결이
    끊기면 같이 사라진다 — 갈아 끼울 수 없는 생체정보라 남기면 지켜야 할 것이 는다.

    404 는 정상이다. 서식에 사진이 없는 지원서일 뿐이고, 그것 때문에 면접을 막지
    않는다. 실패도 마찬가지로 조용히 넘어간다.
    """
    if not SERVICE_TOKEN:
        return None
    try:
        r = await client.get(
            f"{BACKEND_URL}/api/v1/internal/interview/{token}/portrait",
            headers={"X-Service-Token": SERVICE_TOKEN},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        import face_match

        return await asyncio.to_thread(face_match.from_image_bytes, r.content)
    except Exception:
        logger.warning("이력서 사진을 못 받았다 — 동일인 확인을 건너뛴다", exc_info=True)
        return None


async def push_identity(client, token: str, identity: dict) -> None:
    """동일인 확인 결과를 백엔드로 민다 (`/internal/.../identity`).

    판정과 **다른 통로**로 보낸다 — 신원 확인은 참·거짓 판정이 아니고, 같은
    스트림에 섞으면 화면에서 거짓말 지표처럼 읽힌다.
    """
    if not SERVICE_TOKEN:
        return
    r = await client.post(
        f"{BACKEND_URL}/api/v1/internal/interview/{token}/identity",
        json=identity,
        headers={"X-Service-Token": SERVICE_TOKEN},
        timeout=5,
    )
    r.raise_for_status()


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


async def fetch_questions(client, token: str) -> list[dict]:
    """면접 질문 전체. **시작할 때 한 번** 받아 둔다.

    이게 있어야 전사를 안 기다리고 다음 질문을 보낼 수 있다 — 전에는 답변을
    저장해야 다음 질문이 나왔고, 저장하려면 전사가 끝나야 했다.

    서비스 토큰이 없으면 빈 목록이다. 그때는 예전처럼 전사를 기다린다.
    """
    if not SERVICE_TOKEN:
        return []
    try:
        r = await client.get(
            f"{BACKEND_URL}/api/v1/internal/interview/{token}/questions",
            headers={"X-Service-Token": SERVICE_TOKEN},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.warning("질문 목록을 못 받았다 — 전사를 기다리는 방식으로 돈다", exc_info=True)
        return []


async def mark_answered(client, token: str, seq: int) -> None:
    """이 질문에 답을 마쳤다고 백엔드에 **먼저** 남긴다 (2026-09-11).

    전사는 뒤에서 몇 분씩 걸려 끝난다. 그동안 "지금 질문" 이 안 넘어가 있으면
    재접속·앱의 확인 요청이 지원자를 **이미 답한 질문으로 되돌린다** — 시연에서
    Q9 에서 Q1 로 돌아가 다시 한 답이 409 로 버려졌다. 말이 끝난 순간 이것부터
    찍으면 "지금 질문" 이 바로 넘어가고, 전사는 나중에 같은 번호로 채운다.

    서비스 토큰이 없으면 아무것도 안 한다 — 그때는 전사가 저장될 때 답한 것이 된다.
    """
    if not SERVICE_TOKEN:
        return
    r = await client.post(
        f"{BACKEND_URL}/api/v1/internal/interview/{token}/turns/{seq}/answered",
        headers={"X-Service-Token": SERVICE_TOKEN},
        timeout=10,
    )
    r.raise_for_status()


async def submit_answer(client, token: str, transcript: str, seq: int | None = None) -> dict:
    """답변을 저장한다. `seq` 를 붙이면 그 질문 칸에만 들어간다.

    번호 없이 보내면 백엔드가 "아직 답 안 한 가장 앞 질문"에 넣는다 — 전사가
    뒤에서 도는 동안 다음 질문이 이미 나가 있으면 그 규칙은 한 칸씩 밀린다.
    """
    body: dict = {"transcript": transcript}
    if seq is not None:
        body["seq"] = seq
    r = await client.post(
        f"{BACKEND_URL}/api/v1/public/interview/{token}/answer",
        json=body,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


_stt = None
_stt_failed = False   # 한 번 실패하면 매 답변마다 다시 시도하지 않는다
_stt_lock = threading.Lock()
# **전사는 한 번에 하나만 돈다.** 서버가 2 vCPU 라 여럿을 같이 돌리면 서로 느려질
# 뿐 총 시간은 그대로다 — 실측: 30초 발화를 1명이면 37초, 4명 동시면 198초(1명당 50초).
# 줄 세우면 앞사람이 37초에 끝나고 뒤로 갈수록 밀리는데, 같이 돌리면 **모두가**
# 50초를 기다린다. 메모리도 동시 실행만큼 더 쓴다.
_stt_running = threading.Semaphore(1)


def _stt_model():
    """faster-whisper 모델. 처음 부를 때 한 번만 올린다(수십 초 · ~1GB).
    **못 올리면 None 을 돌려준다** — 면접을 끊지 않는다.

    락은 로드 구간만 감싼다 — 두 요청이 동시에 들어와 모델을 두 번 올리면
    메모리가 두 배로 든다.
    """
    global _stt, _stt_failed
    if _stt is not None or _stt_failed:
        return _stt
    with _stt_lock:
        if _stt is not None or _stt_failed:
            return _stt
        try:
            from faster_whisper import WhisperModel

            logger.info("전사 모델 로딩: %s (%s)", STT_MODEL, STT_DEVICE)
            _stt = WhisperModel(
                STT_MODEL, device=STT_DEVICE, compute_type=STT_COMPUTE_TYPE
            )
        except Exception:
            # **여기서 터뜨리면 면접이 끊긴다.** 설정이 잘못됐다는 이유로 지원자가
            # 면접을 못 보게 하지 않는다 — 자리표시자로 내려앉고 로그로 알린다.
            # 실제로 겪은 것들: 라이브러리 미설치 · `STT_DEVICE=cuda` 인데 이미지에
            # CUDA 런타임이 없음(`libcublas.so.12`) · 메모리 부족(`mkl_malloc`).
            # 셋 다 **첫 전사 시점**에야 드러나므로 배포 직후에는 안 보인다.
            _stt_failed = True
            logger.exception(
                "전사 모델을 올리지 못했다 — 자리표시자로 계속한다. model=%s device=%s",
                STT_MODEL, STT_DEVICE,
            )
    return _stt


# 전사 하나를 기다려 주는 한계. 넘으면 포기하고 자리표시자를 남긴다.
#
# **여기서 안 끊으면 면접이 거기서 멈춘다.** 답변이 저장되지 않아 다음 질문이
# 안 나오고, 그 사이 uvicorn 이 핑 응답을 못 받아 WebSocket 을 먼저 닫아 버린다
# (2026-09-09 실측: `processing` 뒤 40초 무응답 → `closed 1011`).
#
# **면접 답변은 3분까지 갈 수 있다** (2026-09-10 실측, Daniel Kim: 98초·63.8초
# 답변이 45초 상한을 넘겨 자리표시자 저장). CPU int8 실측 속도(약 1.8배속) 로
# 3분 발화가 100초 안에 처리되고, 여기에 여유 80초를 더한 180초로 상향한다.
# 이 시간에 다음 질문은 이미 나가 있으므로 지원자를 대기시키지 않는다 (전사가
# 뒤에서 도는 동안 다음 답변이 진행됨 — interview_ws submit_answer 흐름).
#
# GPU 로 옮기면 30~50배속이라 3분 답변도 ~5초에 끝난다. 그때는 상한을 다시
# 45초로 되돌려도 된다 — 짧게 두면 STT 스레드가 CPU 자원을 오래 잡지 않는다.
STT_TIMEOUT_SEC = float(os.getenv("STT_TIMEOUT_SEC", "180"))


def warm_stt() -> None:
    """전사 모델을 미리 올려 둔다. **첫 지원자가 로딩을 물지 않게.**

    `large-v3-turbo` 를 처음 올리는 데 CPU 로 약 26초 걸린다(suvisdev 실측).
    그 시간을 첫 답변이 물면, 답변이 저장되기 전에 WebSocket 이 먼저 죽는다 —
    2026-09-09 실기기에서 그렇게 면접이 첫 질문에서 멈췄다.

    **실패해도 서비스를 죽이지 않는다.** `model()`(판정 모델)은 없으면 뜰 때
    죽는 편이 낫지만, 전사는 없어도 면접이 돈다(자리표시자로 내려앉는다).
    """
    if not STT_MODEL:
        logger.info("전사 꺼짐 — 예열하지 않는다")
        return
    started = time.monotonic()
    try:
        if _stt_model() is None:
            logger.warning("전사 모델 예열 실패 — 자리표시자로 돈다")
            return
    except Exception:
        logger.exception("전사 모델 예열 중 오류 — 자리표시자로 돈다")
        return
    logger.info("전사 모델 예열 완료: %.1f초", time.monotonic() - started)


async def transcribe_async(pcm: bytes) -> str:
    """전사를 딴 스레드에서 하되 **[STT_TIMEOUT_SEC] 를 넘기면 포기한다.**

    포기하면 자리표시자를 돌려준다 — 빈 문자열이 아니다. 빈 문자열은 "말이 안
    담겼다" 는 뜻이라 서버가 답변을 저장하지 않고 다시 답하게 하는데, 시간이
    모자란 것은 지원자 잘못이 아니다. 저장하고 다음 질문으로 넘어가는 편이 낫다.
    """
    seconds = len(pcm) / (SAMPLE_RATE * SAMPLE_WIDTH)
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(transcribe, pcm), timeout=STT_TIMEOUT_SEC
        )
    except asyncio.TimeoutError:
        logger.warning(
            "전사가 %.0f초를 넘겨 포기한다 (발화 %.1f초)", STT_TIMEOUT_SEC, seconds
        )
        return f"[전사 지연 · 발화 {seconds:.1f}초]"


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

    model = _stt_model()
    if model is None:
        return f"[전사 불가 · 발화 {seconds:.1f}초]"

    usable = len(pcm) - (len(pcm) % SAMPLE_WIDTH)
    audio = np.frombuffer(pcm[:usable], dtype=np.int16).astype(np.float32) / 32768.0

    # 줄을 선다(위 `_stt_running` 주석). 기다린 시간이 길면 로그로 남긴다 —
    # 면접이 몰릴 때 이 줄이 병목인지 나중에 알 수 있어야 한다.
    waited = time.monotonic()
    with _stt_running:
        queued = time.monotonic() - waited
        if queued > 1:
            logger.info("전사 대기 %.1f초 (앞에 다른 전사가 돌고 있었다)", queued)
        return _run_transcribe(model, audio)


def _run_transcribe(model, audio) -> str:
    segments, _ = model.transcribe(
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


# ── 답변인가 (2026-09-11) ─────────────────────────────────────
# 발화 끝을 가르는 감지기(`_SpeechDetector`)는 **소리 크기**만 본다. 폰 스피커로
# 나오는 담당자 쪽 방 소리·잡음도 0.7초만 넘으면 "답변 끝" 이 되는데, 그 순간 질문을
# 답한 것으로 찍으면(`mark_answered`) 전사가 비어도 질문이 넘어간다 — 2026-09-11
# 세션 57 에서 58초 만에 질문 10개가 전사 0자로 소진됐다(세션 56 의 6~10번도 같다).
# 그래서 넘기기 전에 **전사와 같은 VAD**(faster-whisper 의 silero)로 사람 목소리가
# 있는지 잰다. 이 VAD 가 아무것도 못 찾으면 전사도 빈 문자열이다 — 답변이 아니다.
MIN_VOICE_SEC = float(os.getenv("MIN_VOICE_SEC", "0.3"))

# 밖에서 갈라 볼 계기판 (`/health`) — 넘긴 것 · 거른 것 · 못 잰 것(→ 막지 않고 넘김).
# 질문이 안 넘어간다는 말이 나오면 `rejected` 가 느는지부터 본다.
ANSWER_STATS = {"voiced": 0, "rejected": 0, "unmeasured": 0}


def voice_seconds(pcm: bytes) -> float | None:
    """발화 안에 사람 목소리가 몇 초 있나. 못 재면 None — **그때는 막지 않는다.**

    VAD 가 고장 났다고 면접이 멈추면 안 된다. 못 재면 예전처럼 넘긴다.
    전사가 쓰는 것과 같은 판정 기준(`VadOptions` 기본값)이고, 앞뒤 여백
    (`speech_pad_ms`)만 빼서 목소리 길이 자체를 잰다. 수십 ms 걸린다.
    """
    usable = len(pcm) - (len(pcm) % SAMPLE_WIDTH)
    if usable == 0:
        return 0.0
    try:
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        audio = np.frombuffer(pcm[:usable], dtype=np.int16).astype(np.float32) / 32768.0
        spans = get_speech_timestamps(
            audio, VadOptions(speech_pad_ms=0), sampling_rate=SAMPLE_RATE
        )
    except Exception:
        logger.exception("목소리 재기 실패 — 막지 않고 넘긴다")
        return None
    return sum(s["end"] - s["start"] for s in spans) / SAMPLE_RATE
