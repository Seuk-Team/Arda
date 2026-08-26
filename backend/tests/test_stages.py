"""단계 전환 규칙 테스트 — DB 불필요, 순수 로직."""

import pytest

from app.stages import StageTransitionError, validate_transition


class TestForwardTransition:
    """정상 전진: applied → screening → interview → accepted."""

    @pytest.mark.parametrize("from_,to_", [
        ("applied", "screening"),
        ("screening", "interview"),
        ("interview", "accepted"),
    ])
    def test_one_step_forward(self, from_, to_):
        validate_transition(from_, to_)

    def test_skip_forward_raises(self):
        with pytest.raises(StageTransitionError, match="건너뛸 수 없습니다"):
            validate_transition("applied", "interview")

    def test_skip_two_steps_raises(self):
        with pytest.raises(StageTransitionError, match="건너뛸 수 없습니다"):
            validate_transition("applied", "accepted")


class TestRejection:
    """불합격은 어느 단계에서든 가능."""

    @pytest.mark.parametrize("from_", ["applied", "screening", "interview", "accepted"])
    def test_reject_from_any(self, from_):
        validate_transition(from_, "rejected")

    def test_return_from_rejected(self):
        validate_transition("rejected", "screening")


class TestBackward:
    """뒤로 이동은 허용 (담당자가 되돌리는 경우)."""

    @pytest.mark.parametrize("from_,to_", [
        ("screening", "applied"),
        ("interview", "screening"),
        ("accepted", "interview"),
    ])
    def test_backward_allowed(self, from_, to_):
        validate_transition(from_, to_)


class TestEdgeCases:
    def test_same_stage_raises(self):
        with pytest.raises(StageTransitionError, match="이미"):
            validate_transition("applied", "applied")

    def test_unknown_stage_raises(self):
        with pytest.raises(StageTransitionError, match="알 수 없는 단계"):
            validate_transition("applied", "nonexistent")
