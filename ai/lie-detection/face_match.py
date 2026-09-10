"""이력서 사진의 얼굴 ↔ 면접 중의 얼굴 — 같은 사람인가 (회의 2026-09-09 3번).

**대리응시를 보려는 것이지 지원자를 평가하려는 것이 아니다.** 결과는 담당자
화면에 표시로만 나가고 판정(`verdict`)에는 섞지 않는다 — 표정·음성 신호와 달리
이건 신원 확인이라 성격이 다르다(ADR-0003 · ADR-0029 와 같은 자리).

**저장하지 않는다.** 이력서 사진도 얼굴 지문도 메모리에만 두고 면접이 끝나면
사라진다. 얼굴 지문은 갈아 끼울 수 없는 생체정보라, 남기는 순간 지켜야 할 것이
하나 늘고 대리응시 확인에는 그때그때 비교로 충분하다.

모델은 InsightFace `w600k_mbf` (MobileFaceNet, ONNX 13MB). torch 를 늘리지 않으려고
onnxruntime 을 쓴다 — faster-whisper 가 이미 끌고 오는 것이라 새 의존성이 아니다.
"""

from __future__ import annotations

import logging
import os

import cv2
import numpy as np

logger = logging.getLogger(__name__)

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "w600k_mbf.onnx")

# 코사인 유사도 문턱. LFW 1000쌍 실측:
#
#     같은 사람 498쌍   평균 +0.608   하위 5% +0.406
#     다른 사람 499쌍   평균 +0.006   상위 1% +0.193   최대 +0.236
#
# **`same` 을 0.40 으로 올렸다** (2026-09-09). 실제 얼굴만 보면 0.30 으로도
# 오탐이 0 이지만, 더미 지원서의 AI 생성 얼굴끼리는 남남이 0.33 까지 올라온다
# (남우빈 이력서 ↔ 백지안 면접 = 0.326 → 잘못 "same"). LFW 기준으로 0.30→0.40
# 은 같은 사람 통과가 97.0%→95.0% 로 2%p 줄 뿐이고, 그 2% 는 `unclear` 로
# 떨어질 뿐 의심받지 않는다. 못 잡는 대리응시보다 "확인 안 됨"이 낫다.
#
# **"다르다" 쪽은 훨씬 보수적으로 잡는다.** 놓친 대리응시는 면접관이 눈으로 잡을
# 여지가 남지만, 멀쩡한 지원자를 의심하는 것은 되돌릴 데가 없다. 0.15 에서 남남의
# 97.2% 가 걸리고 같은 사람의 1.6% 가 억울해진다 — 0.20 으로 올리면 2.2%p 를 더
# 잡는 대신 억울한 쪽이 2.0% 로 는다. 그 교환을 하지 않는다.
#
# 사이 값은 답하지 않는다 — 조명·각도로 같은 사람도 내려온다. 게다가 LFW 는
# 웹캠이 아니라 보도사진이라, 실제 면접 화면은 이보다 나쁠 것으로 본다.
SAME_MIN = 0.40
DIFF_MAX = 0.15

# ArcFace 가 학습된 정렬 기준점 (112×112 안의 눈2·코·입2 위치)
_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)

_session = None
_failed = False


def _model():
    """ONNX 세션. 모델 파일이 없으면 None — 확인을 건너뛸 뿐 면접은 돈다."""
    global _session, _failed
    if _session is None and not _failed:
        if not os.path.exists(MODEL_PATH):
            logger.warning("얼굴 대조 모델이 없다 (%s) — 동일인 확인을 건너뛴다", MODEL_PATH)
            _failed = True
            return None
        import onnxruntime as ort

        _session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    return _session


def _five_points(lm) -> np.ndarray:
    """랜드마크 478개 → 정렬용 5점 (눈2·코·입2).

    **눈과 입은 x 로 정렬해서 넣는다.** 랜드마크 번호의 좌/우는 얼굴 기준이고
    템플릿의 좌/우는 화면 기준이라, 번호를 그대로 쓰면 거울상에서 어긋난다.
    """
    from feature_extractor import _LEFT_EYE, _NOSE_TIP, _RIGHT_EYE

    def center(idx):
        pts = [lm[i] for i in idx]
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    eyes = sorted([center(_LEFT_EYE), center(_RIGHT_EYE)])
    mouth = sorted([lm[61], lm[291]])
    return np.array([eyes[0], eyes[1], lm[_NOSE_TIP], mouth[0], mouth[1]], dtype=np.float32)


def _aligned(lm, rgb) -> np.ndarray:
    """얼굴을 112×112 로 똑바로 세운다.

    ArcFace 는 눈·코·입이 정해진 자리에 오도록 맞춘 사진으로 학습됐다. 그냥 잘라
    넣으면 같은 사람도 각도가 다르면 다른 사람이 된다 — 정렬이 문턱값보다 중요하다.
    """
    matrix, _ = cv2.estimateAffinePartial2D(
        _five_points(lm), _TEMPLATE, method=cv2.LMEDS
    )
    return cv2.warpAffine(rgb, matrix, (112, 112), borderValue=0)


def embed(frame) -> np.ndarray | None:
    """BGR 프레임 → 512차원 얼굴 지문(길이 1). 얼굴이 없거나 모델이 없으면 None."""
    from feature_extractor import _detect

    session = _model()
    if session is None:
        return None
    lm, rgb = _detect(frame)
    if lm is None:
        return None

    face = _aligned(lm, rgb).astype(np.float32)
    blob = ((face - 127.5) / 127.5).transpose(2, 0, 1)[None]
    vec = session.run(None, {session.get_inputs()[0].name: blob})[0][0]
    norm = np.linalg.norm(vec)
    return vec / norm if norm else None


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """두 지문의 코사인 유사도 (-1 ~ 1)."""
    return float(np.dot(a, b))


def verdict(score: float) -> str:
    """유사도 → 담당자가 읽을 한 마디. **"다른 사람이다" 라고 단정하지 않는다.**"""
    if score >= SAME_MIN:
        return "same"
    if score <= DIFF_MAX:
        return "different"
    return "unclear"


def from_image_bytes(raw: bytes) -> np.ndarray | None:
    """이력서에서 꺼낸 사진 바이트 → 얼굴 지문."""
    frame = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    return embed(frame) if frame is not None else None
