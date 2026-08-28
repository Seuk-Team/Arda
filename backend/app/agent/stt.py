"""음성-텍스트 변환 (STT) — OpenAI Whisper API.

마이크 녹음 → Whisper 전사 → entity_resolver 전처리 → 에이전트 입력.
OPENAI_API_KEY가 없으면 즉시 에러를 반환한다.
"""

from __future__ import annotations

import logging
import os
import time

from app.agent.entity_resolver import resolve_entities

logger = logging.getLogger(__name__)

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")
WHISPER_PRICE_PER_MINUTE = 0.006


def _estimate_stt_cost(audio_duration_sec: float) -> float:
    return audio_duration_sec / 60.0 * WHISPER_PRICE_PER_MINUTE


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> dict:
    """오디오 바이트를 Whisper로 전사하고 엔티티 해석을 적용한다.

    Returns:
        {"raw": 원본 전사, "resolved": 전처리 결과,
         "duration_ms": 처리 시간, "audio_duration_sec": 오디오 길이,
         "cost_usd": 추정 비용}
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    start = time.monotonic()
    response = client.audio.transcriptions.create(
        model=WHISPER_MODEL,
        file=(filename, audio_bytes),
        language="ko",
        response_format="verbose_json",
    )
    elapsed_ms = int((time.monotonic() - start) * 1000)

    raw_text = response.text.strip()
    resolved_text = resolve_entities(raw_text)

    audio_duration_sec = getattr(response, "duration", 0.0) or 0.0
    cost = _estimate_stt_cost(audio_duration_sec)

    logger.info(
        "stt_transcribe",
        extra={
            "model": WHISPER_MODEL,
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
