"""비용 추정 + 확인 메시지 생성 테스트."""

import pytest

from app.agent.runtime import PRICING, _describe_action, _estimate_cost


class TestEstimateCost:
    """_estimate_cost 함수 검증."""

    def test_haiku_pricing(self):
        cost = _estimate_cost("claude-haiku-4-5-20251001", 1000, 500)
        expected = (1000 * 1.00 + 500 * 5.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_sonnet_pricing(self):
        cost = _estimate_cost("claude-sonnet-4-6", 1000, 500)
        expected = (1000 * 3.00 + 500 * 15.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_opus_pricing(self):
        cost = _estimate_cost("claude-opus-5", 1000, 500)
        expected = (1000 * 5.00 + 500 * 25.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_unknown_model_uses_fallback(self):
        cost = _estimate_cost("unknown-model", 1000, 500)
        expected = (1000 * 1.00 + 500 * 5.00) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_zero_tokens(self):
        assert _estimate_cost("claude-haiku-4-5-20251001", 0, 0) == 0.0

    def test_input_only(self):
        cost = _estimate_cost("claude-haiku-4-5-20251001", 1_000_000, 0)
        assert cost == pytest.approx(1.00)

    def test_output_only(self):
        cost = _estimate_cost("claude-haiku-4-5-20251001", 0, 1_000_000)
        assert cost == pytest.approx(5.00)

    def test_all_models_in_pricing_table(self):
        for model, (inp, out) in PRICING.items():
            cost = _estimate_cost(model, 100, 100)
            expected = (100 * inp + 100 * out) / 1_000_000
            assert cost == pytest.approx(expected), f"{model} pricing mismatch"


class TestDescribeAction:
    """_describe_action 확인 메시지 검증."""

    def test_change_stage(self):
        desc = _describe_action("change_stage", {
            "application_id": 42,
            "to_stage": "screening",
        })
        assert "#42" in desc
        assert "screening" in desc
        assert "변경" in desc

    def test_assign_interviewer(self):
        desc = _describe_action("assign_interviewer", {
            "application_id": 10,
            "interviewer_ids": [2, 3],
        })
        assert "#10" in desc
        assert "면접관" in desc
        assert "[2, 3]" in desc

    def test_draft_email(self):
        desc = _describe_action("draft_email", {
            "application_id": 5,
            "purpose": "interview",
        })
        assert "#5" in desc
        assert "interview" in desc
        assert "이메일" in desc

    def test_draft_email_default_purpose(self):
        desc = _describe_action("draft_email", {
            "application_id": 5,
        })
        assert "general" in desc

    def test_unknown_tool(self):
        desc = _describe_action("some_tool", {"x": 1})
        assert "some_tool" in desc
