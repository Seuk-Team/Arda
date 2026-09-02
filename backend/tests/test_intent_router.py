"""intent_router.classify 단위 테스트.

규칙 라우터는 순수 함수 (message → DirectAction | None) 라 DB·백엔드 없이
검증한다. 확신도 높은 케이스만 잡히는지, 애매한 건 None 리턴하는지가 핵심.
"""
from __future__ import annotations

import pytest

from app.agent.intent_router import DirectAction, classify


# ── 지원자 목록 ───────────────────────────────────────────────


@pytest.mark.parametrize("message", [
    "지원자 목록 보여줘",
    "지원자 리스트",
    "지원자 다 보여줘",
    "지원자 전체",
    "지원자 모두 보여줘",
    "전체 지원자 목록",
])
def test_list_applicants_matches(message):
    action = classify(message)
    assert action is not None
    assert action.tool_name == "search_applications"
    assert action.rule == "list_applicants"
    assert action.is_write is False


def test_applicant_count_query():
    action = classify("지원자 몇 명이야?")
    assert action is not None
    assert action.tool_name == "search_applications"
    assert action.rule == "count_applicants"


# ── stage 지원자 ──────────────────────────────────────────────


@pytest.mark.parametrize("message,expected_stage", [
    ("면접 지원자 보여줘", "interview"),
    ("면접 단계 지원자", "interview"),
    ("서류심사 지원자 알려줘", "screening"),
    ("서류 검토 단계 지원자", "screening"),
    ("합격 지원자", "accepted"),
    ("최종 합격 지원자 보여줘", "accepted"),
    ("불합격 지원자", "rejected"),
    ("접수 지원자", "applied"),
])
def test_stage_applicants_matches(message, expected_stage):
    action = classify(message)
    assert action is not None
    assert action.tool_name == "search_applications"
    assert action.args["stage"] == [expected_stage]
    assert action.rule.startswith("stage_applicants:")


# ── 이름 검색 ─────────────────────────────────────────────────


@pytest.mark.parametrize("message,expected_name", [
    ("김도현 찾아줘", "김도현"),
    ("김도현 지원자 찾아줘", "김도현"),
    ("문해린 검색해줘", "문해린"),
    ("곽민재 알려줘", "곽민재"),
    ("백지안을 찾아줘", "백지안"),
    ("이민수 조회해줘", "이민수"),
    ("서지호 보여줘", "서지호"),
])
def test_name_search_matches(message, expected_name):
    action = classify(message)
    assert action is not None
    assert action.tool_name == "search_applications"
    assert action.args["q"] == expected_name
    assert action.rule == "name_search"


# ── 단계 변경 ─────────────────────────────────────────────────


@pytest.mark.parametrize("message,expected_name,expected_stage", [
    ("김도현을 면접 단계로 옮겨줘", "김도현", "interview"),
    ("문해린 합격 단계로 변경해줘", "문해린", "accepted"),
    ("백지안을 불합격 단계로 바꿔줘", "백지안", "rejected"),
    ("곽민재를 서류심사 단계로 옮겨줘", "곽민재", "screening"),
    ("서지호 면접으로 보내줘", "서지호", "interview"),
])
def test_change_stage_matches(message, expected_name, expected_stage):
    action = classify(message)
    assert action is not None
    assert action.tool_name == "change_stage"
    assert action.args["_name_lookup"] == expected_name
    assert action.args["to_stage"] == expected_stage
    assert action.is_write is True
    assert action.rule.startswith("change_stage:")


# ── 애매한 것은 통과 (LLM 로 넘김) ───────────────────────────


@pytest.mark.parametrize("message", [
    "안녕",
    "너는 누구야",
    "너 뭐 할 수 있어?",
    "백엔드 개발 지원자 알려줘",  # 이름이 아니라 역량 → 시맨틱, LLM 로
    "Kubernetes 경험 있는 지원자",
    "김도현에게 합격 이메일 초안 써줘",  # 이메일 초안 = 복잡, LLM 로
    "김도현 면접 다음 주 화요일로 잡아줘",  # 날짜 파싱 = 복잡, LLM 로
    "응 변경해줘",  # 확인 응답은 프론트 라우터 담당
    "김도현이 어때?",  # 자유 질의
    "",  # 빈 문자열
    "   ",  # 공백만
])
def test_ambiguous_returns_none(message):
    assert classify(message) is None


# ── 잠재적 오탐 방지 ───────────────────────────────────────


def test_name_too_long_not_matched():
    """이름 후보가 5자 이상이면 잡지 않는다 (한글 이름은 대개 2~4자)."""
    action = classify("김도현영수 면접 단계로 옮겨줘")
    # 5자라 name 매치 안 됨 → change_stage 스킵 → LLM 로
    assert action is None


def test_dataclass_fields_default():
    """DirectAction 기본값 확인."""
    a = DirectAction(tool_name="x")
    assert a.args == {}
    assert a.is_write is False
    assert a.rule == ""


# ── LLM 라우터 (판단은 LLM, 실행은 코드) ─────────────────────────

from app.agent.backends.base import CompletionResult  # noqa: E402
from app.agent.intent_router import classify_llm, INTENT_SCHEMA  # noqa: E402


class _FakeBackend:
    """complete() 가 정해진 텍스트를 돌려주는 최소 어댑터."""

    def __init__(self, text: str):
        self.text = text
        self.prompts: list[str] = []

    def complete(self, *, prompt: str, max_tokens: int, json_schema=None) -> CompletionResult:
        self.prompts.append(prompt)
        assert json_schema is INTENT_SCHEMA
        return CompletionResult(text=self.text, input_tokens=10, output_tokens=5)


def _llm(text: str, message: str) -> DirectAction | None:
    return classify_llm(message, backend=_FakeBackend(text))


def test_llm_name_search_valid():
    a = _llm('{"intent":"name_search","name":"김도현","stage":""}', "김도현씨 프로필 좀")
    assert a is not None
    assert a.tool_name == "search_applications"
    assert a.args["q"] == "김도현"
    assert a.rule == "llm:name_search"


def test_llm_change_stage_valid_with_typo_in_message():
    a = _llm(
        '{"intent":"change_stage","name":"김도현","stage":"accepted"}',
        "김도현씨 최종합격 단계로 옴겨줘",
    )
    assert a is not None
    assert a.tool_name == "change_stage"
    assert a.is_write is True
    assert a.args == {"_name_lookup": "김도현", "to_stage": "accepted"}


def test_llm_strips_honorific_from_name():
    a = _llm('{"intent":"name_search","name":"김도현씨","stage":""}', "김도현씨 찾아줘")
    assert a is not None
    assert a.args["q"] == "김도현"


def test_llm_rejects_name_not_in_message():
    """모델이 이름을 지어내면 폴백 — 창작 차단의 핵심."""
    a = _llm('{"intent":"name_search","name":"홍길동","stage":""}', "김도현 찾아줘")
    assert a is None


def test_llm_rejects_invalid_stage_for_change_stage():
    a = _llm('{"intent":"change_stage","name":"김도현","stage":"hired"}', "김도현 채용해줘")
    assert a is None


def test_llm_change_stage_requires_name():
    a = _llm('{"intent":"change_stage","name":"","stage":"interview"}', "면접 단계로 옮겨줘")
    assert a is None


def test_llm_other_returns_none():
    a = _llm('{"intent":"other","name":"","stage":""}', "안녕")
    assert a is None


def test_llm_list_and_stage_intents():
    a = _llm('{"intent":"list_applicants","name":"","stage":""}', "지원자들 다 보여줘요")
    assert a is not None and a.args == {"limit": 20}
    b = _llm('{"intent":"stage_applicants","name":"","stage":"interview"}', "면접 지원자 누구야")
    assert b is not None and b.args["stage"] == ["interview"]


def test_llm_list_with_stage_promotes_to_stage_intent():
    """S3: 의도는 list 인데 stage 가 유효하면 stage 라우팅 (결정적 승격)."""
    a = _llm('{"intent":"list_applicants","name":"","stage":"accepted"}', "합격한 지원자 보여줘")
    assert a is not None
    assert a.args["stage"] == ["accepted"]
    assert a.rule == "llm:stage_applicants:accepted"


def test_llm_list_without_stage_stays_list():
    a = _llm('{"intent":"list_applicants","name":"","stage":""}', "지원자 목록 보여줘")
    assert a is not None and a.rule == "llm:list_applicants" and "stage" not in a.args


def test_llm_stage_intent_with_schedule_hint_falls_back():
    """O2: 면접 *일정* 질문을 stage 로 잘못 읽어도 가드가 폴백시킨다."""
    for msg in ("오늘 면접 몇 건이야?", "이번 주 면접 일정 알려줘", "내일 면접 시간"):
        a = _llm('{"intent":"stage_applicants","name":"","stage":"interview"}', msg)
        assert a is None, msg


def test_llm_stage_intent_without_hint_routes():
    a = _llm('{"intent":"stage_applicants","name":"","stage":"interview"}', "면접 단계 지원자 보여줘")
    assert a is not None and a.args["stage"] == ["interview"]


def test_llm_malformed_json_falls_back():
    assert _llm("not json", "김도현 찾아줘") is None
    assert _llm("", "김도현 찾아줘") is None


def test_llm_fenced_json_is_parsed():
    a = _llm('```json\n{"intent":"name_search","name":"김도현","stage":""}\n```', "김도현 찾아줘")
    assert a is not None and a.args["q"] == "김도현"


def test_llm_backend_exception_falls_back():
    class _Boom:
        def complete(self, **_):
            raise RuntimeError("ollama down")
    assert classify_llm("김도현 찾아줘", backend=_Boom()) is None


# ── 스위치 (AGENT_INTENT_ROUTER) ──────────────────────────────


def test_switch_default_is_rules(monkeypatch):
    monkeypatch.delenv("AGENT_INTENT_ROUTER", raising=False)
    a = classify("김도현 찾아줘")
    assert a is not None and a.rule == "name_search"


def test_switch_off_returns_none(monkeypatch):
    monkeypatch.setenv("AGENT_INTENT_ROUTER", "0")
    assert classify("김도현 찾아줘") is None


def test_switch_llm_uses_llm_classifier(monkeypatch):
    import app.agent.backends as backends
    monkeypatch.setenv("AGENT_INTENT_ROUTER", "llm")
    fake = _FakeBackend('{"intent":"name_search","name":"김도현","stage":""}')
    monkeypatch.setattr(backends, "get_chat_backend", lambda: fake)
    a = classify("김도현씨 좀 찾아봐")
    assert a is not None and a.rule == "llm:name_search"
    assert len(fake.prompts) == 1 and "김도현씨 좀 찾아봐" in fake.prompts[0]
