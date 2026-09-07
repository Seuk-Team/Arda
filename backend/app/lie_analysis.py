"""면접 영상 진위 분석 호출 (ADR-0029).

`ai/lie-detection` 은 **별도 서비스**다. mediapipe·opencv·librosa 가 무겁고 영상
분석이 CPU 를 오래 써서, 면접 API 가 그 영향을 받으면 안 되기 때문이다. 여기서는
HTTP 로 한 번 부르기만 한다.

## 설정이 없으면 아무것도 하지 않는다

`LIE_SERVICE_URL` 이 비어 있으면 이 기능은 **꺼진 것**이다. 체인(`chain.py`)이
`CHAIN_RPC_URL` 없이 꺼져 있는 것과 같은 방식이고, 이유도 같다 —
**ADR-0029 결정 5**가 "「정하지 못한 것」 ①②③ 이 정해지기 전에는 운영에 붙이지
않는다"고 못 박았다. 환경변수를 안 넣으면 운영에서는 켜지지 않는다.

## 결과를 저장하지 않는다

ADR-0029 는 결과를 담을 표를 **아직 정하지 않았다**(정확도 검증 ①이 끝난 뒤 확정).
그래서 여기서는 부르고 돌려주기만 한다. 저장을 먼저 만들어 두면, 스키마가 정해지기
전에 값이 쌓이고 그 값이 근거처럼 쓰이기 시작한다.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

SERVICE_URL = os.getenv("LIE_SERVICE_URL", "").rstrip("/")

# 영상 분석은 길이에 따라 분 단위까지 간다. 서비스 쪽 gunicorn 도 300초로 잡혀 있다.
TIMEOUT_SEC = 300


def unavailable_reason() -> str | None:
    """왜 못 부르는지. 부를 수 있으면 `None`."""
    if not SERVICE_URL:
        return "LIE_SERVICE_URL 미설정"
    return None


def analyze(video_bytes: bytes, filename: str = "answer.webm") -> dict:
    """영상 하나를 분석 서비스에 넘긴다.

    돌아오는 모양은 서비스 README 그대로다 —
    `{pred, truth_pct, lie_pct, observations[]}`.

    **`observations` 는 판정 근거가 아니다.** 서비스 문서에 적힌 대로 "평균에서
    벗어났다"는 표시일 뿐이고, `flag: high` 가 거짓이라는 뜻이 아니다. 화면에서
    빨강으로 칠해 증거처럼 보이게 하면 안 된다 (ADR-0029 「화면에서 지킬 것」).
    """
    import httpx

    resp = httpx.post(
        f"{SERVICE_URL}/analyze",
        files={"video": (filename, video_bytes, "video/webm")},
        timeout=TIMEOUT_SEC,
    )
    resp.raise_for_status()
    result = resp.json()

    logger.info(
        "lie_analysis",
        extra={
            "bytes": len(video_bytes),
            # 판정값 자체는 로그에 남기지 않는다 — 지원자에 대한 추론이고,
            # 저장하지 않기로 한 값이 로그로 남으면 저장한 것과 같아진다.
            "has_error": "error" in result,
        },
    )
    return result
