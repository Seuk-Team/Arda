"""GuardedToolRunner 단위 테스트 — 중복 호출·0건 재시도 감지.

이 guard 는 tools 계층에 있어 어떤 백엔드가 감싸든 같은 계약이다. 그래서
inner mock 하나로 검증한다.
"""
from __future__ import annotations

import json

import pytest

from app.agent.tools.guard import GuardedToolRunner, StopToolLoop, stable_hash


class _InnerStub:
    """설정된 응답을 순서대로 돌려주는 최소 ToolRunner."""

    definitions = [{"name": "search_applications"}]

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.executed: list[tuple[str, dict]] = []

    def is_deferred(self, name: str) -> bool:
        return name in {"change_stage", "send_email"}

    def describe(self, name: str, arguments: dict) -> str:
        return f"desc:{name}"

    def execute(self, name: str, arguments: dict) -> str:
        self.executed.append((name, dict(arguments)))
        if not self.responses:
            raise RuntimeError("no more stub responses")
        return self.responses.pop(0)


def _ok(count: int) -> str:
    return json.dumps({"ok": True, "count": count, "results": [{"id": i} for i in range(count)]})


# ── 위임 ────────────────────────────────────────────────────────────


def test_passthrough_is_deferred_and_describe():
    inner = _InnerStub([_ok(1)])
    g = GuardedToolRunner(inner)
    assert g.is_deferred("change_stage") is True
    assert g.is_deferred("search_applications") is False
    assert g.describe("search_applications", {"q": "김"}) == "desc:search_applications"
    assert g.definitions is inner.definitions


# ── 정상 흐름 ──────────────────────────────────────────────────────


def test_different_args_pass_through():
    inner = _InnerStub([_ok(3), _ok(2)])
    g = GuardedToolRunner(inner)
    r1 = g.execute("search_applications", {"q": "김도현"})
    r2 = g.execute("search_applications", {"q": "문해린"})
    assert json.loads(r1)["count"] == 3
    assert json.loads(r2)["count"] == 2
    assert len(inner.executed) == 2


def test_zero_result_then_nonzero_resets_streak():
    inner = _InnerStub([_ok(0), _ok(5), _ok(0)])
    g = GuardedToolRunner(inner)
    # 첫 0건은 note 만 붙고 통과
    r1 = json.loads(g.execute("search_applications", {"q": "김"}))
    assert "note" in r1
    # 다른 도구/인자로 5건 반환 → 스트릭 리셋
    r2 = json.loads(g.execute("search_applications", {"q": "문"}))
    assert r2["count"] == 5
    assert "note" not in r2
    # 다시 0건 하나 나와도 스트릭이 리셋됐으므로 즉시 stop 아님
    r3 = json.loads(g.execute("search_applications", {"q": "이"}))
    assert "note" in r3


# ── 패턴 1: 중복 호출 ─────────────────────────────────────────────


def test_duplicate_call_raises_stop_tool_loop():
    inner = _InnerStub([_ok(1)])
    g = GuardedToolRunner(inner)
    g.execute("search_applications", {"q": "김도현"})
    with pytest.raises(StopToolLoop) as ei:
        g.execute("search_applications", {"q": "김도현"})
    assert "duplicate_call" in ei.value.reason
    assert "search_applications" in ei.value.reason
    # 두 번째는 실행하지 않았어야 한다
    assert len(inner.executed) == 1


def test_arg_normalization_treats_whitespace_as_same():
    inner = _InnerStub([_ok(1)])
    g = GuardedToolRunner(inner)
    g.execute("search_applications", {"q": "김도현"})
    with pytest.raises(StopToolLoop):
        # 앞·중간 공백만 다르면 같은 호출로 봐야 한다 (패턴 1 이 새어나가지 않게)
        g.execute("search_applications", {"q": " 김도현  "})
    assert len(inner.executed) == 1


def test_arg_key_order_does_not_matter():
    inner = _InnerStub([_ok(1)])
    g = GuardedToolRunner(inner)
    g.execute("search_applications", {"q": "김", "stage": ["applied"]})
    with pytest.raises(StopToolLoop):
        g.execute("search_applications", {"stage": ["applied"], "q": "김"})


# ── 패턴 2: 0건 연속 재시도 ───────────────────────────────────────


def test_two_zero_result_calls_raise_stop_tool_loop():
    inner = _InnerStub([_ok(0), _ok(0)])
    g = GuardedToolRunner(inner)
    # 첫 0건은 note 만 붙고 통과
    r1 = json.loads(g.execute("search_applications", {"q": "김"}))
    assert r1["count"] == 0
    assert "note" in r1
    # 다른 인자로 다시 0건 → StopToolLoop
    with pytest.raises(StopToolLoop) as ei:
        g.execute("search_applications", {"q": "문"})
    assert "zero_result_streak" in ei.value.reason


def test_zero_via_empty_results_list_counts():
    inner = _InnerStub([
        json.dumps({"ok": True, "results": []}),
        json.dumps({"ok": True, "results": []}),
    ])
    g = GuardedToolRunner(inner)
    json.loads(g.execute("search_applications", {"q": "김"}))
    with pytest.raises(StopToolLoop):
        g.execute("search_applications", {"q": "문"})


# ── 판정 불가 (error 반환·비JSON) ────────────────────────────────


def test_error_result_is_not_treated_as_zero():
    inner = _InnerStub([
        json.dumps({"error": "지원자를 찾을 수 없습니다"}),
        _ok(3),
    ])
    g = GuardedToolRunner(inner)
    r1 = json.loads(g.execute("search_applications", {"application_id": 999}))
    assert "error" in r1
    # 에러는 0건 스트릭에 안 들어간다 — 다음 호출은 정상 실행
    r2 = json.loads(g.execute("search_applications", {"application_id": 1}))
    assert r2["count"] == 3


def test_non_json_response_passes_through():
    inner = _InnerStub(["not json at all"])
    g = GuardedToolRunner(inner)
    r = g.execute("search_applications", {"q": "김"})
    assert r == "not json at all"


# ── 해시 자체 ────────────────────────────────────────────────────


def test_stable_hash_ignores_whitespace_and_key_order():
    a = stable_hash("search_applications", {"q": "김도현", "stage": ["applied"]})
    b = stable_hash("search_applications", {"stage": ["applied"], "q": " 김도현 "})
    assert a == b


def test_stable_hash_differs_on_meaningful_change():
    a = stable_hash("search_applications", {"q": "김도현"})
    b = stable_hash("search_applications", {"q": "문해린"})
    assert a != b
