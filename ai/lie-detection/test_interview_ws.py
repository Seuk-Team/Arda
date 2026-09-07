"""발화 끝 판정 테스트.

이게 틀리면 면접이 안 돈다 — 말하는 중에 끊고 들어가거나, 말을 마쳐도
다음 질문이 안 나온다. 마이크가 필요 없도록 PCM 을 직접 만들어 넣는다.
"""

from __future__ import annotations

import time

import numpy as np

from interview_ws import (
    MIN_SPEECH_SEC,
    SAMPLE_RATE,
    SILENCE_END_SEC,
    InterviewSession,
    _SpeechDetector,
)

CHUNK_SEC = 0.05
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_SEC)


def _pcm(amplitude: int) -> bytes:
    """무음(0)이나 일정한 크기의 소리 한 조각."""
    if amplitude == 0:
        return np.zeros(CHUNK_SAMPLES, dtype=np.int16).tobytes()
    rng = np.random.default_rng(0)
    return (rng.normal(0, amplitude, CHUNK_SAMPLES)).astype(np.int16).tobytes()


QUIET = _pcm(0)
LOUD = _pcm(4000)


def _calibrate(det: _SpeechDetector) -> None:
    """접속 초반 조용한 구간. 이게 지나야 판정이 시작된다."""
    for _ in range(10):
        det.feed(QUIET)


class TestSpeechDetector:
    def test_보정_전에는_판정하지_않는다(self):
        det = _SpeechDetector()
        # 첫 조각부터 시끄러워도 아직 기준이 없다
        assert det.feed(LOUD) is None

    def test_말을_시작하면_begin(self):
        det = _SpeechDetector()
        _calibrate(det)
        assert det.feed(LOUD) == "begin"

    def test_말하는_중에는_끊지_않는다(self):
        """문장 사이의 짧은 쉼으로 질문이 넘어가면 안 된다."""
        det = _SpeechDetector()
        _calibrate(det)
        det.feed(LOUD)
        time.sleep(MIN_SPEECH_SEC + 0.05)
        # SILENCE_END_SEC 보다 짧은 쉼
        assert det.feed(QUIET) is None
        time.sleep(SILENCE_END_SEC / 2)
        assert det.feed(QUIET) is None

    def test_충분히_조용해지면_end(self):
        det = _SpeechDetector()
        _calibrate(det)
        det.feed(LOUD)
        time.sleep(MIN_SPEECH_SEC + 0.05)
        det.feed(QUIET)
        time.sleep(SILENCE_END_SEC + 0.05)
        assert det.feed(QUIET) == "end"

    def test_기침처럼_짧은_소리는_답변이_아니다(self):
        """문 닫는 소리로 질문이 넘어가면 안 된다."""
        det = _SpeechDetector()
        _calibrate(det)
        det.feed(LOUD)  # begin
        det.feed(QUIET)
        time.sleep(SILENCE_END_SEC + 0.05)
        # MIN_SPEECH_SEC 를 못 채웠으므로 end 가 아니다
        assert det.feed(QUIET) is None

    def test_다시_말하면_또_begin(self):
        det = _SpeechDetector()
        _calibrate(det)
        det.feed(LOUD)
        time.sleep(MIN_SPEECH_SEC + 0.05)
        det.feed(QUIET)
        time.sleep(SILENCE_END_SEC + 0.05)
        assert det.feed(QUIET) == "end"
        assert det.feed(LOUD) == "begin"


class TestSession:
    def test_답변을_꺼내면_비워진다(self):
        """다음 답변이 앞 답변 소리를 물고 가면 안 된다."""
        s = InterviewSession("tok")
        s.add_audio(LOUD)
        s.add_audio(LOUD)
        pcm, _ = s.take_answer()
        assert len(pcm) == len(LOUD) * 2
        again, _ = s.take_answer()
        assert again == b""

    def test_프레임이_적으면_신호를_내지_않는다(self):
        """없는 것이 틀린 것보다 낫다."""
        s = InterviewSession("tok")
        assert s.signal([[0.3] * 7 for _ in range(4)]) is None

    def test_프레임이_충분하면_신호를_낸다(self):
        s = InterviewSession("tok")
        sig = s.signal([[0.3] * 7 for _ in range(20)])
        assert sig is not None
        assert sig["frames"] == 20
        assert set(sig) == {"frames", "eye_openness", "blink_variation", "head_movement", "asymmetry"}

    def test_깨진_프레임은_버린다(self):
        """JPEG 이 아닌 것이 와도 연결이 죽으면 안 된다."""
        s = InterviewSession("tok")
        for _ in range(6):
            s.add_frame(b"not a jpeg")
        assert s.frames == []
