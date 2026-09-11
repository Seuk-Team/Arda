"""전사를 기다리지 않는다 — 면접 진행과 전사를 떼어낸 뒤의 동작.

이게 틀리면 사람이 몰릴 때 지원자 화면이 "처리 중" 에서 멈춘다. 그러면
**동시에 몇 명이 오는지 미리 맞춰야** 서비스가 사는데, 쓰는 회사가 늘면
그걸 맞출 수가 없다.
"""

from __future__ import annotations

import asyncio
import time

import pytest

import app as srv
import interview_ws as iw
from test_interview_ws import LOUD, QUIET

QUESTIONS = [
    {"seq": 1, "question": "첫 질문"},
    {"seq": 2, "question": "둘째 질문"},
]


class FakeWS:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_json(self, payload):
        self.sent.append(payload)

    def types(self):
        return [m["type"] for m in self.sent]


def _session(questions=QUESTIONS) -> iw.InterviewSession:
    s = iw.InterviewSession("tok-flow")
    s.questions = list(questions)
    for _ in range(12):
        s.add_audio(QUIET)      # 바닥값 보정
    return s


async def _speak(ws, session, seconds=0.05):
    """말했다가 멈춘다 — `_on_binary` 가 'end' 를 보게 만든다."""
    session.add_audio(LOUD)                      # begin
    await asyncio.sleep(iw.MIN_SPEECH_SEC + 0.05)
    session.add_audio(QUIET)                     # 침묵 시작
    await asyncio.sleep(iw.SILENCE_END_SEC + 0.05)
    return await srv._on_binary(ws, None, session, bytes([srv.KIND_AUDIO]) + QUIET)


@pytest.fixture()
def saved(monkeypatch):
    """저장된 답변을 (seq, 전사) 로 모은다."""
    out = []

    async def fake_submit(client, token, transcript, seq=None):
        out.append((seq, transcript))
        return {}

    monkeypatch.setattr(srv, "submit_answer", fake_submit)
    monkeypatch.setattr(srv, "finish_interview", _noop)
    return out


@pytest.fixture(autouse=True)
def _voiced(monkeypatch):
    """이 파일의 소리(`LOUD`)는 가우스 잡음이라 VAD 가 목소리로 보지 않는다. 진행
    흐름을 보는 시험들이라 목소리가 있다고 둔다 — 거르는 동작은 `TestVoiceGate` 가 본다."""
    monkeypatch.setattr(srv, "voice_seconds", lambda pcm: 5.0)


async def _noop(*a, **kw):
    return None


class TestVoiceGate:
    """목소리가 없는 소리로 질문이 넘어가지 않는다 (2026-09-11).

    세션 57: 폰 스피커 소리·잡음이 '답변 끝' 으로 잡힐 때마다 질문이 "답함" 으로
    찍혀, 58초 만에 질문 10개가 전사 0자로 소진되고 면접이 닫혔다.
    """

    def test_목소리가_없으면_질문을_넘기지_않는다(self, monkeypatch, saved):
        async def _t():
            marked = []

            async def fake_mark(client, token, seq):
                marked.append(seq)

            monkeypatch.setattr(srv, "mark_answered", fake_mark)
            monkeypatch.setattr(srv, "voice_seconds", lambda pcm: 0.0)
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert ws.sent[-1]["type"] == "retry"
            assert marked == [], "목소리 없는 소리로 '답함' 을 찍으면 그 질문은 돌아올 길이 없다"
            assert s.current_seq() == 1
            assert s.pending.qsize() == 0
        asyncio.run(_t())

    def test_목소리가_있으면_넘긴다(self, monkeypatch, saved):
        async def _t():
            monkeypatch.setattr(srv, "mark_answered", _noop)
            monkeypatch.setattr(srv, "voice_seconds", lambda pcm: 2.0)
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert ws.sent[-1] == {"type": "question", "seq": 2, "text": "둘째 질문"}
        asyncio.run(_t())

    def test_목소리를_못_재면_막지_않는다(self, monkeypatch, saved):
        """VAD 가 고장 났다고 면접이 멈추면 안 된다 — 예전처럼 넘긴다."""
        async def _t():
            monkeypatch.setattr(srv, "mark_answered", _noop)
            monkeypatch.setattr(srv, "voice_seconds", lambda pcm: None)
            before = iw.ANSWER_STATS["unmeasured"]
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert ws.sent[-1]["seq"] == 2
            assert iw.ANSWER_STATS["unmeasured"] == before + 1
        asyncio.run(_t())


def _slow_stt(delay, text="답변입니다"):
    async def fake(pcm, hint=""):
        await asyncio.sleep(delay)
        return text

    return fake


class TestNoWaiting:
    def test_전사가_느려도_다음_질문이_바로_간다(self, monkeypatch, saved):
        """이 테스트가 이 변경의 전부다. 전에는 전사가 끝나야 질문이 나갔다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(2.0))
            ws, s = FakeWS(), _session()
            pump = asyncio.create_task(srv._transcribe_pump(None, s))

            t = time.monotonic()
            await _speak(ws, s)
            elapsed = time.monotonic() - t

            assert ws.sent[-1] == {"type": "question", "seq": 2, "text": "둘째 질문"}
            # 전사 2초를 기다렸다면 여기서 걸린다
            assert elapsed < iw.SILENCE_END_SEC + 1.0
            assert saved == []          # 아직 저장 전
            await s.pending.join()
            assert saved == [(1, "답변입니다")]
            pump.cancel()
        asyncio.run(_t())

    def test_저장할_때_질문_번호를_붙인다(self, monkeypatch, saved):
        """번호가 없으면 백엔드가 '가장 앞 빈칸' 에 넣어 한 칸씩 밀린다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(0.01))
            ws, s = FakeWS(), _session()
            pump = asyncio.create_task(srv._transcribe_pump(None, s))
            await _speak(ws, s)
            await s.pending.join()
            assert saved[0][0] == 1
            pump.cancel()
        asyncio.run(_t())

    def test_마지막_질문이면_전사를_끝내고_닫는다(self, monkeypatch, saved):
        """먼저 닫으면 마지막 답변이 저장되기 전에 done 이 되어 빈칸이 남는다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(0.3))
            ws, s = FakeWS(), _session([QUESTIONS[1]])   # 질문 하나뿐
            pump = asyncio.create_task(srv._transcribe_pump(None, s))
            await _speak(ws, s)
            assert ws.types()[-1] == "done"
            assert saved == [(2, "답변입니다")]          # done 전에 이미 저장됐다
            pump.cancel()
        asyncio.run(_t())

    def test_전사가_비면_그_칸은_빈칸으로_남는다(self, monkeypatch, saved):
        """다음 질문이 이미 나가서 '다시 답변해 주세요' 를 못 한다 — 기다리지
        않는 대가이고, 담당자가 빈칸을 보고 판단한다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(0.01, text=""))
            ws, s = FakeWS(), _session()
            pump = asyncio.create_task(srv._transcribe_pump(None, s))
            await _speak(ws, s)
            await s.pending.join()
            assert saved == []
            assert "retry" not in ws.types()
            pump.cancel()
        asyncio.run(_t())

    def test_질문_목록이_없으면_예전처럼_기다린다(self, monkeypatch, saved):
        """서비스 토큰이 없거나 조회가 실패한 경우. 느리지만 동작은 같다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(0.05))
            monkeypatch.setattr(
                srv, "submit_answer",
                lambda c, t, tr, seq=None: _returns({"current_question": "다음", "question_seq": 9}),
            )
            ws, s = FakeWS(), _session(questions=[])
            await _speak(ws, s)
            assert ws.types() == ["processing", "question"]
            assert ws.sent[-1]["text"] == "다음"
        asyncio.run(_t())

    def test_답변_완료_버튼도_기다리지_않는다(self, monkeypatch, saved):
        """[답변 완료](`{"type":"end"}`, #140)와 침묵 감지가 같은 길을 탄다 —
        끝을 누가 정했든 그 뒤는 같아야 한다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(2.0))
            ws, s = FakeWS(), _session()
            pump = asyncio.create_task(srv._transcribe_pump(None, s))

            for _ in range(int(iw.MIN_SPEECH_SEC / 0.05) + 2):
                s.add_audio(LOUD)
            assert s.force_end() is True

            t = time.monotonic()
            await srv._finish_answer(ws, None, s)
            assert time.monotonic() - t < 1.0
            assert ws.sent[-1] == {"type": "question", "seq": 2, "text": "둘째 질문"}

            await s.pending.join()
            assert saved == [(1, "답변입니다")]
            pump.cancel()
        asyncio.run(_t())


def _returns(value):
    async def _fn():
        return value

    return _fn()


class TestAnsweredFirst:
    """말이 끝나는 순간 '답했다' 부터 남긴다 (2026-09-11).

    전사를 기다려 '답했다' 를 정하던 때는 그 사이 재접속이 지원자를 이미 답한
    질문으로 되돌렸다(시연: Q9 → Q1, 다시 한 답은 409 로 버려짐).
    """

    def test_다음_질문을_보내기_전에_답했다고_남긴다(self, monkeypatch, saved):
        async def _t():
            order = []

            async def fake_mark(client, token, seq):
                order.append(("mark", seq))

            monkeypatch.setattr(srv, "mark_answered", fake_mark)
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(2.0))
            ws, s = FakeWS(), _session()
            real_send = ws.send_json

            async def spy(payload):
                order.append(("send", payload.get("type")))
                await real_send(payload)

            ws.send_json = spy
            pump = asyncio.create_task(srv._transcribe_pump(None, s))
            await _speak(ws, s)
            assert ("mark", 1) in order
            assert order.index(("mark", 1)) < order.index(("send", "question"))
            assert saved == []          # 전사는 아직 — 그래도 답한 것은 이미 남았다
            await s.pending.join()
            pump.cancel()
        asyncio.run(_t())

    def test_답함_표시가_실패해도_면접은_간다(self, monkeypatch, saved):
        async def _t():
            async def broken(client, token, seq):
                raise RuntimeError("백엔드가 잠깐 안 받는다")

            monkeypatch.setattr(srv, "mark_answered", broken)
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(0.01))
            ws, s = FakeWS(), _session()
            pump = asyncio.create_task(srv._transcribe_pump(None, s))
            await _speak(ws, s)
            assert ws.sent[-1] == {"type": "question", "seq": 2, "text": "둘째 질문"}
            await s.pending.join()
            assert saved == [(1, "답변입니다")]
            pump.cancel()
        asyncio.run(_t())

    def test_번호를_못_찾으면_첫_질문이_아니라_끝으로_간다(self):
        """예전에는 0(첫 질문)으로 가서 이미 답한 1번을 다시 물었다."""
        qs = [{"seq": 1, "question": "a"}, {"seq": 2, "question": "b"}]
        assert srv._cursor_of(qs, 2) == 1
        assert srv._cursor_of(qs, 7) == 2
        assert srv._cursor_of(qs, None) == 2

    def test_준비된_질문이_떨어지면_꼬리질문을_받아_이어간다(self, monkeypatch, saved):
        """꼬리질문은 전사가 저장된 뒤에 백엔드가 붙인다 — 시작 때 받은 목록에는 없다."""
        async def _t():
            tail = {"seq": 3, "question": "꼬리 질문"}
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(0.01))
            monkeypatch.setattr(
                srv, "fetch_questions", lambda c, t: _returns([QUESTIONS[1], tail])
            )
            monkeypatch.setattr(
                srv, "fetch_state",
                lambda c, t: _returns({"status": "in_progress", "question_seq": 3}),
            )
            ws, s = FakeWS(), _session([QUESTIONS[1]])   # 준비된 질문 하나뿐
            pump = asyncio.create_task(srv._transcribe_pump(None, s))
            await _speak(ws, s)
            assert ws.sent[-1] == {"type": "question", "seq": 3, "text": "꼬리 질문"}
            assert "done" not in ws.types()
            pump.cancel()
        asyncio.run(_t())

    def test_남은_질문이_없으면_닫는다(self, monkeypatch, saved):
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _slow_stt(0.01))
            monkeypatch.setattr(srv, "fetch_questions", lambda c, t: _returns([QUESTIONS[1]]))
            monkeypatch.setattr(
                srv, "fetch_state",
                lambda c, t: _returns({"status": "in_progress", "question_seq": None}),
            )
            ws, s = FakeWS(), _session([QUESTIONS[1]])
            pump = asyncio.create_task(srv._transcribe_pump(None, s))
            await _speak(ws, s)
            assert ws.types()[-1] == "done"
            pump.cancel()
        asyncio.run(_t())
