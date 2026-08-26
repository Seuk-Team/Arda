"""에이전트 런타임 루프 테스트 — Claude API 를 mock 해서 핵심 로직 검증.

검증 대상:
- 쓰기 도구 호출 시 즉시 실행하지 않고 pending_action 반환
- 읽기 도구만 있으면 바로 실행
- MAX_ROUNDS 초과 시 안내 메시지
- 토큰 사용량 누적
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from app.agent.runtime import MAX_ROUNDS, AgentResult, run_agent


@dataclass
class FakeTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class FakeToolUseBlock:
    type: str = "tool_use"
    id: str = "tool_1"
    name: str = ""
    input: dict = None

    def __post_init__(self):
        if self.input is None:
            self.input = {}


@dataclass
class FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 50


@dataclass
class FakeResponse:
    content: list = None
    stop_reason: str = "end_turn"
    usage: FakeUsage = None

    def __post_init__(self):
        if self.content is None:
            self.content = []
        if self.usage is None:
            self.usage = FakeUsage()


def _make_mock_anthropic(*responses):
    """anthropic.Anthropic().messages.create 가 순서대로 응답을 돌려주는 mock."""
    mock_module = MagicMock()
    client = mock_module.Anthropic.return_value
    if len(responses) == 1:
        client.messages.create.return_value = responses[0]
    else:
        client.messages.create.side_effect = list(responses)
    return mock_module


def _make_deps():
    db = MagicMock()
    user = MagicMock()
    user.role = "recruiter"
    return db, user


def _run_with_mock(message, mock_module, execute_tool_return=None):
    """anthropic 모듈을 mock 으로 교체해서 run_agent 를 호출한다."""
    db, user = _make_deps()
    patches = [patch.dict("sys.modules", {"anthropic": mock_module})]
    if execute_tool_return is not None:
        patches.append(patch("app.agent.runtime.execute_tool", return_value=execute_tool_return))

    with patches[0]:
        if len(patches) > 1:
            with patches[1] as mock_exec:
                result = run_agent(message, [], db, user, "시스템 프롬프트")
                return result, mock_exec, db, user
        result = run_agent(message, [], db, user, "시스템 프롬프트")
        return result, None, db, user


class TestWriteToolPendingAction:
    """쓰기 도구가 나오면 실행하지 않고 pending_action 으로 반환해야 한다."""

    def test_change_stage_returns_pending(self):
        response = FakeResponse(
            content=[
                FakeTextBlock(text="단계를 변경하겠습니다."),
                FakeToolUseBlock(name="change_stage", input={
                    "application_id": 1,
                    "to_stage": "screening",
                }),
            ],
            stop_reason="tool_use",
        )
        mock_module = _make_mock_anthropic(response)
        result, _, _, _ = _run_with_mock("김도현 서류심사로", mock_module)

        assert result.pending_action is not None
        assert result.pending_action.tool_name == "change_stage"
        assert result.pending_action.arguments["to_stage"] == "screening"
        assert "변경" in result.pending_action.description

    def test_assign_interviewer_returns_pending(self):
        response = FakeResponse(
            content=[
                FakeToolUseBlock(name="assign_interviewer", input={
                    "application_id": 1,
                    "interviewer_ids": [2, 3],
                }),
            ],
            stop_reason="tool_use",
        )
        mock_module = _make_mock_anthropic(response)
        result, _, _, _ = _run_with_mock("면접관 배정해줘", mock_module)

        assert result.pending_action is not None
        assert result.pending_action.tool_name == "assign_interviewer"

    def test_draft_email_returns_pending(self):
        response = FakeResponse(
            content=[
                FakeToolUseBlock(name="draft_email", input={
                    "application_id": 1,
                    "purpose": "interview",
                }),
            ],
            stop_reason="tool_use",
        )
        mock_module = _make_mock_anthropic(response)
        result, _, _, _ = _run_with_mock("메일 초안 써줘", mock_module)

        assert result.pending_action is not None
        assert result.pending_action.tool_name == "draft_email"


class TestReadToolExecution:
    """읽기 도구는 바로 실행하고 루프를 계속한다."""

    def test_read_tool_executes_immediately(self):
        search_response = FakeResponse(
            content=[
                FakeToolUseBlock(name="search_applications", input={"q": "김도현"}),
            ],
            stop_reason="tool_use",
        )
        final_response = FakeResponse(
            content=[FakeTextBlock(text="김도현 지원자를 찾았습니다.")],
            stop_reason="end_turn",
        )
        mock_module = _make_mock_anthropic(search_response, final_response)
        result, mock_exec, _, _ = _run_with_mock(
            "김도현 찾아줘", mock_module,
            execute_tool_return='[{"id": 1, "name": "김도현"}]',
        )

        mock_exec.assert_called_once()
        assert mock_exec.call_args[0][0] == "search_applications"
        assert result.pending_action is None
        assert "찾았습니다" in result.reply


class TestTextOnlyResponse:
    """도구 호출 없이 텍스트만 응답하는 경우."""

    def test_text_reply(self):
        response = FakeResponse(
            content=[FakeTextBlock(text="안녕하세요, 무엇을 도와드릴까요?")],
            stop_reason="end_turn",
        )
        mock_module = _make_mock_anthropic(response)
        result, _, _, _ = _run_with_mock("안녕", mock_module)

        assert result.reply == "안녕하세요, 무엇을 도와드릴까요?"
        assert result.pending_action is None
        assert len(result.tool_calls) == 0


class TestTokenTracking:
    """토큰 사용량이 AgentResult 에 누적되는지."""

    def test_tokens_accumulate(self):
        r1 = FakeResponse(
            content=[FakeToolUseBlock(name="list_postings", input={})],
            stop_reason="tool_use",
            usage=FakeUsage(input_tokens=200, output_tokens=80),
        )
        r2 = FakeResponse(
            content=[FakeTextBlock(text="공고 목록입니다.")],
            stop_reason="end_turn",
            usage=FakeUsage(input_tokens=300, output_tokens=120),
        )
        mock_module = _make_mock_anthropic(r1, r2)
        result, _, _, _ = _run_with_mock(
            "공고 보여줘", mock_module, execute_tool_return='[]',
        )

        assert result.input_tokens == 500
        assert result.output_tokens == 200


class TestMaxRounds:
    """MAX_ROUNDS 초과 시 안내 메시지."""

    def test_exceeds_max_rounds(self):
        loop_response = FakeResponse(
            content=[FakeToolUseBlock(name="search_applications", input={"q": "test"})],
            stop_reason="tool_use",
        )
        mock_module = _make_mock_anthropic(loop_response)
        mock_module.Anthropic.return_value.messages.create.return_value = loop_response

        result, mock_exec, _, _ = _run_with_mock(
            "무한 검색", mock_module, execute_tool_return='[]',
        )

        assert "제한" in result.reply
        assert mock_exec.call_count == MAX_ROUNDS


class TestNoAnthropicPackage:
    """anthropic 패키지 없이 호출하면 안내 메시지."""

    def test_import_error_returns_message(self):
        db, user = _make_deps()
        with patch.dict("sys.modules", {"anthropic": None}):
            result = run_agent("테스트", [], db, user, "시스템 프롬프트")
        assert "anthropic" in result.reply.lower() or "설치" in result.reply
