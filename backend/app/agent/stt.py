"""음성-텍스트 변환 (STT).

마이크 녹음 → 전사 → entity_resolver 전처리 → 에이전트 입력.

백엔드가 둘이다 (`STT_BACKEND`, 기본 `openai` — 미설정이면 지금까지와 동일):

- `openai`         : OpenAI Whisper API. `OPENAI_API_KEY` 필요, 오디오가 외부로 나간다
- `faster_whisper` : 로컬 전사. 외부 호출 0건, 비용 0

로컬 백엔드를 쓰려면 별도 설치가 필요하다 — `uv sync --extra local`.
운영 API 서버(t3.micro)에 기본으로 깔리면 안 되므로 optional 로 뺐다.
"""

from __future__ import annotations

import io
import logging
import os
import threading
import time

from app.agent.entity_resolver import resolve_entities

logger = logging.getLogger(__name__)

STT_BACKEND = os.getenv("STT_BACKEND", "openai").strip().lower()

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
WHISPER_PRICE_PER_MINUTE = 0.006

# 로컬 전사 설정. large-v3 는 품질이 가장 좋지만 ~3GB 를 내려받는다.
LOCAL_MODEL = os.getenv("WHISPER_LOCAL_MODEL", "large-v3")
LOCAL_DEVICE = os.getenv("WHISPER_DEVICE", "auto")
LOCAL_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8_float16")

# 모델 로드는 비싸다(수 초 ~ 수십 초). 한 번 올려 두고 재사용한다.
# 락은 로드 구간만 감싼다 — 두 요청이 동시에 들어와 모델을 두 번 올리면 VRAM 이 두 배로 든다.
_local_model = None
_local_lock = threading.Lock()


def backend_tag() -> str:
    """로그·응답에 남길 식별자. 모델명만 남기면 어느 엔진이 만든 값인지 알 수 없다."""
    if STT_BACKEND == "faster_whisper":
        return f"faster-whisper:{LOCAL_MODEL}"
    return f"openai:{WHISPER_MODEL}"


def _estimate_stt_cost(audio_duration_sec: float) -> float:
    """API 전사 비용(USD) 추정. 로컬 전사는 부르지 않는다 — 0 이다."""
    return audio_duration_sec / 60.0 * WHISPER_PRICE_PER_MINUTE


def _get_local_model():
    global _local_model
    if _local_model is not None:
        return _local_model
    with _local_lock:
        if _local_model is not None:
            return _local_model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - 설치 안내 경로
            raise RuntimeError(
                "faster-whisper 가 설치되지 않았습니다. `uv sync --extra local` 로 설치하세요"
            ) from exc
        logger.info("로컬 STT 모델 로딩: %s (%s)", LOCAL_MODEL, LOCAL_DEVICE)
        _local_model = WhisperModel(
            LOCAL_MODEL, device=LOCAL_DEVICE, compute_type=LOCAL_COMPUTE_TYPE
        )
        return _local_model


def _transcribe_openai(audio_bytes: bytes, filename: str) -> tuple[str, float]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=(filename, audio_bytes),
        language="ko",
        response_format="verbose_json",
    )
    return response.text.strip(), (getattr(response, "duration", 0.0) or 0.0)


def _transcribe_local(audio_bytes: bytes) -> tuple[str, float]:
    """로컬 전사. 오디오가 이 프로세스를 벗어나지 않는다."""
    model = _get_local_model()
    # faster-whisper 는 경로 대신 바이너리 파일 객체를 받는다 — 임시 파일을 안 만든다
    segments, info = model.transcribe(io.BytesIO(audio_bytes), language="ko")
    # segments 는 제너레이터다. 여기서 소비해야 전사가 실제로 돈다
    text = "".join(seg.text for seg in segments).strip()
    return text, float(getattr(info, "duration", 0.0) or 0.0)


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> dict:
    """오디오 바이트를 전사하고 엔티티 해석을 적용한다.

    Returns:
        {"raw": 원본 전사, "resolved": 전처리 결과,
         "duration_ms": 처리 시간, "audio_duration_sec": 오디오 길이,
         "cost_usd": 추정 비용}

    반환 계약은 백엔드와 무관하게 같다 — 화면(SttResponse)이 이 형태에 묶여 있다.
    """
    if STT_BACKEND not in ("openai", "faster_whisper"):
        # 조용히 openai 로 폴백하지 않는다. 오타 하나로 오디오가 외부로 나가면 안 된다
        raise RuntimeError(
            f"알 수 없는 STT_BACKEND: {STT_BACKEND} (가능: openai, faster_whisper)"
        )

    start = time.monotonic()
    if STT_BACKEND == "faster_whisper":
        raw_text, audio_duration_sec = _transcribe_local(audio_bytes)
        cost = 0.0
    else:
        raw_text, audio_duration_sec = _transcribe_openai(audio_bytes, filename)
        cost = _estimate_stt_cost(audio_duration_sec)
    elapsed_ms = int((time.monotonic() - start) * 1000)

    resolved_text = resolve_entities(raw_text)

    logger.info(
        "stt_transcribe",
        extra={
            "backend": STT_BACKEND,
            "model": backend_tag(),
            "raw_length": len(raw_text),
            "resolved_length": len(resolved_text),
            "duration_ms": elapsed_ms,
            "audio_duration_sec": round(audio_duration_sec, 2),
            "cost_usd": round(cost, 6),
        },
    )

    return {
        "raw": raw_text,
        "resolved": resolved_text,
        "duration_ms": elapsed_ms,
        "audio_duration_sec": round(audio_duration_sec, 2),
        "cost_usd": round(cost, 6),
    }
