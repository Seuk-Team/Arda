#!/usr/bin/env python
"""로컬 AI 모델을 미리 받아 캐시에 넣는다 — 런타임에 인터넷을 타지 않게.

**왜 필요한가.** `SentenceTransformer(...)` 와 `WhisperModel(...)` 은 모델이 없으면
**첫 사용 시점에 HuggingFace 에서 내려받는다.** 그 결과 세 가지가 생긴다:

1. 온프레미스·에어갭 환경에서 그냥 죽는다
2. 프라이빗 서브넷이면 NAT 게이트웨이가 있어야 한다 — "외부 호출 0건"이 아니게 된다
3. 첫 요청만 수십 초 걸린다. 담당자 눈에는 "가끔 멈추는 앱"이다

빌드·프로비저닝 단계에서 한 번 돌리고, 런타임에는 `HF_HUB_OFFLINE=1` 로 잠근다.
그러면 모델이 빠졌을 때 조용히 내려받는 대신 **바로 실패해서 눈에 띈다.**

사용:

    # 임베딩만 (API 서버용 — 기본)
    uv run python scripts/prefetch_models.py

    # STT 까지 (GPU 장비용 — faster-whisper 가 설치돼 있어야 한다)
    uv run python scripts/prefetch_models.py --stt

캐시 위치는 `HF_HOME` 을 따른다. 컨테이너·인스턴스에서는 이 값을 볼륨에 두고
런타임과 같은 경로를 쓰게 해야 의미가 있다.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _fetch_embedding() -> bool:
    from app.agent.embedder import DEFAULT_MODEL

    print(f"임베딩 모델 받는 중: {DEFAULT_MODEL}")
    started = time.perf_counter()
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(DEFAULT_MODEL)
        # 실제로 한 번 돌려 본다 — 파일만 받고 로드가 안 되는 경우를 여기서 잡는다
        model.encode(["동작 확인"])
    except Exception as exc:
        print(f"  실패: {type(exc).__name__}: {exc}")
        return False
    print(f"  완료 ({time.perf_counter() - started:.1f}초)")
    return True


def _fetch_stt() -> bool:
    from app.agent.stt import LOCAL_COMPUTE_TYPE, LOCAL_MODEL

    print(f"STT 모델 받는 중: {LOCAL_MODEL}")
    started = time.perf_counter()
    try:
        from faster_whisper import WhisperModel

        # 받아 두는 것이 목적이라 device 는 cpu 로 고정한다 — 빌드 머신에 GPU 가
        # 없을 수 있고, 파일은 device 와 무관하게 같은 캐시에 들어간다.
        WhisperModel(LOCAL_MODEL, device="cpu", compute_type="int8")
    except ImportError:
        print("  건너뜀: faster-whisper 미설치 (uv sync --extra local)")
        return True
    except Exception as exc:
        print(f"  실패: {type(exc).__name__}: {exc}")
        return False
    print(f"  완료 ({time.perf_counter() - started:.1f}초, compute_type={LOCAL_COMPUTE_TYPE})")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="로컬 AI 모델 사전 다운로드")
    parser.add_argument("--stt", action="store_true", help="STT 모델도 받는다 (GPU 장비용)")
    args = parser.parse_args()

    if os.getenv("HF_HUB_OFFLINE") == "1":
        print("HF_HUB_OFFLINE=1 이면 받을 수 없다. 이 스크립트를 돌릴 때는 꺼야 한다.")
        return 1

    print(f"캐시 위치(HF_HOME): {os.getenv('HF_HOME') or '(기본값 ~/.cache/huggingface)'}\n")

    ok = _fetch_embedding()
    if args.stt:
        ok = _fetch_stt() and ok

    if ok:
        print("\n전부 받았다. 런타임에는 HF_HUB_OFFLINE=1 을 걸어 재다운로드를 막는다.")
        return 0
    print("\n일부 실패. 위 메시지를 보고 다시 돌려라.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
