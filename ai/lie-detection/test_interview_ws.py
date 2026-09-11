"""발화 끝 판정 테스트.

이게 틀리면 면접이 안 돈다 — 말하는 중에 끊고 들어가거나, 말을 마쳐도
다음 질문이 안 나온다. 마이크가 필요 없도록 PCM 을 직접 만들어 넣는다.
"""

from __future__ import annotations

import asyncio
import time

import numpy as np

import interview_ws as iw
from interview_ws import (
    LIVE_EVERY_SEC,
    MIN_NOISE,
    MIN_SPEECH_SEC,
    SAMPLE_RATE,
    SAMPLE_WIDTH,
    SILENCE_END_SEC,
    InterviewSession,
    LiveScorer,
    _SpeechDetector,
    score,
)

CHUNK_SEC = 0.05
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_SEC)


def _pcm(amplitude: int) -> bytes:
    """무음(0)이나 일정한 크기의 소리 한 조각."""
    if amplitude == 0:
        return np.zeros(CHUNK_SAMPLES, dtype=np.int16).tobytes()
    rng = np.random.default_rng(0)
    return (rng.normal(0, amplitude, CHUNK_SAMPLES)).astype(np.int16).tobytes()


DEAD = _pcm(0)        # 마이크 예열 — 디지털 무음. **소리로 세지 않는다**
QUIET = _pcm(120)     # 조용한 방. 바닥값이 여기서 잡힌다
LOUD = _pcm(4000)     # 말소리


def _calibrate(det: _SpeechDetector) -> None:
    """접속 초반 조용한 구간. 이게 지나야 판정이 시작된다."""
    for _ in range(12):
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


class TestLiveScorer:
    """말하는 동안 굴러가는 판정. 창 밖으로 나간 것은 버려야 한다."""

    def test_창_길이만큼만_소리를_들고_있다(self):
        s = LiveScorer(window_sec=1.0)
        for _ in range(60):  # 3초치를 넣어도
            s.add_audio(LOUD)
        assert len(s.snapshot()[0]) == int(1.0 * SAMPLE_RATE * SAMPLE_WIDTH)

    def test_창_밖의_얼굴은_버린다(self):
        s = LiveScorer(window_sec=2.0)
        s.add_face([0.0] * 7, now=100.0)
        s.add_face([1.0] * 7, now=101.0)
        s.add_face([2.0] * 7, now=103.0)  # 이 시점에 100.0 은 창 밖
        rows = s.snapshot()[1]
        assert rows == [[1.0] * 7, [2.0] * 7]

    def test_주기보다_자주는_판정하지_않는다(self):
        s = LiveScorer()
        assert s.due(100.0) is True
        assert s.due(100.0 + LIVE_EVERY_SEC / 2) is False
        assert s.due(100.0 + LIVE_EVERY_SEC) is True


class TestScore:
    """재료가 모자라면 **판정을 내지 않는다.** 0 으로 채운 숫자가 나가면
    사람은 그것을 판정으로 읽는다."""

    def test_얼굴이_없으면_판정하지_않는다(self):
        out = score(LOUD * 100, rows=[], seconds=4.0)
        assert out["ok"] is False and "얼굴" in out["reason"]

    def test_소리가_짧으면_판정하지_않는다(self):
        rows = [[0.2, 0.2, 0.05, 10.0, 10.0, 0.0, 0.0]] * 10
        out = score(LOUD, rows=rows, seconds=4.0)  # 0.05초
        assert out["ok"] is False and "소리" in out["reason"]

    def test_재료가_있으면_확률과_얼굴신호를_같이_낸다(self):
        rng = np.random.default_rng(1)
        pcm = (rng.normal(0, 3000, SAMPLE_RATE * 3)).astype(np.int16).tobytes()
        rows = [
            [0.25 + i * 0.001, 0.25, 0.05, 10.0, 10.0, 0.01, 0.0] for i in range(30)
        ]
        out = score(pcm, rows=rows, seconds=4.0)
        assert out["ok"] is True
        assert out["pred"] in (0, 1)
        assert abs(out["truth_pct"] + out["lie_pct"] - 100.0) < 0.2
        assert any(s["key"] == "눈 깜빡임" for s in out["signals"])

    def test_목소리_지표를_같이_낸다(self):
        """판정 벡터 100개 중 86개가 목소리다 (2026-09-11). 200Hz 한 음을 그대로 내면
        음 높이는 200 근처, 억양 폭은 0 에 가깝게 나와야 한다."""
        t = np.arange(SAMPLE_RATE * 3) / SAMPLE_RATE
        pcm = (np.sin(2 * np.pi * 200 * t) * 8000).astype(np.int16).tobytes()
        rows = [
            [0.25 + i * 0.001, 0.25, 0.05, 10.0, 10.0, 0.01, 0.0] for i in range(30)
        ]
        out = score(pcm, rows=rows, seconds=4.0)
        assert out["ok"] is True
        v = out["voice"]
        assert abs(v["pitch_hz"] - 200) < 10
        assert v["pitch_var_st"] < 0.5
        assert v["voiced_pct"] > 50
        assert {"loud_db", "loud_var_db"} <= set(v)

    def test_판정_벡터는_예전_계산과_숫자까지_같다(self):
        """model.pkl 은 예전 계산으로 배웠다. 지표를 붙이면서 벡터가 바뀌면 판정이
        조용히 달라진다 — 예전 식을 그대로 옮겨 놓고 비교한다."""
        import librosa

        from feature_extractor import extract_audio_with_voice

        rng = np.random.default_rng(3)
        y = rng.normal(0, 0.1, 22050 * 2).astype(np.float32)
        vec, _ = extract_audio_with_voice(y, 22050)

        mfcc = librosa.feature.mfcc(y=y.astype(np.float32), sr=22050, n_mfcc=40)
        rms = librosa.feature.rms(y=y)
        zcr = librosa.feature.zero_crossing_rate(y=y)
        f0, _, _ = librosa.pyin(y, fmin=50, fmax=500, frame_length=2048, hop_length=512)
        f0 = np.nan_to_num(f0)
        old = np.concatenate([
            mfcc.mean(axis=1), mfcc.std(axis=1),
            rms.mean(axis=1), rms.std(axis=1),
            zcr.mean(axis=1), zcr.std(axis=1),
            [f0.mean(), f0.std()],
        ])
        assert vec.shape == (86,)
        np.testing.assert_array_equal(vec, old)


class TestVoiceSeconds:
    """'답변 끝' 을 넘기기 전에 사람 목소리가 있는지 잰다 (2026-09-11).

    크기만 보는 감지기는 폰 스피커 소리·잡음도 답변으로 잡았다(세션 57).
    """

    def test_무음은_목소리가_없다(self):
        assert iw.voice_seconds(DEAD * 40) == 0.0

    def test_잡음은_목소리로_보지_않는다(self):
        v = iw.voice_seconds(LOUD * 60)  # 3초 가우스 잡음
        assert v is not None and v < iw.MIN_VOICE_SEC

    def test_못_재면_None(self, monkeypatch):
        """None 이면 막지 않고 넘긴다 — VAD 가 없다고 면접이 멈추면 안 된다."""
        import builtins

        real = builtins.__import__

        def fake(name, *a, **kw):
            if name.startswith("faster_whisper"):
                raise ImportError("없음")
            return real(name, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", fake)
        assert iw.voice_seconds(LOUD * 20) is None


class TestNoiseFloor:
    """2026-09-08 운영 사고 회귀 시험.

    폰으로 돌렸더니 질문 1에서 안 넘어갔다 — 보정이 마이크 예열 무음에 걸려
    임계값이 125 로 앉았고, 그 뒤 생활 소음에 `loud` 가 영영 참이 됐다.
    """

    def test_예열_무음으로는_보정이_끝나지_않는다(self):
        det = _SpeechDetector()
        for _ in range(50):        # 2.5초치 디지털 무음
            det.feed(DEAD)
        assert det.noise is None, "0 만 보고 바닥값을 정하면 안 된다"

    def test_예열_뒤_진짜_소음으로_보정된다(self):
        det = _SpeechDetector()
        for _ in range(20):
            det.feed(DEAD)         # 마이크가 아직 안 켜짐
        for _ in range(12):
            det.feed(QUIET)        # 이제 방 소음이 들어온다
        assert det.noise is not None
        assert det.noise > MIN_NOISE, "바닥값이 방 소음을 따라가야 한다"

    def test_바닥값이_낮게_잡혀도_스스로_빠져나온다(self):
        """실제로 난 사고 그대로 — 낮은 바닥값 + 그보다 큰 생활 소음."""
        det = _SpeechDetector()
        _calibrate(det)
        det._noise = MIN_NOISE                       # 임계값 125 로 앉은 상태
        ambient = _pcm(200)                          # 그보다 큰 생활 소음

        det.feed(ambient)
        assert det.speaking, "지금은 소음을 말로 본다 (사고 재현)"

        # 소음만 계속 들어와도 바닥값이 올라 **침묵 판정이 시작돼야** 한다.
        # 예전 코드는 `_silence_started` 가 영영 서지 않아 180초까지 갇혔다.
        for i in range(400):                         # 20초치
            det.feed(ambient)
            if det._silence_started is not None:
                break
        assert det._silence_started is not None, "생활 소음에 갇히면 안 된다"
        assert i < 200, f"10초 안에 빠져나와야 한다 (걸린 조각 {i})"

        # 빠져나오면 다시 "듣는 중"으로 돌아온다. `end` 가 아니라 None 인 것이 맞다 —
        # 실제로 말한 시간이 MIN_SPEECH_SEC 에 못 미치므로 답변으로 세지 않는다.
        time.sleep(SILENCE_END_SEC + 0.05)
        det.feed(ambient)
        assert not det.speaking, "빠져나온 뒤에는 다시 듣는 상태여야 한다"

    def test_말하는_중에는_바닥값이_치솟지_않는다(self):
        """탈출 장치가 진짜 발화를 끊으면 안 된다 — 낱말 사이 골이 있으면 안 오른다."""
        det = _SpeechDetector()
        _calibrate(det)
        before = det.noise
        for _ in range(20):        # 말-쉼-말-쉼 (실제 발화 모양)
            for _ in range(6):
                det.feed(LOUD)
            det.feed(QUIET)
        assert det.noise < before * 2, f"바닥값이 {before:.0f} → {det.noise:.0f} 로 치솟았다"

class TestTranscribeFallback:
    """전사가 안 되는 상황에서 **면접이 끊기지 않아야 한다.**

    설정이 잘못됐다는 이유로 지원자가 면접을 못 보게 하지 않는다.
    """

    def test_스위치가_비면_자리표시자를_돌려준다(self, monkeypatch):
        monkeypatch.setattr(iw, "STT_MODEL", "")
        out = iw.transcribe(LOUD * 40)
        assert out.startswith("[전사 꺼짐")

    def test_모델을_못_올려도_터지지_않는다(self, monkeypatch):
        monkeypatch.setattr(iw, "STT_MODEL", "없는-모델")
        monkeypatch.setattr(iw, "_stt", None)
        monkeypatch.setattr(iw, "_stt_failed", False)
        out = iw.transcribe(LOUD * 40)
        assert out.startswith("[전사 불가")

    def test_한_번_실패하면_다시_시도하지_않는다(self, monkeypatch):
        tries = []

        def boom(*a, **k):
            tries.append(1)
            raise RuntimeError("못 올림")

        monkeypatch.setattr(iw, "STT_MODEL", "없는-모델")
        monkeypatch.setattr(iw, "_stt", None)
        monkeypatch.setattr(iw, "_stt_failed", False)
        monkeypatch.setitem(
            __import__("sys").modules, "faster_whisper", type("m", (), {"WhisperModel": boom})
        )
        for _ in range(3):
            iw.transcribe(LOUD * 40)
        # 답변마다 수십 초짜리 로딩을 다시 시도하면 면접이 답변마다 멈춘다
        assert len(tries) == 1


class TestChunkSizeIndependence:
    """조각 크기가 달라도 판정이 같아야 한다.

    전에는 창을 **조각 수**로 셌다(40개 = 2초). 그래서 클라이언트가 다른 크기로
    보내면 기준이 통째로 어긋났고, 실제로 앱(#104)이 이 값에 맞추려고 마이크를
    1600바이트로 다시 잘라 보내고 있었다. **맞춰야 하는 쪽은 서버다.**
    """

    @staticmethod
    def _pcm_ms(amplitude: int, ms: int) -> bytes:
        n = int(SAMPLE_RATE * ms / 1000)
        if amplitude == 0:
            return np.zeros(n, dtype=np.int16).tobytes()
        rng = np.random.default_rng(0)
        return (rng.normal(0, amplitude, n)).astype(np.int16).tobytes()

    def _floor_after_calibration(self, ms: int) -> float:
        det = _SpeechDetector()
        quiet = self._pcm_ms(120, ms)
        # 넉넉히 넣어 보정이 끝나게 한다
        for _ in range(int(2000 / ms) + 2):
            det.feed(quiet)
        return det.noise

    def test_조각_크기가_달라도_바닥값이_비슷하다(self):
        floors = {ms: self._floor_after_calibration(ms) for ms in (20, 50, 100, 200)}
        assert all(f is not None for f in floors.values()), floors
        lo, hi = min(floors.values()), max(floors.values())
        # 같은 소리를 다르게 잘라 넣었을 뿐이니 바닥값도 거의 같아야 한다
        assert hi / lo < 1.3, f"조각 크기에 따라 바닥값이 갈린다: {floors}"

    def test_큰_조각으로도_말을_잡는다(self):
        """앱이 200ms 로 보내도 돌아야 한다 — 50ms 에 맞춰 잘라 줄 필요가 없다."""
        det = _SpeechDetector()
        quiet, loud = self._pcm_ms(120, 200), self._pcm_ms(4000, 200)
        for _ in range(12):
            det.feed(quiet)
        assert det.feed(loud) == "begin"
        time.sleep(MIN_SPEECH_SEC + 0.05)
        det.feed(quiet)
        time.sleep(SILENCE_END_SEC + 0.05)
        assert det.feed(quiet) == "end"


class TestIdentity:
    """이력서 사진 ↔ 면접자 동일인 확인 (회의 2026-09-09 3번).

    얼굴 인식 모델을 부르지 않고 상태 기계만 본다 — 모델의 정확도는 LFW 로 따로
    쟀고(`face_match` 주석), 여기서 확인할 것은 **언제 한 번 답하는가**다.
    """

    def _session(self, monkeypatch, scores):
        """지문 대조가 주어진 점수들을 순서대로 낸다고 치고 세션을 만든다."""
        import face_match

        it = iter(scores)
        monkeypatch.setattr(face_match, "embed", lambda img: np.zeros(512))
        monkeypatch.setattr(face_match, "similarity", lambda a, b: next(it))
        s = InterviewSession("tok")
        s.reference = np.zeros(512)
        return s

    def _jpeg(self) -> bytes:
        import cv2

        return cv2.imencode(".jpg", np.zeros((120, 120, 3), np.uint8))[1].tobytes()

    def _feed(self, session, n):
        """FRAME_STRIDE 때문에 실제로 보는 장은 3장에 1장이다."""
        out = []
        for _ in range(n * iw.FRAME_STRIDE):
            out.append(session.add_frame(self._jpeg()))
        return [x for x in out if x is not None]

    def test_다섯_장을_보고_한_번_답한다(self, monkeypatch):
        s = self._session(monkeypatch, [0.6] * 10)
        assert self._feed(s, iw.IDENTITY_FRAMES - 1) == []
        got = self._feed(s, 1)
        assert got == [{"match": "same", "score": 0.6}]

    def test_한_번_정해지면_다시_안_낸다(self, monkeypatch):
        """신원은 면접 중에 바뀌는 값이 아니다 — 매초 흔들리면 못 읽는다."""
        s = self._session(monkeypatch, [0.6] * 30)
        self._feed(s, iw.IDENTITY_FRAMES)
        assert self._feed(s, 5) == []

    def test_가장_잘_맞은_장으로_정한다(self, monkeypatch):
        """눈 감은 장·흔들린 장이 섞여도 멀쩡한 지원자를 의심하지 않는다."""
        s = self._session(monkeypatch, [0.05, 0.02, 0.51, 0.03, 0.04])
        assert self._feed(s, iw.IDENTITY_FRAMES) == [{"match": "same", "score": 0.51}]

    def test_전부_낮으면_다르다고_말한다(self, monkeypatch):
        s = self._session(monkeypatch, [0.05, 0.02, 0.09, 0.03, 0.04])
        assert self._feed(s, iw.IDENTITY_FRAMES) == [{"match": "different", "score": 0.09}]

    def test_애매하면_단정하지_않는다(self, monkeypatch):
        s = self._session(monkeypatch, [0.2] * 5)
        assert self._feed(s, iw.IDENTITY_FRAMES) == [{"match": "unclear", "score": 0.2}]

    def test_이력서_사진이_없으면_통째로_건너뛴다(self, monkeypatch):
        """서식에 사진이 빠졌다고 지원자가 불이익을 받으면 안 된다."""
        s = self._session(monkeypatch, [0.6] * 10)
        s.reference = None
        assert self._feed(s, 10) == []

    def test_얼굴이_안_잡힌_장은_세지_않는다(self, monkeypatch):
        import face_match

        s = self._session(monkeypatch, [0.6] * 10)
        monkeypatch.setattr(face_match, "embed", lambda img: None)
        assert self._feed(s, 10) == []
class TestTranscribeTimeout:
    """전사가 오래 걸려도 **면접이 거기서 멈추면 안 된다** (2026-09-09 실측).

    첫 답변이 모델 로딩(약 26초)을 물면, 답변이 저장되기 전에 uvicorn 이 핑
    응답을 못 받아 WebSocket 을 먼저 닫는다 — `processing` 뒤 40초 무응답 →
    `closed 1011`. 실기기에서 면접이 첫 질문에서 멈춘 원인이었다.
    """

    def test_시간을_넘기면_자리표시자를_남기고_넘어간다(self, monkeypatch):
        def slow(_pcm):
            time.sleep(5)
            return "늦게 온 답"

        monkeypatch.setattr(iw, "transcribe", slow)
        monkeypatch.setattr(iw, "STT_TIMEOUT_SEC", 0.2)

        out = asyncio.run(iw.transcribe_async(LOUD * 40))

        # **빈 문자열이 아니다.** 빈 것은 "말이 안 담겼다" 라 서버가 답변을
        # 저장하지 않고 다시 답하게 하는데, 시간이 모자란 건 지원자 잘못이 아니다
        assert out.startswith("[전사 지연")
        assert out != ""

    def test_제때_끝나면_그_결과를_그대로_준다(self, monkeypatch):
        monkeypatch.setattr(iw, "transcribe", lambda _pcm: "제때 온 답")
        monkeypatch.setattr(iw, "STT_TIMEOUT_SEC", 5)

        assert asyncio.run(iw.transcribe_async(LOUD * 40)) == "제때 온 답"


class TestWarmStt:
    """예열은 **서비스를 죽이지 않는다.** 전사가 없어도 면접은 돈다."""

    def test_스위치가_비면_아무것도_안_한다(self, monkeypatch):
        called = []
        monkeypatch.setattr(iw, "STT_MODEL", "")
        monkeypatch.setattr(iw, "_stt_model", lambda: called.append(1))

        iw.warm_stt()

        assert called == []

    def test_모델을_못_올려도_터지지_않는다(self, monkeypatch):
        monkeypatch.setattr(iw, "STT_MODEL", "없는-모델")

        def boom():
            raise RuntimeError("못 올림")

        monkeypatch.setattr(iw, "_stt_model", boom)

        iw.warm_stt()  # 여기서 예외가 새면 워커가 뜨다가 죽는다
