"""지원자 채팅 FAQ 응답 검증 (LLM 은 전부 가짜, 실호출 없음)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.agent import faq
from app.agent.backends.base import CompletionResult


def _posting(title="백엔드", description="Python 3년 이상. Docker 우대."):
    return SimpleNamespace(id=1, title=title, description=description)


def _fake_backend(text="React 를 우대 조건으로 언급하고 있어요.", unavailable=None):
    b = MagicMock()
    b.unavailable_reason.return_value = unavailable
    b.model_tag.return_value = "anthropic:claude-haiku-4-5-20251001"
    b.model = "claude-haiku-4-5-20251001"
    b.complete.return_value = CompletionResult(
        text=text, input_tokens=800, output_tokens=120, cost_usd=0.00136,
    )
    return b


class TestAnswerQuestion:
    def test_공고_내용을_프롬프트에_넣는다(self):
        with patch.object(faq, "get_chat_backend") as mock_get:
            mock_get.return_value = _fake_backend()
            answer, cost, tag = faq.answer_question(_posting(), "우대 조건이 뭔가요?")
        assert answer == "React 를 우대 조건으로 언급하고 있어요."
        assert cost == pytest.approx(0.00136)
        assert "anthropic" in tag

        # 프롬프트에 공고 제목·설명·질문이 실렸는지
        _, kwargs = mock_get.return_value.complete.call_args
        prompt = kwargs["prompt"]
        assert "백엔드" in prompt
        assert "Python 3년 이상" in prompt
        assert "우대 조건이 뭔가요?" in prompt

    def test_긴_질문은_500자로_잘린다(self):
        # 잘림 확인은 "긴 반복 블록"의 존재 여부로 — 프롬프트 템플릿 자체에 있는
        # 몇 개의 '가' 는 세지 않는다
        with patch.object(faq, "get_chat_backend") as mock_get:
            mock_get.return_value = _fake_backend()
            faq.answer_question(_posting(), "가" * 900)
        prompt = mock_get.return_value.complete.call_args.kwargs["prompt"]
        assert "가" * 500 in prompt
        assert "가" * 501 not in prompt

    def test_공고_설명이_비면_안내_문구로_대체(self):
        with patch.object(faq, "get_chat_backend") as mock_get:
            mock_get.return_value = _fake_backend()
            faq.answer_question(_posting(description=None), "복리후생?")
        prompt = mock_get.return_value.complete.call_args.kwargs["prompt"]
        assert "(설명 없음)" in prompt

    def test_지원자_상태가_프롬프트에_들어간다(self):
        """개인 문의(다음 일정·현재 단계)에 답할 근거."""
        ctx = "- 현재 전형 단계: 면접\n- 다음 일정: 면접 확정 — 2026.09.03 (목) 14:00 ~ 15:00"
        with patch.object(faq, "get_chat_backend") as mock_get:
            mock_get.return_value = _fake_backend()
            faq.answer_question(_posting(), "다음 일정 언제죠?", applicant_context=ctx)
        prompt = mock_get.return_value.complete.call_args.kwargs["prompt"]
        assert "지원자 본인의 상태" in prompt
        assert "면접 확정" in prompt
        assert "2026.09.03 (목) 14:00" in prompt

    def test_상태_컨텍스트가_비면_기본값(self):
        with patch.object(faq, "get_chat_backend") as mock_get:
            mock_get.return_value = _fake_backend()
            faq.answer_question(_posting(), "질문")
        prompt = mock_get.return_value.complete.call_args.kwargs["prompt"]
        assert "(추가 정보 없음)" in prompt

    def test_백엔드_사용_불가면_예외(self):
        with patch.object(faq, "get_chat_backend") as mock_get:
            mock_get.return_value = _fake_backend(unavailable="ANTHROPIC_API_KEY 미설정")
            with pytest.raises(RuntimeError, match="API_KEY"):
                faq.answer_question(_posting(), "질문")
