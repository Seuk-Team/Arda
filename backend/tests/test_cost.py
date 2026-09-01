"""비용 추정 + 확인 메시지 생성 테스트."""

from unittest.mock import MagicMock

import pytest

from app.agent.runtime import PRICING, _describe_action, _estimate_cost


def _mock_db(name="홍길동", education="서울대 컴공"):
    """_applicant_label 이 DB 없이 동작하게 하는 가짜 세션."""
    app = MagicMock()
    app.name = name
    app.education = education
    db = MagicMock()
    db.get.return_value = app
    return db


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
        }, _mock_db())
        assert "홍길동" in desc
        assert "서류심사" in desc
        assert "변경" in desc

    def test_assign_interviewer(self):
        desc = _describe_action("assign_interviewer", {
            "application_id": 10,
            "interviewer_ids": [2, 3],
        }, _mock_db())
        assert "홍길동" in desc
        assert "면접관" in desc
        assert "2명" in desc

    def test_create_schedule_proposal(self):
        desc = _describe_action("create_schedule_proposal", {
            "application_id": 7,
            "max_slots": 3,
        }, _mock_db())
        assert "홍길동" in desc
        assert "면접 일정" in desc
        assert "3개" in desc

    def test_draft_email(self):
        desc = _describe_action("draft_email", {
            "application_id": 5,
            "purpose": "interview",
        }, _mock_db())
        assert "홍길동" in desc
        assert "면접 안내" in desc
        assert "이메일" in desc

    def test_draft_email_default_purpose(self):
        desc = _describe_action("draft_email", {
            "application_id": 5,
        }, _mock_db())
        assert "안내" in desc

    def test_unknown_tool(self):
        desc = _describe_action("some_tool", {"x": 1}, _mock_db())
        assert "some_tool" in desc

    def test_applicant_not_found_fallback(self):
        db = MagicMock()
        db.get.return_value = None
        desc = _describe_action("change_stage", {
            "application_id": 99,
            "to_stage": "interview",
        }, db)
        assert "#99" in desc


class TestEstimateCostWithCache:
    """캐시 요율 반영 검증 — 캐시 항을 빼먹으면 비용이 실제보다 작게 나온다."""

    def test_cache_write_is_1_25x_input(self):
        cost = _estimate_cost("claude-haiku-4-5", 0, 0, cache_write_tokens=1_000_000)
        assert cost == pytest.approx(1.25)

    def test_cache_read_is_0_1x_input(self):
        cost = _estimate_cost("claude-haiku-4-5", 0, 0, cache_read_tokens=1_000_000)
        assert cost == pytest.approx(0.10)

    def test_cache_args_default_to_zero(self):
        """기존 호출부(2인자)의 결과가 달라지면 안 된다."""
        assert _estimate_cost("claude-haiku-4-5", 1000, 500) == pytest.approx(
            _estimate_cost("claude-haiku-4-5", 1000, 500, 0, 0)
        )

    def test_all_terms_sum(self):
        cost = _estimate_cost("claude-haiku-4-5", 1000, 500, 2000, 4000)
        expected = (
            1000 * 1.00 + 500 * 5.00 + 2000 * 1.00 * 1.25 + 4000 * 1.00 * 0.10
        ) / 1_000_000
        assert cost == pytest.approx(expected)

    def test_캐시_읽기가_정가보다_싸다(self):
        """같은 토큰 수라면 캐시 읽기가 항상 더 싸야 한다 — 이게 캐싱의 목적이다."""
        uncached = _estimate_cost("claude-haiku-4-5", 10_000, 0)
        cached = _estimate_cost("claude-haiku-4-5", 0, 0, cache_read_tokens=10_000)
        assert cached < uncached
