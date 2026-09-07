"""면접 진행 보조 규칙 (ADR-0026 결정 4).

여기서 보는 것은 **"제안이 판정으로 새지 않는가"** 다. 점수가 없어야 하고,
아무 문제가 없을 때는 아무 말도 하지 않아야 하고, 되묻기가 추궁이 되지
않아야 한다.
"""

from __future__ import annotations

from dataclasses import fields

from app import interview_pacing as pacing

긴_답 = "제가 맡은 부분은 결제 정산 API 였고 응답 시간을 절반으로 줄였습니다"
짧은_답 = "네"


class Test제안하지_않을_때:
    def test_충분히_답하면_아무_말도_안_한다(self):
        """매 답변마다 뭔가 말하면 지원자는 계속 지적받는 느낌을 받는다."""
        assert pacing.suggest(긴_답) is None

    def test_앞이_짧았어도_이번이_충분하면_안_한다(self):
        assert pacing.suggest(긴_답, [짧은_답]) is None


class Test짧은_답:
    def test_한_번_짧으면_되묻는다(self):
        hint = pacing.suggest(짧은_답)
        assert hint is not None
        assert hint.action == "follow_up"
        assert hint.message  # 지원자에게 그대로 보여줄 문장이 있어야 한다

    def test_연속으로_짧으면_되묻는_대신_쉬어가기를_권한다(self):
        """두 번 연속 짧은 것은 그 질문 하나의 문제가 아닐 수 있다.

        계속 되물으면 추궁이 된다.
        """
        hint = pacing.suggest(짧은_답, [짧은_답])
        assert hint is not None
        assert hint.action == "offer_break"

    def test_공백만_많은_답은_길다고_보지_않는다(self):
        hint = pacing.suggest("네    \n\n  ")
        assert hint is not None
        assert hint.action == "follow_up"


class Test평가로_새지_않는다:
    """ADR-0026 결정 4 — 점수에 넣지 않는다. 구조로 막혀 있어야 한다."""

    def test_점수에_해당하는_값이_아예_없다(self):
        hint = pacing.suggest(짧은_답)
        assert hint is not None
        names = {f.name for f in fields(hint)}
        assert names == {"action", "message"}

    def test_행동은_정해진_둘_중_하나다(self):
        """새 action 을 늘릴 때 여기서 한 번 걸리게 한다 — 판정어가 끼어들지 않게."""
        for transcript, earlier in [(짧은_답, []), (짧은_답, [짧은_답])]:
            hint = pacing.suggest(transcript, earlier)
            assert hint is not None
            assert hint.action in {"follow_up", "offer_break"}
