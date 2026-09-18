"""면접 중 실시간 분석 요약 (2026-09-17) — 센다 → 줄인다 → AI 문장 + 검사.

**문장 속 숫자는 전부 센 값이어야 한다.** 이 규칙이 풀리면 AI 가 지어낸 수치가
종합 평가에 근거처럼 뜬다 — 서류↔발언 대조가 원문에 없는 인용을 버리는 것과 같은 자리.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.interview import live_summary as ls


def _verdict(truth=70.0, top="무표정", blink=0.4, head=False, pitch=180.0):
    signals = [{"key": "눈 깜빡임", "value": f"{blink}회/초 (정상)", "flag": "normal"}]
    if head:
        signals.append({"key": "고개 움직임", "value": "많음", "flag": "high"})
    return {
        "truth_pct": truth,
        "lie_pct": 100 - truth,
        "signals": signals,
        "expressions": [
            {"label": "neutral", "label_ko": top, "prob": 0.8},
            {"label": "happy", "label_ko": "기쁨", "prob": 0.1},
        ],
        "voice": {"pitch_hz": pitch, "pitch_var_st": 2.0, "loud_var_db": 4.0, "voiced_pct": 50.0},
    }


def _session(samples=None):
    return SimpleNamespace(truth_samples=samples)


class TestRecord:
    def test_전체와_질문별로_센다(self):
        s, db = _session(), MagicMock()
        ls.record_live_sample(db, s, _verdict(80.0, "무표정", 0.4), 1)
        ls.record_live_sample(db, s, _verdict(60.0, "긴장", 0.8, head=True), 2)
        ls.record_live_sample(db, s, _verdict(70.0, "긴장", 0.6), 2)

        t = s.truth_samples
        assert t["n"] == 3 and t["truth_sum"] == 210.0
        assert t["expr"] == {"무표정": 1, "긴장": 2}
        assert t["by_q"]["1"]["n"] == 1
        assert t["by_q"]["2"]["expr"] == {"긴장": 2}
        assert t["by_q"]["2"]["flags"] == {"고개 움직임": 1}
        assert db.commit.call_count == 3

    def test_옛_진위_집계와_같은_자리다(self):
        """`screening.truth_consistency` 가 그대로 읽어야 한다."""
        from app.application.screening import truth_consistency

        s = _session({"n": 2, "truth_sum": 120.0})  # 이 변경 전에 쌓인 모양
        ls.record_live_sample(MagicMock(), s, {"truth_pct": 90.0}, None)
        assert truth_consistency(s.truth_samples) == 70

    def test_옛_호출도_그대로_된다(self):
        from app.interview.scoring import record_truth_sample

        s = _session()
        record_truth_sample(MagicMock(), s, 55.0)
        assert s.truth_samples == {"n": 1, "truth_sum": 55.0}

    def test_질문을_모르면_전체에만_센다(self):
        s = _session()
        ls.record_live_sample(MagicMock(), s, _verdict(), None)
        assert "by_q" not in s.truth_samples


class TestStats:
    def _samples(self):
        s = _session()
        for v, q in [
            (_verdict(80.0, "무표정", 0.4), 1),
            (_verdict(60.0, "긴장", 0.8, head=True, pitch=200.0), 2),
            (_verdict(70.0, "긴장", 0.6, pitch=220.0), 2),
        ]:
            ls.record_live_sample(MagicMock(), s, v, q)
        return s.truth_samples

    def test_사람이_읽을_숫자로_줄인다(self):
        st = ls.live_stats(self._samples())
        o = st["overall"]
        assert o["n"] == 3 and o["truth"] == 70
        assert o["expressions"][0] == {"label": "긴장", "pct": 67}
        assert o["blink_per_sec"] == 0.6
        assert o["flags_pct"] == {"고개 움직임": 33}
        assert o["voice"]["pitch_hz"] == 200

        q2 = st["per_question"][1]
        assert q2["seq"] == 2 and q2["truth"] == 65 and q2["blink_per_sec"] == 0.7

    def test_판정이_없으면_None(self):
        assert ls.live_stats(None) is None
        assert ls.live_stats({"n": 0}) is None


class TestCheck:
    STATS = {"overall": {"n": 57, "truth": 64, "expressions": [{"label": "긴장", "pct": 35}], "blink_per_sec": 0.8},
             "per_question": [{"seq": 1, "n": 30, "truth": 72}]}

    def test_센_숫자만_쓰면_통과(self):
        text = "실시간 분석 57회 동안 진위 평균은 64%였고, Q1 에서는 72%였다. 긴장 표정이 35%로 가장 많았고 눈 깜빡임은 0.8회/초였다."
        assert ls.check_summary(text, self.STATS) is None

    def test_지어낸_숫자가_있으면_버린다(self):
        assert ls.check_summary("진위 평균은 65%였다.", self.STATS) == "수치에 없는 숫자: 65"

    def test_계산한_숫자도_버린다(self):
        """72 - 64 = 8 — 적힌 값이 아니다."""
        assert ls.check_summary("Q1 은 전체보다 8%p 높았다.", self.STATS) is not None

    def test_사람을_단정하면_버린다(self):
        assert ls.check_summary("긴장 표정이 35%로 자신감이 부족해 보였다.", self.STATS).startswith("금지어")

    def test_틀_문장은_검사를_통과한다(self):
        text = ls.template_summary(self.STATS)
        assert ls.check_summary(text, self.STATS) is None
        assert "57회" in text and "64%" in text


class TestSummarize:
    STATS = TestCheck.STATS

    def test_프롬프트는_수치만_받는다(self):
        """전사·이력서를 넣지 않는다 — 수치 밖의 말로 사람을 해석할 재료를 주지 않는다."""
        from app.agent.prompts import variables

        assert variables("interview_live_summary") == {"stats_json"}

    def _run(self, raw: str):
        with patch("app.agent.summarizer._call_llm", return_value=(raw, 0, 0, 0.0, "end_turn")):
            return ls.summarize(MagicMock(), self.STATS)

    def test_AI_문장을_쓴다(self):
        out = self._run('{"summary": "실시간 분석 57회, 진위 평균 64%였다."}')
        assert out["summary_source"] == "ai"
        assert out["summary"] == "실시간 분석 57회, 진위 평균 64%였다."
        assert out["prompt"] == "interview_live_summary.v1"

    def test_검사에_걸리면_틀_문장으로(self):
        out = self._run('{"summary": "진위 평균 99%였다."}')
        assert out["summary_source"] == "template"
        assert out["rejected"] == "수치에 없는 숫자: 99"
        assert "64%" in out["summary"]

    def test_AI_가_실패하면_틀_문장으로(self):
        with patch("app.agent.summarizer._call_llm", side_effect=RuntimeError("503")):
            out = ls.summarize(MagicMock(), self.STATS)
        assert out["summary_source"] == "template"
