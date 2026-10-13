"""답변인지는 전사가 정한다 — [답변 완료] 뒤 받아쓴 뒤에 넘기는 동작 (2026-09-15 개정).

09-11 판은 "답했다" 를 먼저 찍고 다음 질문을 보낸 뒤 전사를 뒤에서 돌렸다(CPU whisper
가 45~180초라). 그 순서는 전사가 비면 질문이 소비된 채 빈칸이 남아 앞에서 VAD 로
걸러야 했고, 그 VAD 가 앱 소리를 "목소리 0초" 로 봐서 실제 답변이 튕겼다. 전사가
API 로 옮겨 1~3초가 되면서 다시 기다린다 — 이 파일은 그 순서를 지킨다.
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


async def _speak(ws, session):
    """말하고 [답변 완료] 를 누른 뒤 **끝내기가 돌아올 때까지** 기다린다.

    답변은 이 버튼으로만 끝난다(2026-09-15). 끝내기는 2026-10-13 부터 뒤에서 돌므로
    (`_finish_answer` 주석 — 소켓을 막지 않으려고) 버튼 핸들러는 바로 돌아오고, 결과는
    `wait_finish` 뒤에 본다. 소켓이 빠질 때 `_pump` 가 하는 것과 같다.
    """
    for _ in range(int(iw.MIN_SPEECH_SEC / 0.05) + 2):
        session.add_audio(LOUD)
    await srv._on_text(ws, None, session, '{"type": "end"}')
    await srv.wait_finish(session)


async def _pause(ws, session):
    """말했다가 멈춘다 — 감지기가 '멈춤' 을 낸다. 아무 일도 일어나지 않아야 한다."""
    session.add_audio(LOUD)                      # begin
    await asyncio.sleep(iw.MIN_SPEECH_SEC + 0.05)
    session.add_audio(QUIET)                     # 침묵 시작
    await asyncio.sleep(iw.PAUSE_CHECK_SEC + 0.05)
    await srv._on_binary(ws, None, session, bytes([srv.KIND_AUDIO]) + QUIET)


@pytest.fixture()
def saved(monkeypatch):
    """저장된 답변을 (seq, 전사) 로 모은다."""
    out = []

    async def fake_submit(client, token, transcript, seq=None):
        out.append((seq, transcript))
        return {}

    monkeypatch.setattr(srv, "submit_answer", fake_submit)
    monkeypatch.setattr(srv, "finish_interview", _noop)
    monkeypatch.setattr(srv, "mark_answered", _noop)
    return out


@pytest.fixture(autouse=True)
def _quiet_verdict(monkeypatch):
    """말하는 동안 도는 실시간 판정은 이 파일의 관심사가 아니다."""
    monkeypatch.setattr(srv, "_live_verdict", _noop)


async def _noop(*a, **kw):
    return None


def _returns(value):
    async def _fn():
        return value

    return _fn()


def _stt(text="답변입니다", delay=0.0):
    async def fake(pcm, hint=""):
        if delay:
            await asyncio.sleep(delay)
        return text

    return fake


class TestTranscriptDecides:
    """받아쓴 글이 있으면 저장하고 넘기고, 없으면 같은 질문에 다시 답하게 한다."""

    def test_전사가_비면_넘기지_않고_소리를_되돌린다(self, monkeypatch, saved):
        """세션 57(잡음이 질문 10개를 빈 답변으로 소진)을 이제는 전사 결과로 막는다."""
        async def _t():
            marked = []

            async def fake_mark(client, token, seq):
                marked.append(seq)

            monkeypatch.setattr(srv, "mark_answered", fake_mark)
            monkeypatch.setattr(srv, "transcribe_async", _stt(""))
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert ws.types() == ["processing", "retry"]
            assert marked == [] and saved == []
            assert s.current_seq() == 1
            assert s.audio, "거른 소리는 버퍼로 되돌린다 — 다시 말한 것과 합쳐진다"
        asyncio.run(_t())

    def test_전사가_있으면_저장하고_다음_질문(self, monkeypatch, saved):
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt("답변입니다"))
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert ws.types() == ["processing", "question"]
            assert ws.sent[-1] == {"type": "question", "seq": 2, "text": "둘째 질문"}
            assert saved == [(1, "답변입니다")]
            assert s.current_seq() == 2
        asyncio.run(_t())

    def test_전사를_기다린_뒤에_넘긴다(self, monkeypatch, saved):
        """다음 질문은 저장이 끝난 **뒤에** 나간다 — 그래야 빈 전사에 질문이 소비되지 않는다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt("답변입니다", delay=0.3))
            ws, s = FakeWS(), _session()
            t = time.monotonic()
            await _speak(ws, s)
            assert time.monotonic() - t >= 0.3
            assert ws.types().index("question") > 0
            assert saved == [(1, "답변입니다")]
        asyncio.run(_t())

    def test_답했다_표시가_저장보다_먼저다(self, monkeypatch, saved):
        """재접속이 그 사이 지원자를 이미 답한 질문으로 되돌리지 않게 (2026-09-11 d960f9f)."""
        async def _t():
            order = []

            async def fake_mark(client, token, seq):
                order.append(("mark", seq))

            async def fake_submit(client, token, transcript, seq=None):
                order.append(("submit", seq))
                return {}

            monkeypatch.setattr(srv, "mark_answered", fake_mark)
            monkeypatch.setattr(srv, "submit_answer", fake_submit)
            monkeypatch.setattr(srv, "transcribe_async", _stt())
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert order == [("mark", 1), ("submit", 1)]
        asyncio.run(_t())

    def test_답함_표시가_실패해도_저장하고_넘긴다(self, monkeypatch, saved):
        async def _t():
            async def broken(client, token, seq):
                raise RuntimeError("백엔드가 잠깐 안 받는다")

            monkeypatch.setattr(srv, "mark_answered", broken)
            monkeypatch.setattr(srv, "transcribe_async", _stt())
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert ws.sent[-1]["type"] == "question"
            assert saved == [(1, "답변입니다")]
        asyncio.run(_t())

    def test_저장이_실패하면_넘기지_않는다(self, monkeypatch, saved):
        """넘겨 버리면 그 답은 어디에도 없다 — 소리를 되돌리고 다시 답하게 한다."""
        async def _t():
            async def broken(client, token, transcript, seq=None):
                raise RuntimeError("백엔드 5xx")

            monkeypatch.setattr(srv, "submit_answer", broken)
            monkeypatch.setattr(srv, "transcribe_async", _stt())
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert ws.sent[-1]["type"] == "retry"
            assert s.current_seq() == 1 and s.audio
        asyncio.run(_t())

    def test_저장하는_답변에서_이상입니다를_뗀다(self, monkeypatch, saved):
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt("캐시를 붙였습니다. 이상입니다."))
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert saved == [(1, "캐시를 붙였습니다.")]
        asyncio.run(_t())

    def test_이상입니다만_말하면_빈_답변이다(self, monkeypatch, saved):
        """습관적 마무리만 있으면 답이 없는 것이다 — 다시 답하게 한다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt("이상입니다"))
            ws, s = FakeWS(), _session()
            await _speak(ws, s)
            assert ws.sent[-1]["type"] == "retry" and saved == []
        asyncio.run(_t())

    def test_전사_중에_또_누르면_한_번만_끝낸다(self, monkeypatch, saved):
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt(delay=0.2))
            ws, s = FakeWS(), _session()
            first = asyncio.create_task(_speak(ws, s))
            await asyncio.sleep(0.05)
            await srv._on_text(ws, None, s, '{"type": "end"}')   # 전사 도는 중에 한 번 더
            await first
            assert [m for m in ws.sent if m["type"] == "question"] == [
                {"type": "question", "seq": 2, "text": "둘째 질문"}
            ]
            assert saved == [(1, "답변입니다")]
        asyncio.run(_t())

    def test_질문_목록이_없으면_백엔드가_준_지금_질문을_쓴다(self, monkeypatch, saved):
        """서비스 토큰이 없거나 조회가 실패한 경우. 흐름은 같다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt())
            monkeypatch.setattr(
                srv, "submit_answer",
                lambda c, t, tr, seq=None: _returns({"current_question": "다음", "question_seq": 9}),
            )
            ws, s = FakeWS(), _session(questions=[])
            await _speak(ws, s)
            assert ws.types() == ["processing", "question"]
            assert ws.sent[-1]["text"] == "다음"
        asyncio.run(_t())


class TestEndOfQuestions:
    def test_마지막_질문이면_저장한_뒤_닫는다(self, monkeypatch, saved):
        """먼저 닫으면 마지막 답변이 저장되기 전에 done 이 되어 빈칸이 남는다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt())
            monkeypatch.setattr(srv, "fetch_questions", lambda c, t: _returns([QUESTIONS[1]]))
            monkeypatch.setattr(
                srv, "fetch_state",
                lambda c, t: _returns({"status": "in_progress", "question_seq": None}),
            )
            ws, s = FakeWS(), _session([QUESTIONS[1]])   # 질문 하나뿐
            await _speak(ws, s)
            assert ws.types()[-1] == "done"
            assert saved == [(2, "답변입니다")]
        asyncio.run(_t())

    def test_준비된_질문이_떨어지면_꼬리질문을_받아_이어간다(self, monkeypatch, saved):
        """꼬리질문은 전사가 저장된 뒤에 백엔드가 붙인다 — 시작 때 받은 목록에는 없다."""
        async def _t():
            tail = {"seq": 3, "question": "꼬리 질문"}
            monkeypatch.setattr(srv, "transcribe_async", _stt())
            monkeypatch.setattr(
                srv, "fetch_questions", lambda c, t: _returns([QUESTIONS[1], tail])
            )
            monkeypatch.setattr(
                srv, "fetch_state",
                lambda c, t: _returns({"status": "in_progress", "question_seq": 3}),
            )
            ws, s = FakeWS(), _session([QUESTIONS[1]])
            await _speak(ws, s)
            assert ws.sent[-1] == {"type": "question", "seq": 3, "text": "꼬리 질문"}
            assert "done" not in ws.types()
        asyncio.run(_t())

    def test_번호를_못_찾으면_첫_질문이_아니라_끝으로_간다(self):
        """예전에는 0(첫 질문)으로 가서 이미 답한 1번을 다시 물었다."""
        qs = [{"seq": 1, "question": "a"}, {"seq": 2, "question": "b"}]
        assert srv._cursor_of(qs, 2) == 1
        assert srv._cursor_of(qs, 7) == 2
        assert srv._cursor_of(qs, None) == 2


class TestOnlyButtonEnds:
    """답변 끝은 [답변 완료] 와 상한뿐이다 (2026-09-15). 침묵도, "이상입니다" 도 아니다."""

    def test_조용해진_것만으로는_넘어가지_않는다(self, monkeypatch, saved):
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt())
            ws, s = FakeWS(), _session()
            await _pause(ws, s)
            assert "question" not in ws.types() and "processing" not in ws.types()
            assert saved == [] and s.current_seq() == 1
            assert s.audio, "멈춘 동안의 소리도 버리지 않는다 — 이어서 말하면 한 답이 된다"
        asyncio.run(_t())

    def test_붙자마자_누르면_답변으로_세지_않는다(self, monkeypatch, saved):
        """MIN_SPEECH_SEC 도 안 쌓였으면 전사할 것도 없다 — 바로 retry."""
        async def _t():
            called = []
            monkeypatch.setattr(srv, "transcribe_async", lambda pcm, hint="": called.append(1) or _returns("x"))
            ws, s = FakeWS(), _session()
            await srv._on_text(ws, None, s, '{"type": "end"}')
            assert ws.sent[-1]["type"] == "retry" and called == []
        asyncio.run(_t())

    def test_답변이_상한을_넘으면_끊는다(self, monkeypatch, saved):
        """버튼 없이 이어지면 끝이 없다 — 상한에서 끊고 받아쓴다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt())
            monkeypatch.setattr(iw, "MAX_ANSWER_SEC", 0.2)
            before = iw.ANSWER_STATS["by_limit"]
            ws, s = FakeWS(), _session()
            s.add_audio(LOUD)                        # 첫 말
            await asyncio.sleep(0.25)
            await srv._on_binary(ws, None, s, bytes([srv.KIND_AUDIO]) + LOUD)
            await srv.wait_finish(s)
            assert ws.sent[-1] == {"type": "question", "seq": 2, "text": "둘째 질문"}
            assert iw.ANSWER_STATS["by_limit"] == before + 1
            assert saved == [(1, "답변입니다")]
        asyncio.run(_t())


async def _drain() -> None:
    """뒤에서 도는 확인 task 가 끝날 때까지 기다린다.

    `asyncio.sleep(0.05)` 같은 시간 대기로 두면 **기계가 바쁠 때 무작위로 깨진다** —
    실제로 2026-09-16 에 컨테이너가 다른 일을 같이 할 때 두 번 깨졌다. 남은 task 를
    직접 모아 기다리면 부하와 무관하게 같은 결과가 나온다.
    """
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending)


class TestFinishedSessionStopsScoring:
    """끝난 면접은 더 듣지 않는다 (2026-09-16, 앱 오너 실측).

    지원자 쪽이 소켓을 안 닫으면 — 앱이 「면접 종료」 뒤에도 마이크를 놓지 않거나
    웹 탭을 그냥 열어 두면 — 서버가 끝난 세션을 계속 판정했다. 실측에서 `scored`
    가 10초에 하나씩 올랐고 **그 전부가 `no_face`** 라 통계까지 흐려졌다.

    **소켓만 믿지 않는다** — 지원자 화면의 [면접 종료] 는 백엔드로 바로 가고
    이 소켓은 통지를 못 받는다. 그래서 주기적으로 백엔드에 물어 스스로 멈춘다.
    """

    class _Client:
        def __init__(self, status: str, fail: bool = False):
            self.status = status
            self.fail = fail
            self.calls = 0

        async def get(self, url, timeout=None):
            self.calls += 1
            if self.fail:
                raise RuntimeError("망 끊김")
            status = self.status

            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {"status": status}

            return R()

    def _session(self):
        # 새 세션 그대로 쓴다. 예전에는 `last_done_check = 0.0` 으로 덮었는데, 그러면
        # 기계가 켜진 지 60초가 안 됐을 때 첫 확인이 건너뛰어져 가끔 깨졌다(2026-09-17).
        return srv.InterviewSession("tok-done")

    def test_막_켜진_기계에서도_첫_확인은_바로(self):
        """부팅 후 0초여도 첫 확인은 간격에 걸리지 않는다."""
        s = self._session()
        assert 0.0 - s.last_done_check >= srv.DONE_CHECK_SEC

    def test_끝난_세션이면_멈춘다(self):
        s = self._session()
        asyncio.run(srv._check_done(self._Client("done"), s))
        assert s.done is True

    def test_진행_중이면_계속_듣는다(self):
        s = self._session()
        asyncio.run(srv._check_done(self._Client("in_progress"), s))
        assert s.done is False

    def test_못_물어보면_계속_듣는다(self):
        """망이 흔들린다고 면접을 끊으면 잃는 것이 더 크다."""
        s = self._session()
        asyncio.run(srv._check_done(self._Client("done", fail=True), s))
        assert s.done is False

    def test_자주_묻지_않는다(self, monkeypatch):
        """확인은 1분에 한 번이다 — 소리 조각마다 물으면 그게 부하다."""
        s = self._session()
        client = self._Client("in_progress")

        async def run():
            srv._schedule_done_check(client, s)
            srv._schedule_done_check(client, s)   # 간격 안 — 또 물으면 안 된다
            await _drain()
            assert client.calls == 1

            # 시계를 되감는 대신 마지막 확인 시각을 과거로 민다. `time.monotonic`
            # 자체를 패치하면 **이벤트 루프의 시계까지 멈춰** 테스트가 걸린다.
            s.last_done_check -= srv.DONE_CHECK_SEC + 1
            srv._schedule_done_check(client, s)
            await _drain()
            assert client.calls == 2, "간격이 지났는데 안 물었다"

        asyncio.run(run())

    def test_소리_처리를_막지_않는다(self):
        """확인은 HTTP 한 번이라 최악이면 10초다. 그 자리에서 기다리면 답변이 밀린다.

        **시간을 재지 않는다** — 느린 기계에서 무작위로 깨진다. 대신 「예약 직후에는
        아직 결과가 없다」로 본다: 그 자리에서 기다렸다면 돌아왔을 때 이미 `done`
        이어야 하기 때문이다.
        """
        s = self._session()
        client = self._Client("done")

        async def run():
            srv._schedule_done_check(client, s)
            assert s.done is False, "예약이 아니라 그 자리에서 기다렸다"

            await _drain()
            assert s.done is True, "뒤에서 돌던 확인이 끝나면 멈춰야 한다"

        asyncio.run(run())


class TestTwoSocketsOneSession:
    """한 면접에 소켓 둘 — 앱이 소리, 담당자 방이 얼굴 (2026-09-16, 앱 오너 요청).

    앱은 09-09 개편에서 영상을 WebRTC 로 보내게 바뀌어 얼굴 JPEG 을 한 장도 안
    보낸다. 서버는 WebRTC 미디어 경로에 없어 그 영상을 못 본다. 그런데 **담당자
    방은 이미 그 영상을 받아 그리고 있다** — 거기서 프레임을 떠 보내면 된다.

    소켓마다 세션을 새로 만들면 **각자 반쪽만** 쥐어 판정이 안 난다(소리만 →
    `no_face`, 얼굴만 → `short_audio`). 그래서 토큰 하나에 세션 하나다.
    """

    def setup_method(self):
        srv._SESSIONS.clear()
        srv._SESSION_REFS.clear()

    def test_같은_토큰이면_같은_세션을_쓴다(self):
        a = srv._acquire_session("tok")
        b = srv._acquire_session("tok")

        assert a is b, "소켓마다 세션이 따로면 소리와 얼굴이 안 합쳐진다"
        assert srv._SESSION_REFS["tok"] == 2

    def test_다른_토큰은_섞이지_않는다(self):
        assert srv._acquire_session("tok-a") is not srv._acquire_session("tok-b")

    def test_하나가_빠져도_면접은_계속된다(self):
        """담당자가 방을 닫아도 지원자 면접은 이어져야 한다 — 그 반대도 같다."""
        session = srv._acquire_session("tok")
        srv._acquire_session("tok")

        assert srv._release_session("tok") == 1
        assert srv._SESSIONS["tok"] is session

    def test_마지막_하나가_빠지면_버린다(self):
        srv._acquire_session("tok")
        assert srv._release_session("tok") == 0
        assert "tok" not in srv._SESSIONS

    def test_담당자가_보낸_소리는_버린다(self):
        """앱이 WebRTC 를 `audio: false` 로 열어 담당자가 받는 스트림엔 소리가 없다.

        그 무음을 받아 두면 지원자 목소리에 섞여 전사가 망가진다.
        """
        session = srv._acquire_session("tok")
        before = len(session.audio)

        asyncio.run(
            srv._on_binary(
                None, None, session,
                bytes([srv.KIND_AUDIO]) + b"\x00" * 640,
                is_recruiter=True,
            )
        )

        assert len(session.audio) == before, "담당자의 무음이 답변에 섞였다"

    def _video(self, session, *, recruiter: bool):
        async def run():
            await srv._on_binary(
                None, None, session,
                bytes([srv.KIND_VIDEO]) + b"\xff\xd8fake",
                is_recruiter=recruiter,
            )
            await _drain()

        asyncio.run(run())

    def test_웹_지원자가_얼굴을_보내면_담당자_얼굴은_버린다(self, monkeypatch):
        """같은 얼굴이 두 줄기로 들어오면 recv 가 두 배가 된다 (2026-09-17, 민아님 (가))."""
        session = srv._acquire_session("tok")
        monkeypatch.setattr(
            srv.iw, "face_row_search_full", lambda *_: ([0.0] * 7, 0, None)
        )

        self._video(session, recruiter=False)   # 웹 지원자 페이지
        self._video(session, recruiter=True)    # 담당자 방 — 같은 순간

        assert session.frame_stats["recv"] == 1, "지원자 원본만 세야 한다"
        assert session.frame_stats["dropped_recruiter"] == 1

    def test_지원자_얼굴이_끊기면_담당자_얼굴을_쓴다(self, monkeypatch):
        """지원자 탭이 가려져 전송이 멈추면 담당자 방이 이어받는다."""
        session = srv._acquire_session("tok")
        monkeypatch.setattr(
            srv.iw, "face_row_search_full", lambda *_: ([0.0] * 7, 0, None)
        )

        self._video(session, recruiter=False)
        session.applicant_video_at -= srv.iw.APPLICANT_VIDEO_FRESH_SEC + 1
        self._video(session, recruiter=True)

        assert session.frame_stats["recv"] == 2
        assert session.frame_stats["dropped_recruiter"] == 0

    def test_담당자가_보낸_얼굴은_센다(self, monkeypatch):
        """앱 지원자는 얼굴을 안 보낸다 — 담당자 방이 유일한 출처다."""
        session = srv._acquire_session("tok")
        monkeypatch.setattr(
            srv.iw, "face_row_search_full", lambda *_: ([0.0] * 7, 0, None)
        )

        asyncio.run(
            srv._on_binary(
                None, None, session,
                bytes([srv.KIND_VIDEO]) + b"\xff\xd8fake",
                is_recruiter=True,
            )
        )

        assert session.frame_stats["recv"] == 1


class TestSocketStaysAliveWhileTranscribing:
    """전사하는 동안 소켓을 막지 않는다 (2026-10-13).

    전에는 [답변 완료] 핸들러가 전사를 그 자리에서 기다려 `_pump` 가 `receive()` 를
    못 불렀다. uvicorn(websockets-sansio) 은 앱이 읽지 않는 동안 소켓 읽기를 멈추고,
    그 사이 keepalive pong 도 못 읽어 20초 뒤 `1011 keepalive ping timeout` 으로
    끊는다. 운영(2 vCPU 로컬 전사 30~100초)에서 [답변 완료] 뒤 20~40초에 지원자
    소켓이 죽고 웹은 "정리하는 중" 에 멈췄다 — 10-13 세션 5건 전부.
    """

    class _PumpWS(FakeWS):
        """`_pump` 가 읽을 메시지를 미리 넣어 두는 소켓."""

        def __init__(self, messages):
            super().__init__()
            self.queue: asyncio.Queue = asyncio.Queue()
            for m in messages:
                self.queue.put_nowait(m)

        async def receive(self):
            return await self.queue.get()

    def setup_method(self):
        srv._SESSIONS.clear()
        srv._SESSION_REFS.clear()

    def test_버튼_핸들러는_전사를_기다리지_않고_돌아온다(self, monkeypatch, saved):
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt("답변입니다", delay=0.3))
            ws, s = FakeWS(), _session()
            for _ in range(int(iw.MIN_SPEECH_SEC / 0.05) + 2):
                s.add_audio(LOUD)
            t = time.monotonic()
            await srv._on_text(ws, None, s, '{"type": "end"}')
            assert time.monotonic() - t < 0.3, "핸들러가 전사를 그 자리에서 기다렸다"
            assert s.finishing and s.finish_task is not None
            assert saved == [], "아직 전사 중이다"

            await srv.wait_finish(s)
            assert ws.types() == ["processing", "question"]
            assert saved == [(1, "답변입니다")]
            assert s.finish_task is None and not s.finishing
        asyncio.run(_t())

    def test_전사_중에도_ping에_pong한다(self, monkeypatch, saved):
        """소켓이 살아 있다는 증거 — 핸들러가 읽고 있어야 pong 이 나간다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt(delay=0.3))
            ws, s = FakeWS(), _session()
            for _ in range(int(iw.MIN_SPEECH_SEC / 0.05) + 2):
                s.add_audio(LOUD)
            await srv._on_text(ws, None, s, '{"type": "end"}')
            await srv._on_text(ws, None, s, '{"type": "ping"}')
            assert "pong" in ws.types() and "question" not in ws.types()

            await srv.wait_finish(s)
            assert ws.types()[-1] == "question"
        asyncio.run(_t())

    def test_전사_중에_온_소리는_다음_답변으로_쌓이고_알림은_없다(self, monkeypatch, saved):
        """'listening' 을 보내면 화면이 "정리하는 중" 에서 "듣고 있습니다" 로 튄다."""
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt(delay=0.3))
            ws, s = FakeWS(), _session()
            for _ in range(int(iw.MIN_SPEECH_SEC / 0.05) + 2):
                s.add_audio(LOUD)
            await srv._on_text(ws, None, s, '{"type": "end"}')
            assert s.audio == [], "버튼 시점까지의 소리는 이 답변으로 떼어 갔다"

            for _ in range(5):
                await srv._on_binary(ws, None, s, bytes([srv.KIND_AUDIO]) + LOUD)
            assert "listening" not in ws.types()
            assert len(s.audio) == 5, "전사 중에 온 소리는 다음 답변의 앞부분이다"

            await srv.wait_finish(s)
            assert saved == [(1, "답변입니다")]
            assert len(s.audio) == 5, "끝내기가 다음 답변의 소리를 건드리지 않는다"
        asyncio.run(_t())

    def test_펌프는_전사_중에_끊겨도_답변을_저장한다(self, monkeypatch, saved):
        """지원자가 전사 중에 나가도 답변은 남아야 한다 — `_pump` 가 끝내기를 기다린다.

        `httpx` 클라이언트는 `interview` 핸들러가 돌아가면 닫히므로, 기다리지 않으면
        저장이 "client has been closed" 로 죽는다(10-11 운영 로그).
        """
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt("답변입니다", delay=0.3))
            s = srv._acquire_session("tok-pump")
            s.questions = list(QUESTIONS)
            for _ in range(12):
                s.add_audio(QUIET)
            for _ in range(int(iw.MIN_SPEECH_SEC / 0.05) + 2):
                s.add_audio(LOUD)
            ws = self._PumpWS([
                {"type": "websocket.receive", "text": '{"type": "end"}'},
                {"type": "websocket.receive", "text": '{"type": "ping"}'},
                {"type": "websocket.disconnect", "code": 1001},
            ])

            t = time.monotonic()
            await srv._pump(ws, None, s, "tok-pump", is_recruiter=False)

            assert "pong" in ws.types(), "전사 중에도 읽고 있어야 한다"
            assert time.monotonic() - t >= 0.3, "끊겼다고 끝내기를 버리면 답변이 사라진다"
            assert saved == [(1, "답변입니다")]
            assert "tok-pump" not in srv._SESSIONS, "끝내기를 기다린 뒤에 세션을 놓는다"
        asyncio.run(_t())

    def test_담당자_소켓은_지원자의_끝내기를_기다리지_않는다(self, monkeypatch, saved):
        async def _t():
            monkeypatch.setattr(srv, "transcribe_async", _stt(delay=0.3))
            s = srv._acquire_session("tok-rec")
            srv._acquire_session("tok-rec")          # 담당자 방
            s.questions = list(QUESTIONS)
            for _ in range(12):
                s.add_audio(QUIET)
            for _ in range(int(iw.MIN_SPEECH_SEC / 0.05) + 2):
                s.add_audio(LOUD)
            await srv._on_text(FakeWS(), None, s, '{"type": "end"}')

            t = time.monotonic()
            await srv._pump(
                self._PumpWS([{"type": "websocket.disconnect", "code": 1001}]),
                None, s, "tok-rec", is_recruiter=True,
            )
            assert time.monotonic() - t < 0.3, "담당자 방이 지원자 전사에 묶였다"
            await srv.wait_finish(s)
        asyncio.run(_t())
