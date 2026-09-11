"""면접 진행 보조 규칙 (ADR-0026 결정 4).

여기서 보는 것은 **"제안이 판정으로 새지 않는가"** 다. 점수가 없어야 하고,
아무 문제가 없을 때는 아무 말도 하지 않아야 하고, 되묻기가 추궁이 되지
않아야 한다.
"""

from __future__ import annotations

from dataclasses import fields

from app.interview import pacing

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


class Test발화_속도:
    """음성으로 답했을 때만 볼 수 있다 (2026-09-07, 설계 §5-4 이후)."""

    def test_말이_유난히_느리면_질문을_바꾸자고_한다(self):
        # 33자를 30초에 = 1.1자/초
        hint = pacing.suggest(긴_답, audio_duration_sec=30.0)
        assert hint is not None
        assert hint.action == "rephrase"

    def test_보통_속도면_아무_말도_안_한다(self):
        # 같은 답을 6초에 = 5.5자/초
        assert pacing.suggest(긴_답, audio_duration_sec=6.0) is None

    def test_텍스트로_답하면_속도를_안_본다(self):
        """`audio_duration_sec` 이 없으면 길이만 본다 — 없는 것을 신호로 쓰지 않는다."""
        assert pacing.suggest(긴_답) is None

    def test_너무_짧은_녹음은_속도를_재지_않는다(self):
        """2초짜리는 첫 한마디 뜸들이는 것만으로 속도가 반토막 난다."""
        assert pacing.suggest(긴_답, audio_duration_sec=2.0) is None

    def test_짧은_답이_속도보다_먼저다(self):
        """두 글자짜리 답의 초당 글자 수는 사람에 대한 정보가 아니다."""
        hint = pacing.suggest(짧은_답, audio_duration_sec=30.0)
        assert hint is not None
        assert hint.action == "follow_up"


class Test평가로_새지_않는다:
    """ADR-0026 결정 4 — 점수에 넣지 않는다. 구조로 막혀 있어야 한다."""

    def test_점수에_해당하는_값이_아예_없다(self):
        hint = pacing.suggest(짧은_답)
        assert hint is not None
        names = {f.name for f in fields(hint)}
        assert names == {"action", "message"}

    def test_행동은_정해진_셋_중_하나다(self):
        """새 action 을 늘릴 때 여기서 한 번 걸리게 한다 — 판정어가 끼어들지 않게."""
        cases = [
            (짧은_답, [], None),
            (짧은_답, [짧은_답], None),
            (긴_답, [], 30.0),
        ]
        for transcript, earlier, duration in cases:
            hint = pacing.suggest(transcript, earlier, audio_duration_sec=duration)
            assert hint is not None
            assert hint.action in {"follow_up", "offer_break", "rephrase"}

    def test_느린_답에도_심리_추론을_적지_않는다(self):
        """"긴장" 같은 말을 넣는 순간 ADR-0026 결정 2 를 넘는다."""
        hint = pacing.suggest(긴_답, audio_duration_sec=30.0)
        assert hint is not None
        for 금지어 in ("긴장", "불안", "거짓", "의심", "점수"):
            assert 금지어 not in hint.message
