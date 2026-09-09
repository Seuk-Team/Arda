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


async def _noop(*a, **kw):
    return None


def _slow_stt(delay, text="답변입니다"):
    async def fake(pcm):
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


def _returns(value):
    async def _fn():
        return value

    return _fn()
