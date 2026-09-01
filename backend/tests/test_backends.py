"""LLM 백엔드 어댑터 테스트 — Ollama 서버 없이 mock 으로 돈다.

검증 대상:
- 백엔드 선택 (역할별 env, 기본값, 오타)
- `<think>` 제거 — 지우지 않으면 사고 과정이 프론트로 샌다
- 도구 스키마 변환 (Anthropic input_schema → Ollama parameters)
- 로컬 비용 0.0 · backend:model 태깅
- 로컬 추론 직렬화 락 / num_ctx 명시
"""

from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock, patch

import pytest

from app.agent.backends import (
    AnthropicBackend,
    OllamaBackend,
    build_backend,
    get_chat_backend,
    get_summary_backend,
)
from app.agent.backends.ollama_backend import (
    DEFAULT_NUM_CTX,
    strip_think,
    to_ollama_tools,
)
from app.agent.tools import TOOL_DEFINITIONS


# ── 도구 통로 더블 ──


class FakeToolRunner:
    def __init__(self, definitions=None, deferred=(), output="[]"):
        self.definitions = list(definitions if definitions is not None else TOOL_DEFINITIONS)
        self._deferred = set(deferred)
        self._output = output
        self.calls: list[tuple[str, dict]] = []

    def is_deferred(self, name):
        return name in self._deferred

    def describe(self, name, arguments):
        return f"{name} 실행"

    def execute(self, name, arguments):
        self.calls.append((name, arguments))
        return self._output


def _ollama_response(content="", tool_calls=None, prompt_eval=1000, eval_count=50):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return {
        "model": "qwen3:8b",
        "message": msg,
        "done": True,
        "prompt_eval_count": prompt_eval,
        "eval_count": eval_count,
    }


def _tool_call(name, arguments):
    return {"function": {"name": name, "arguments": arguments}}


def _patch_post(*responses):
    """OllamaBackend._post_chat 를 순서대로 응답하도록 바꾼다."""
    mock = MagicMock()
    if len(responses) == 1:
        mock.return_value = responses[0]
    else:
        mock.side_effect = list(responses)
    return patch.object(OllamaBackend, "_post_chat", mock), mock


# ── 백엔드 선택 ──


class TestBackendSelection:
    """전역 스위치가 아니라 역할별 env 다. 둘 다 미설정이면 현재와 동일해야 한다."""

    def test_기본값은_양쪽_다_anthropic(self):
        with patch.dict("os.environ", {}, clear=True):
            assert get_chat_backend().name == "anthropic"
            assert get_summary_backend().name == "anthropic"

    def test_요약만_로컬로_가르는_중간_상태(self):
        with patch.dict("os.environ", {"AGENT_SUMMARY_BACKEND": "ollama"}, clear=True):
            assert get_chat_backend().name == "anthropic"
            assert get_summary_backend().name == "ollama"

    def test_채팅만_로컬로_가르는_중간_상태(self):
        with patch.dict("os.environ", {"AGENT_CHAT_BACKEND": "ollama"}, clear=True):
            assert get_chat_backend().name == "ollama"
            assert get_summary_backend().name == "anthropic"

    def test_빈_문자열은_기본값(self):
        with patch.dict("os.environ", {"AGENT_CHAT_BACKEND": ""}, clear=True):
            assert get_chat_backend().name == "anthropic"

    def test_대소문자_공백_무시(self):
        with patch.dict("os.environ", {"AGENT_CHAT_BACKEND": "  Ollama "}, clear=True):
            assert get_chat_backend().name == "ollama"

    def test_모르는_이름은_터진다(self):
        """조용히 anthropic 으로 돌아가면 로컬인 줄 알고 과금한다."""
        with patch.dict("os.environ", {"AGENT_CHAT_BACKEND": "llamacpp"}, clear=True):
            with pytest.raises(ValueError, match="llamacpp"):
                get_chat_backend()

    def test_역할별_모델_env_가_따로_먹는다(self):
        env = {
            "AGENT_CHAT_BACKEND": "ollama",
            "AGENT_SUMMARY_BACKEND": "ollama",
            "OLLAMA_CHAT_MODEL": "qwen3:8b",
            "OLLAMA_SUMMARY_MODEL": "qwen3:4b",
        }
        with patch.dict("os.environ", env, clear=True):
            assert get_chat_backend().model == "qwen3:8b"
            assert get_summary_backend().model == "qwen3:4b"

    def test_anthropic_모델_env_는_그대로(self):
        with patch.dict("os.environ", {"AGENT_CHAT_MODEL": "claude-sonnet-5"}, clear=True):
            assert build_backend("anthropic", "chat").model == "claude-sonnet-5"


# ── 태깅 ──


class TestModelTag:
    """모델명만으로는 부족하다 — 토크나이저가 달라 토큰 수를 가로로 못 비교한다."""

    def test_anthropic_태그(self):
        assert AnthropicBackend("claude-haiku-4-5").model_tag() == (
            "anthropic:claude-haiku-4-5"
        )

    def test_ollama_태그는_모델명의_콜론도_보존한다(self):
        assert OllamaBackend("qwen3:8b").model_tag() == "ollama:qwen3:8b"

    def test_능력_플래그가_백엔드마다_다르다(self):
        assert OllamaBackend("qwen3:8b").supports_structured_output is True
        assert AnthropicBackend("claude-haiku-4-5").supports_structured_output is False


# ── <think> 제거 ──


class TestStripThink:
    def test_블록_전체를_지운다(self):
        assert strip_think("<think>고민중</think>안녕하세요") == "안녕하세요"

    def test_여러_블록(self):
        raw = "<think>a</think>첫째<think>b</think>둘째"
        assert strip_think(raw) == "첫째둘째"

    def test_줄바꿈이_들어간_블록(self):
        raw = "<think>\n한 줄\n두 줄\n</think>\n결과입니다"
        assert strip_think(raw) == "결과입니다"

    def test_닫히지_않은_여는_태그는_뒤를_통째로_버린다(self):
        """길이 제한에 걸려 끊기면 닫는 태그가 안 온다."""
        assert strip_think("답변입니다\n<think>여기서 잘림") == "답변입니다"

    def test_닫는_태그만_남은_경우(self):
        """템플릿이 여는 태그를 먹고 내보내는 경우가 있다."""
        assert strip_think("숨은 사고</think>실제 답변") == "실제 답변"

    def test_think_가_없으면_그대로(self):
        assert strip_think("그냥 답변") == "그냥 답변"

    def test_빈_문자열(self):
        assert strip_think("") == ""
        assert strip_think(None) == ""

    def test_대문자_태그도_지운다(self):
        assert strip_think("<THINK>x</THINK>답") == "답"

    def test_run_chat_응답에_think_가_남지_않는다(self):
        p, _ = _patch_post(_ollama_response(content="<think>흠</think>김도현입니다."))
        with p:
            result = OllamaBackend("qwen3:8b").run_chat(
                message="김도현 찾아줘",
                history=[],
                system_prompt="시스템",
                tools=FakeToolRunner(),
            )
        assert "<think>" not in result.reply
        assert result.reply == "김도현입니다."

    def test_도구_라운드의_이력에도_think_가_안_쌓인다(self):
        """지우지 않으면 다음 라운드 입력에 사고 과정이 그대로 실린다."""
        p, mock = _patch_post(
            _ollama_response(
                content="<think>검색해야지</think>찾아볼게요",
                tool_calls=[_tool_call("search_applications", {"q": "김도현"})],
            ),
            _ollama_response(content="<think>정리</think>1명 찾았습니다."),
        )
        with p:
            result = OllamaBackend("qwen3:8b").run_chat(
                message="김도현 찾아줘",
                history=[],
                system_prompt="시스템",
                tools=FakeToolRunner(),
            )
        second_payload = mock.call_args_list[1].args[0]
        assistant_turns = [m for m in second_payload["messages"] if m["role"] == "assistant"]
        assert assistant_turns
        assert all("<think>" not in m["content"] for m in assistant_turns)
        assert result.reply == "1명 찾았습니다."

    def test_complete_도_think_를_지운다(self):
        p, _ = _patch_post(_ollama_response(content='<think>음</think>{"a":1}'))
        with p:
            out = OllamaBackend("qwen3:8b").complete(prompt="p", max_tokens=500)
        assert out.text == '{"a":1}'


# ── 도구 스키마 변환 ──


class TestToolConversion:
    def test_input_schema_가_parameters_로_간다(self):
        defs = [{
            "name": "search_applications",
            "description": "지원자를 검색합니다",
            "input_schema": {
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
        }]
        converted = to_ollama_tools(defs)
        assert len(converted) == 1
        fn = converted[0]["function"]
        assert converted[0]["type"] == "function"
        assert fn["name"] == "search_applications"
        assert fn["description"] == "지원자를 검색합니다"
        assert fn["parameters"] == defs[0]["input_schema"]
        assert "input_schema" not in fn

    def test_실제_도구_정의_전부_변환된다(self):
        converted = to_ollama_tools(TOOL_DEFINITIONS)
        assert len(converted) == len(TOOL_DEFINITIONS)
        assert {c["function"]["name"] for c in converted} == {
            d["name"] for d in TOOL_DEFINITIONS
        }
        for c in converted:
            assert c["function"]["parameters"]["type"] == "object"

    def test_원본_정의를_변형하지_않는다(self):
        """tools/__init__.py 는 다른 도메인 소유다 — 건드리면 안 된다."""
        before = json.dumps(TOOL_DEFINITIONS, ensure_ascii=False, sort_keys=True)
        to_ollama_tools(TOOL_DEFINITIONS)
        after = json.dumps(TOOL_DEFINITIONS, ensure_ascii=False, sort_keys=True)
        assert before == after
        assert all("input_schema" in d for d in TOOL_DEFINITIONS)

    def test_스키마가_없으면_빈_객체(self):
        converted = to_ollama_tools([{"name": "noop"}])
        assert converted[0]["function"]["parameters"] == {
            "type": "object", "properties": {},
        }


# ── 비용 ──


class TestLocalCost:
    """로컬 추론은 과금이 없다. PRICING 의 haiku 폴백이 끼면 안 된다."""

    def test_run_chat_비용은_0(self):
        p, _ = _patch_post(_ollama_response(content="네", prompt_eval=9000, eval_count=800))
        with p:
            result = OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=[], system_prompt="시스템", tools=FakeToolRunner(),
            )
        assert result.cost_usd == 0.0
        assert result.input_tokens == 9000
        assert result.output_tokens == 800

    def test_complete_비용은_0(self):
        p, _ = _patch_post(_ollama_response(content="{}", prompt_eval=500, eval_count=20))
        with p:
            out = OllamaBackend("qwen3:8b").complete(prompt="p", max_tokens=500)
        assert out.cost_usd == 0.0

    def test_로컬_모델명이_PRICING_폴백에_안_닿는다(self):
        from app.agent.backends.anthropic_backend import PRICING, _estimate_cost

        assert "qwen3:8b" not in PRICING
        # 만약 중앙에서 계산했다면 haiku 단가가 붙었을 값
        would_be = _estimate_cost("qwen3:8b", 9000, 800)
        assert would_be > 0

        p, _ = _patch_post(_ollama_response(content="네", prompt_eval=9000, eval_count=800))
        with p:
            result = OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=[], system_prompt="시스템", tools=FakeToolRunner(),
            )
        assert result.cost_usd == 0.0

    def test_캐시_토큰은_0이고_backend_로_구분된다(self):
        """로컬에는 프롬프트 캐싱 개념이 없다 — '미적중'과 '개념 없음'의 구분은 backend."""
        p, _ = _patch_post(_ollama_response(content="네"))
        with p:
            result = OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=[], system_prompt="시스템", tools=FakeToolRunner(),
            )
        assert result.cache_write_tokens == 0
        assert result.cache_read_tokens == 0
        assert result.backend == "ollama"
        assert result.model == "ollama:qwen3:8b"


# ── 도구 루프 ──


class TestOllamaToolLoop:
    def test_읽기_도구는_바로_실행하고_루프를_잇는다(self):
        runner = FakeToolRunner(output='[{"id":1,"name":"김도현"}]')
        p, mock = _patch_post(
            _ollama_response(tool_calls=[_tool_call("search_applications", {"q": "김도현"})]),
            _ollama_response(content="1명 찾았습니다."),
        )
        with p:
            result = OllamaBackend("qwen3:8b").run_chat(
                message="김도현 찾아줘", history=[], system_prompt="시스템", tools=runner,
            )
        assert runner.calls == [("search_applications", {"q": "김도현"})]
        assert result.reply == "1명 찾았습니다."
        assert result.rounds == 2
        # 도구 결과가 tool 역할로 다시 들어간다
        second_payload = mock.call_args_list[1].args[0]
        assert any(m["role"] == "tool" for m in second_payload["messages"])

    def test_쓰기_도구는_실행하지_않고_pending_action(self):
        runner = FakeToolRunner(deferred={"change_stage"})
        p, _ = _patch_post(
            _ollama_response(
                content="바꿀까요?",
                tool_calls=[_tool_call("change_stage", {"application_id": 1, "to_stage": "screening"})],
            )
        )
        with p:
            result = OllamaBackend("qwen3:8b").run_chat(
                message="서류심사로", history=[], system_prompt="시스템", tools=runner,
            )
        assert runner.calls == []
        assert result.pending_action is not None
        assert result.pending_action.tool_name == "change_stage"
        assert result.pending_action.arguments["to_stage"] == "screening"

    def test_arguments_가_JSON_문자열로_와도_dict_로_받는다(self):
        runner = FakeToolRunner()
        p, _ = _patch_post(
            _ollama_response(tool_calls=[_tool_call("search_applications", '{"q": "김도현"}')]),
            _ollama_response(content="완료"),
        )
        with p:
            OllamaBackend("qwen3:8b").run_chat(
                message="x", history=[], system_prompt="시스템", tools=runner,
            )
        assert runner.calls == [("search_applications", {"q": "김도현"})]

    def test_MAX_ROUNDS_에서_멈춘다(self):
        from app.agent.backends.base import MAX_ROUNDS

        runner = FakeToolRunner()
        looping = _ollama_response(tool_calls=[_tool_call("search_applications", {"q": "x"})])
        mock = MagicMock(return_value=looping)
        with patch.object(OllamaBackend, "_post_chat", mock):
            result = OllamaBackend("qwen3:8b").run_chat(
                message="무한", history=[], system_prompt="시스템", tools=runner,
            )
        assert "제한" in result.reply
        assert len(runner.calls) == MAX_ROUNDS
        assert result.rounds == MAX_ROUNDS

    def test_system_프롬프트가_첫_메시지로_들어간다(self):
        p, mock = _patch_post(_ollama_response(content="네"))
        with p:
            OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=[], system_prompt="시스템 프롬프트", tools=FakeToolRunner(),
            )
        messages = mock.call_args.args[0]["messages"]
        assert messages[0] == {"role": "system", "content": "시스템 프롬프트"}
        assert messages[-1] == {"role": "user", "content": "안녕"}

    def test_이력_계약은_role_content_평문_그대로다(self):
        history = [
            {"role": "user", "content": "이전 질문"},
            {"role": "assistant", "content": "이전 답변"},
        ]
        p, mock = _patch_post(_ollama_response(content="네"))
        with p:
            OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=history, system_prompt="시스템", tools=FakeToolRunner(),
            )
        messages = mock.call_args.args[0]["messages"]
        assert messages[1:3] == history


# ── num_ctx / 잘림 경고 ──


class TestNumCtx:
    def test_num_ctx_를_항상_명시한다(self):
        """기본값이 작아서 긴 프롬프트가 조용히 잘린다."""
        p, mock = _patch_post(_ollama_response(content="네"))
        with p:
            OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=[], system_prompt="시스템", tools=FakeToolRunner(),
            )
        assert mock.call_args.args[0]["options"]["num_ctx"] == DEFAULT_NUM_CTX

    def test_env_로_num_ctx_를_바꾼다(self):
        with patch.dict("os.environ", {"OLLAMA_NUM_CTX": "32768"}, clear=True):
            backend = OllamaBackend("qwen3:8b")
        assert backend.num_ctx == 32768

    def test_잘못된_num_ctx_는_기본값(self):
        with patch.dict("os.environ", {"OLLAMA_NUM_CTX": "많이"}, clear=True):
            assert OllamaBackend("qwen3:8b").num_ctx == DEFAULT_NUM_CTX

    def test_컨텍스트가_거의_찼으면_경고(self, caplog):
        p, _ = _patch_post(_ollama_response(content="네", prompt_eval=DEFAULT_NUM_CTX - 10))
        with p, caplog.at_level("WARNING"):
            OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=[], system_prompt="시스템", tools=FakeToolRunner(),
            )
        assert "ollama_context_near_full" in caplog.text

    def test_입력_추정_대비_너무_적게_먹었으면_경고(self, caplog):
        p, _ = _patch_post(_ollama_response(content="네", prompt_eval=10))
        with p, caplog.at_level("WARNING"):
            OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=[], system_prompt="가" * 12000,
                tools=FakeToolRunner(),
            )
        assert "ollama_prompt_truncation_suspected" in caplog.text

    def test_정상_범위면_경고_없음(self, caplog):
        p, _ = _patch_post(_ollama_response(content="네", prompt_eval=4000))
        with p, caplog.at_level("WARNING"):
            OllamaBackend("qwen3:8b").run_chat(
                message="안녕", history=[], system_prompt="가" * 9000,
                tools=FakeToolRunner(),
            )
        assert "ollama_context_near_full" not in caplog.text
        assert "ollama_prompt_truncation_suspected" not in caplog.text


# ── 직렬화 락 ──


class TestSerialization:
    """GPU 가 하나라 로컬 추론은 직렬로만 돈다. /agent/chat 은 sync def 라
    FastAPI 스레드풀에서 병렬로 들어온다."""

    def test_추론_호출이_겹치지_않는다(self):
        import httpx

        overlap = []
        active = {"n": 0}
        guard = threading.Lock()

        def fake_post(url, json=None, timeout=None):
            with guard:
                active["n"] += 1
                if active["n"] > 1:
                    overlap.append(True)
            threading.Event().wait(0.02)
            with guard:
                active["n"] -= 1
            response = MagicMock(spec=httpx.Response)
            response.json.return_value = _ollama_response(content="네")
            response.raise_for_status.return_value = None
            return response

        backend = OllamaBackend("qwen3:8b")

        def call():
            backend.run_chat(
                message="안녕", history=[], system_prompt="시스템", tools=FakeToolRunner(),
            )

        with patch("httpx.post", side_effect=fake_post):
            threads = [threading.Thread(target=call) for _ in range(6)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert overlap == [], "로컬 추론 호출이 겹쳤다 — 직렬화 락이 안 걸렸다"

    def test_락은_모듈_수준이라_인스턴스마다_새로_생기지_않는다(self):
        from app.agent.backends import ollama_backend

        a = ollama_backend._INFERENCE_LOCK
        OllamaBackend("qwen3:8b")
        OllamaBackend("qwen3:4b")
        assert ollama_backend._INFERENCE_LOCK is a

    def test_anthropic_경로에는_락이_없다(self):
        import inspect

        from app.agent.backends import anthropic_backend

        source = inspect.getsource(anthropic_backend)
        assert "Lock" not in source
        assert "_INFERENCE_LOCK" not in source


# ── 구조화 출력 능력 플래그 ──


class TestStructuredOutput:
    def test_ollama_는_format_에_스키마를_싣는다(self):
        schema = {"type": "object", "properties": {"a": {"type": "string"}}}
        p, mock = _patch_post(_ollama_response(content="{}"))
        with p:
            OllamaBackend("qwen3:8b").complete(
                prompt="p", max_tokens=500, json_schema=schema,
            )
        assert mock.call_args.args[0]["format"] == schema

    def test_스키마가_없으면_format_키가_없다(self):
        p, mock = _patch_post(_ollama_response(content="{}"))
        with p:
            OllamaBackend("qwen3:8b").complete(prompt="p", max_tokens=500)
        assert "format" not in mock.call_args.args[0]

    def test_summarizer_는_플래그가_거짓이면_스키마를_안_넘긴다(self):
        from app.agent.summarizer import _call_llm

        backend = MagicMock()
        backend.supports_structured_output = False
        backend.complete.return_value = MagicMock(
            text=" {} ", input_tokens=10, output_tokens=5, cost_usd=0.001,
        )
        _call_llm(backend, "프롬프트", "chain_summarize")
        assert backend.complete.call_args.kwargs["json_schema"] is None

    def test_summarizer_는_플래그가_참이면_스키마를_넘긴다(self):
        from app.agent.summarizer import _STEP_SCHEMAS, _call_llm

        backend = MagicMock()
        backend.supports_structured_output = True
        backend.complete.return_value = MagicMock(
            text="{}", input_tokens=10, output_tokens=5, cost_usd=0.0,
        )
        _call_llm(backend, "프롬프트", "chain_evaluate")
        assert (
            backend.complete.call_args.kwargs["json_schema"]
            == _STEP_SCHEMAS["chain_evaluate"]
        )

    def test_parse_json_은_실패해도_예외가_아니라_None(self):
        """능력 플래그가 거짓일 때 기대는 폴백 — 계약이 바뀌면 안 된다."""
        from app.agent.summarizer import _parse_json

        assert _parse_json("이건 JSON이 아니다", "step1", 1) is None
        assert _parse_json('```json\n{"a":1}\n```', "step1", 1) == {"a": 1}
