"""연산 장치 점검 (2026-10-14, infra/compute.sh).

`infra/compute.sh` 가 CPU↔GPU 를 바꾼 뒤 **정말 그 장치에서 도는지** 확인하는 자리다.

설정값(STT_DEVICE 등)만 봐서는 모른다 — `cuda` 라고 적어 놓고 이미지에 CUDA 가 없으면
모델 로드가 조용히 실패하고(면접은 자리표시자로 내려앉는다) 설정값은 여전히 `cuda` 다.
그래서 모델마다 **한 번 실제로 돌리고, 모델이 앉은 장치를 모델에게서 읽는다.**

- `devices()` : 설정값 + 보이는 GPU 수. 싸다 — `/health` 가 매번 부른다.
- `run()`     : 모델 4종을 1건씩 돌린다. 무겁다 — `POST /selftest` (서비스 토큰) 로만.

**면접을 밀어내지 않는다.** 전사는 면접과 같은 줄(`_stt_running`)에 서되 5초 안에
차례가 안 오면 `busy` 로 돌려준다. 입력은 합성 신호다(1초 음, 회색 사진) — 결과값은
보지 않고 돌았는지·어디서 돌았는지·얼마나 걸렸는지만 본다.
"""

from __future__ import annotations

import functools
import logging
import time

import numpy as np

import feature_extractor as fe
import interview_ws as iw

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _cuda_devices() -> int | None:
    """보이는 GPU 수. torch 를 올리지 않고 ctranslate2 에게 묻는다 (전사 엔진이라 늘 있다).

    CPU 판 이미지·GPU 없는 기계에서는 0. 뜬 뒤에 GPU 가 생길 일은 없어 한 번만 묻는다.
    """
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return None


def devices() -> dict:
    """설정된 장치. 꺼진 모델은 None — 장치를 말할 것이 없다."""
    import deception_vit

    return {
        "stt": iw.STT_DEVICE if iw.STT_MODEL else None,
        "stt_compute_type": iw.STT_COMPUTE_TYPE if iw.STT_MODEL else None,
        "stt_backend": "openai" if iw.stt_via_api() else ("local" if iw.STT_MODEL else None),
        "vit": fe.VIT_DEVICE if fe.VIT_MODEL else None,
        "deception": deception_vit.DEVICE,
        "cuda_devices": _cuda_devices(),
    }


def _timed(fn):
    """fn() 을 돌려 (결과, 걸린 ms). 예외는 그대로 올린다."""
    started = time.monotonic()
    result = fn()
    return result, round((time.monotonic() - started) * 1000, 1)


def _device_of(module) -> str:
    return str(next(module.parameters()).device)


def _stt() -> dict:
    if not iw.STT_MODEL:
        return {"status": "off"}
    model = iw._stt_model()
    if model is None:
        return {"status": "unavailable", "detail": "전사 모델 로드 실패 — 서비스 로그 확인"}
    if not iw._stt_running.acquire(timeout=5):
        return {"status": "busy", "detail": "면접 전사가 돌고 있다 — 잠시 뒤 다시"}
    try:
        t = np.arange(iw.SAMPLE_RATE, dtype=np.float32) / iw.SAMPLE_RATE
        audio = (0.1 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

        def go():
            # vad 를 끈다 — 켜면 음 1초가 잘려 나가 모델이 아예 안 돈다
            segments, _ = model.transcribe(
                audio, language=iw.STT_LANGUAGE or None, beam_size=1,
                vad_filter=False, condition_on_previous_text=False,
            )
            return list(segments)  # 생성기라 끝까지 읽어야 실제로 돈다

        _, ms = _timed(go)
    finally:
        iw._stt_running.release()
    return {
        "status": "ok",
        "device": model.model.device,
        "compute_type": model.model.compute_type,
        "ms": ms,
    }


def _vit() -> dict:
    if not fe.VIT_MODEL:
        return {"status": "off"}
    crop = np.full((224, 224, 3), 128, dtype=np.uint8)
    probs, ms = _timed(lambda: fe.expression_rows([crop]))
    if probs is None:
        return {"status": "error", "detail": "표정 확률이 비었다"}
    _, model, _ = fe._vit_pair()
    return {"status": "ok", "device": _device_of(model), "ms": ms}


def _deception_vit() -> dict:
    import deception_vit as dv

    if not dv.available():
        return {"status": "unavailable", "detail": "모델 로드 실패 — 서비스 로그 확인"}
    frame = np.full((224, 224, 3), 128, dtype=np.uint8)
    result, ms = _timed(lambda: dv.predict(frame))
    if result is None:
        return {"status": "error", "detail": "추론 실패 — 서비스 로그 확인"}
    return {"status": "ok", "device": _device_of(dv._model), "ms": ms}


def _deception_whisper() -> dict:
    import deception_whisper as dw

    if not dw.available():
        # 이미지에 openai-whisper 패키지가 없으면 늘 여기다 (CPU·GPU 판 같음)
        return {"status": "unavailable", "detail": "모델 로드 실패 — openai-whisper 미설치 등"}
    pcm = np.zeros(dw.SAMPLE_RATE, dtype=np.int16).tobytes()
    result, ms = _timed(lambda: dw.predict(pcm))
    if result is None:
        return {"status": "error", "detail": "추론 실패 — 서비스 로그 확인"}
    return {"status": "ok", "device": _device_of(dw._model), "ms": ms}


def run() -> dict:
    """모델 4종을 1건씩. 하나가 터져도 나머지는 돈다 — 무엇이 어디서 안 되는지가 답이다."""
    models = {}
    for name, fn in (
        ("stt", _stt),
        ("vit", _vit),
        ("deception_vit", _deception_vit),
        ("deception_whisper", _deception_whisper),
    ):
        try:
            models[name] = fn()
        except Exception as e:
            logger.exception("selftest %s 실패", name)
            models[name] = {"status": "error", "detail": f"{type(e).__name__}: {e}"[:300]}
    return {"devices": devices(), "models": models}
