"""tools 계층 idempotency guard — 로컬 sLLM 이 같은 도구를 반복 호출하는
실패 패턴을 잡는다. 원리적으로는 어느 백엔드에도 유효하지만 실측(2026-09-02
C0 지도) 상 로컬 4B 경로에서 주로 발동한다.

**요청당 새 인스턴스로 써야 한다.** `run_agent()` 가 매 호출마다 새로 만들어야
두 번째 사용자 요청부터 오탐이 나지 않는다 — 이 조건은 코드로만 보장되고
문서로는 부족하다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")


class StopToolLoop(Exception):
    """어댑터에게 도구 루프에서 빠져나와 reply 라운드로 가라는 신호.

    - `reason` 은 로깅용 짧은 라벨 (`duplicate_call:search_users:2` 같은).
    - `note` 는 다음 라운드 프롬프트에 실릴 사용자용 한국어 안내.
    """

    def __init__(self, reason: str, note: str):
        super().__init__(reason)
        self.reason = reason
        self.note = note


def _norm(v: Any) -> Any:
    """정규화 — `'김도현 '` 과 `'김도현'` 이 다른 호출로 새어나가지 않게."""
    if isinstance(v, str):
        return _WS.sub(" ", v.strip())
    if isinstance(v, list):
        return [_norm(x) for x in v]
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in sorted(v.items())}
    return v


def stable_hash(name: str, args: dict) -> str:
    payload = {"n": name, "a": _norm(args)}
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _count_of(result: Any) -> int:
    """도구 결과에서 결과 개수 추정. 판정 못하면 -1 (0건 판정도 안 함).

    error 반환은 실패이지만 "0건 재시도" 와 별개다 — 여기서는 -1 로 취급하고
    루프는 어댑터의 기존 처리에 맡긴다.
    """
    if not isinstance(result, dict):
        return -1
    if "error" in result:
        return -1
    if isinstance(result.get("count"), int):
        return result["count"]
    if isinstance(result.get("results"), list):
        return len(result["results"])
    return -1


class GuardedToolRunner:
    """도구 실행에 중복 호출·0건 재시도 감지를 얹는 래퍼.

    - 같은 `(name, 정규화된 args)` 재호출이 `DUP_LIMIT` 회에 도달하면 `StopToolLoop`
    - 결과 count 가 0 인 것이 `ZERO_LIMIT` 회 연속되면 `StopToolLoop`
    - 첫 0건에는 결과 dict 에 `note` 를 얹어 다음 라운드에 신호 (원 필드는 보존)

    `StopToolLoop` 는 어댑터가 잡아서 reply 라운드로 넘어가야 한다.
    grammar 로 도구 분기를 아예 제거할 수 있는 structured 경로가 이상적이고,
    일반 경로는 fallback 문구로 종료한다.
    """

    DUP_LIMIT = 2     # 같은 호출이 이번이 두 번째면 stop
    ZERO_LIMIT = 2    # 0건 결과가 연속으로 이번이 두 번째면 stop

    def __init__(self, inner):
        self.inner = inner
        self.definitions = inner.definitions
        self._counts: dict[str, int] = {}
        self._zero_streak = 0

    def is_deferred(self, name: str) -> bool:
        return self.inner.is_deferred(name)

    def describe(self, name: str, arguments: dict) -> str:
        return self.inner.describe(name, arguments)

    def execute(self, name: str, arguments: dict) -> str:
        key = stable_hash(name, arguments)
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count

        if count >= self.DUP_LIMIT:
            reason = f"duplicate_call:{name}:{count}"
            logger.info("stop_tool_loop", extra={"reason": reason, "tool": name})
            raise StopToolLoop(
                reason,
                "같은 도구를 같은 조건으로 이미 호출했어요. 지금까지 알아낸 정보로 답하거나 사용자에게 조건을 다시 여쭤보세요.",
            )

        result_json = self.inner.execute(name, arguments)
        try:
            result = json.loads(result_json)
        except (json.JSONDecodeError, TypeError):
            # 파싱 불가면 0건 스트릭도 리셋 — 판정 불가
            self._zero_streak = 0
            return result_json

        c = _count_of(result)
        if c == 0:
            self._zero_streak += 1
            if self._zero_streak >= self.ZERO_LIMIT:
                reason = f"zero_result_streak:{self._zero_streak}"
                logger.info("stop_tool_loop", extra={"reason": reason, "tool": name})
                raise StopToolLoop(
                    reason,
                    "도구가 계속 결과를 찾지 못하고 있어요. 사용자에게 이름·조건을 다시 확인해 주세요.",
                )
            if isinstance(result, dict) and "note" not in result:
                result["note"] = "결과가 없습니다. 사용자에게 이름·조건을 다시 확인하세요."
                result_json = json.dumps(result, ensure_ascii=False)
        else:
            self._zero_streak = 0

        return result_json
