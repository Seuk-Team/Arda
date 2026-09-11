"""에이전트 API 엔드포인트 TestClient 테스트.

FastAPI TestClient 로 HTTP 레벨에서 검증한다.
외부 서비스(Claude, Whisper)는 mock, DB 는 트랜잭션 롤백.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import Application, User


@pytest.fixture()
def member(db: Session) -> User:
    user = User(
        email="api-member@fixture.local",
        password_hash="hashed",
        name="API멤버",
        role="member",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def other_member(db: Session) -> User:
    """배정도 없고 admin 도 아닌 또 다른 멤버.

    예전에는 "권한 부족" 표본이었다. 에이전트 엔드포인트는 이제 로그인만 보므로
    (ADR-0017) 같은 일을 할 수 있는지를 검증하는 표본으로 쓴다.
    """
    user = User(
        email="api-other-member@fixture.local",
        password_hash="hashed",
        name="다른멤버",
        role="member",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client(db: Session, member: User) -> TestClient:
    """멤버로 인증된 TestClient."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: member

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


@pytest.fixture()
def other_member_client(db: Session, other_member: User) -> TestClient:
    """다른 멤버로 인증된 TestClient."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: other_member

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


@pytest.fixture()
def unauth_client(db: Session) -> TestClient:
    """인증 없는 TestClient."""
    app.dependency_overrides[get_db] = lambda: db

    yield TestClient(app, raise_server_exceptions=False)

    app.dependency_overrides.clear()


# ── /summarize ──────────────────────────────────────────────


class TestSummarize:
    """POST /api/v1/agent/applications/{id}/summarize"""

    def _available_backend(self):
        """`unavailable_reason() → None` 인 백엔드 목. 대부분의 테스트가 이 상태를 원한다.

        `get_summary_backend()` 를 직접 mock 해서, 테스트 프로세스에 실제
        ANTHROPIC_API_KEY 가 있든 없든 결과가 같게 만든다.
        """
        backend = MagicMock()
        backend.unavailable_reason.return_value = None
        return backend

    def test_success(self, client: TestClient, application: Application):
        with (
            patch("app.application.api.agent.get_summary_backend", return_value=self._available_backend()),
            patch("app.application.api.agent.generate_summary", return_value='{"gist":"요약"}'),
        ):
            resp = client.post(f"/api/v1/agent/applications/{application.id}/summarize")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data

    def test_not_found(self, client: TestClient):
        with patch("app.application.api.agent.generate_summary"):
            resp = client.post("/api/v1/agent/applications/999999/summarize")
        assert resp.status_code == 404

    def test_summary_generation_fails(self, client: TestClient, application: Application):
        """백엔드는 살아 있지만 생성 자체가 실패 → 422 (LLM 응답 파싱 실패 등)."""
        with (
            patch("app.application.api.agent.get_summary_backend", return_value=self._available_backend()),
            patch("app.application.api.agent.generate_summary", return_value=None),
        ):
            resp = client.post(f"/api/v1/agent/applications/{application.id}/summarize")
        assert resp.status_code == 422
        # 문구가 "API 키" 를 언급하지 않아야 한다 — 그건 503 사유다
        assert "API 키" not in resp.json()["message"]

    def test_backend_unavailable(self, client: TestClient, application: Application):
        """키 미설정 등 백엔드 사유 → 503 + 원문 사유."""
        backend = MagicMock()
        backend.unavailable_reason.return_value = "ANTHROPIC_API_KEY 미설정"
        with patch("app.application.api.agent.get_summary_backend", return_value=backend):
            resp = client.post(f"/api/v1/agent/applications/{application.id}/summarize")
        assert resp.status_code == 503
        assert "ANTHROPIC_API_KEY" in resp.json()["message"]

    def test_unauth_rejected(self, unauth_client: TestClient, application: Application):
        resp = unauth_client.post(f"/api/v1/agent/applications/{application.id}/summarize")
        assert resp.status_code == 401


# ── /interview-probes ───────────────────────────────────────


class TestInterviewProbes:
    """POST /api/v1/agent/applications/{id}/interview-probes"""

    def _available_backend(self):
        backend = MagicMock()
        backend.unavailable_reason.return_value = None
        return backend

    _CLAIMS = [
        {
            "claim": "응답이 820ms에서 240ms로 줄었습니다",
            "type": "수치",
            "questions": ["어디가 병목이었어요?", "어떻게 측정했어요?"],
        }
    ]

    def _post(self, client, application, *, claims=_CLAIMS, backend=None):
        with (
            patch(
                "app.application.api.agent.get_summary_backend",
                return_value=backend or self._available_backend(),
            ),
            patch("app.application.api.agent.generate_probes", return_value=claims),
        ):
            return client.post(
                f"/api/v1/agent/applications/{application.id}/interview-probes"
            )

    def test_주장과_질문을_돌려준다(
        self, client: TestClient, db, application: Application
    ):
        application.self_intro = "응답이 820ms에서 240ms로 줄었습니다"
        db.flush()
        resp = self._post(client, application)
        assert resp.status_code == 200
        claims = resp.json()["claims"]
        assert claims[0]["type"] == "수치"
        assert len(claims[0]["questions"]) == 2

    def test_자소서도_이력서도_없으면_422(
        self, client: TestClient, db, application: Application
    ):
        """모델을 부르기 전에 끝난다 — 뽑을 원문이 없으면 토큰을 쓰지 않는다."""
        application.skills = None
        application.career_years = None
        db.flush()
        resp = self._post(client, application)
        assert resp.status_code == 422
        assert "자기소개서" in resp.json()["message"]

    def test_자소서가_없어도_이력서가_있으면_돈다(
        self, client: TestClient, application: Application
    ):
        """폼에 쓴 경력·기술도 지원자가 쓴 글이다 — 자소서만 보던 때와 달라진 점.

        `application` 픽스처에 경력 3년·기술 3개가 들어 있다. 전에는 이걸 두고도
        "뽑을 원문이 없다"며 422 였다.
        """
        resp = self._post(client, application)
        assert resp.status_code == 200

    def test_빈_목록도_200(self, client: TestClient, db, application: Application):
        """감상·다짐만 쓴 자기소개서. 실패가 아니라 '뽑을 게 없음' 이다."""
        application.self_intro = "좋은 개발자가 되고 싶습니다"
        db.flush()
        resp = self._post(client, application, claims=[])
        assert resp.status_code == 200
        assert resp.json()["claims"] == []

    def test_백엔드_불가는_503(self, client: TestClient, db, application: Application):
        """키 미설정이 '생성 실패' 로 둔갑하면 원인이 안 보인다."""
        application.self_intro = "응답이 820ms에서 240ms로 줄었습니다"
        db.flush()
        backend = MagicMock()
        backend.unavailable_reason.return_value = "ANTHROPIC_API_KEY 미설정"
        resp = self._post(client, application, backend=backend)
        assert resp.status_code == 503
        assert "ANTHROPIC_API_KEY" in resp.json()["message"]

    def test_생성_실패는_422(self, client: TestClient, db, application: Application):
        application.self_intro = "응답이 820ms에서 240ms로 줄었습니다"
        db.flush()
        resp = self._post(client, application, claims=None)
        assert resp.status_code == 422

    def test_없는_지원자는_404(self, client: TestClient):
        with patch("app.application.api.agent.generate_probes"):
            resp = client.post("/api/v1/agent/applications/999999/interview-probes")
        assert resp.status_code == 404

    def test_unauth_rejected(self, unauth_client: TestClient, application: Application):
        resp = unauth_client.post(
            f"/api/v1/agent/applications/{application.id}/interview-probes"
        )
        assert resp.status_code == 401


# ── /chat ───────────────────────────────────────────────────


@dataclass
class FakeAgentResult:
    reply: str = "검색 결과입니다."
    tool_calls: list = None
    pending_action: object = None
    input_tokens: int = 100
    output_tokens: int = 50
    # 프롬프트 캐시 사용량. 실제 AgentResult 에 있는데 이 더블에만 없어서
    # /agent/chat 이 result.cache_write_tokens 를 읽다 500 이 났다.
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    # model 은 backend:model 태그다. 비용은 백엔드가 계산해서 실어 보내므로
    # 더블에도 cost_usd 가 있어야 한다 (없으면 /agent/chat 이 500 난다).
    model: str = "anthropic:claude-haiku-4-5-20251001"
    backend: str = "anthropic"
    cost_usd: float = 0.00035
    # 실행된 도구 결과 (동명이인 선택지 재료). 실제 AgentResult 에도 있다.
    tool_results: list = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []
        if self.tool_results is None:
            self.tool_results = []


class TestChat:
    """POST /api/v1/agent/chat"""

    def test_success(self, client: TestClient):
        # 메시지는 intent_router (Phase 1 레버 ②) 가 잡지 않을 자유 질의로 —
        # "김도현 찾아줘" 같은 뻔한 이름 검색은 라우터가 LLM 을 우회하므로 이
        # test 의 run_agent mock 이 안 걸린다. 라우터 자체 검증은
        # tests/test_intent_router.py 참고.
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "김도현에 대해 어떻게 생각해?",
                "history": [],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"] == "검색 결과입니다."
        assert data["input_tokens"] == 100
        assert data["output_tokens"] == 50
        assert "cost_usd" in data

    def test_empty_message_rejected(self, client: TestClient):
        resp = client.post("/api/v1/agent/chat", json={
            "message": "",
            "history": [],
        })
        assert resp.status_code == 422

    def test_message_too_long(self, client: TestClient):
        resp = client.post("/api/v1/agent/chat", json={
            "message": "가" * 2001,
            "history": [],
        })
        assert resp.status_code == 422

    def test_with_pending_action(self, client: TestClient):
        from app.agent.runtime import PendingAction
        result = FakeAgentResult(
            reply="단계를 변경할까요?",
            pending_action=PendingAction(
                tool_name="change_stage",
                arguments={"application_id": 1, "to_stage": "interview_scheduled"},
                description="지원자 #1의 단계를 변경합니다",
            ),
        )
        with patch("app.application.api.agent.run_agent", return_value=result):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "면접 단계로 옮겨줘",
                "history": [],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["pending_action"] is not None
        assert data["pending_action"]["tool_name"] == "change_stage"

    def test_unauth_rejected(self, unauth_client: TestClient):
        resp = unauth_client.post("/api/v1/agent/chat", json={
            "message": "검색해줘",
            "history": [],
        })
        assert resp.status_code == 401

    def test_entity_resolver_applied(self, client: TestClient):
        """resolve_entities 가 메시지에 적용되는지 확인."""
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()) as mock_run:
            client.post("/api/v1/agent/chat", json={
                "message": "파이썬 이년 경력",
                "history": [],
            })
        call_kwargs = mock_run.call_args
        resolved_msg = call_kwargs.kwargs.get("message") or call_kwargs.args[0]
        assert "Python" in resolved_msg or "2년" in resolved_msg


# ── 라우터 직접 실행 핸들러 (전환 규칙 사전 검사) ──────────────


class TestDirectHandlerStageRule:
    """카드를 만들기 전에 validate_transition 을 거친다 (2026-09-02 한도윤 사례)."""

    def test_skip_forward_offers_next_stage_card(self, db, admin_user, application):
        from app.agent.intent_router import DirectAction
        from app.api.agent import _handle_direct
        # fixture 지원자는 applied. interview 로 두 칸 건너뛰기 요청.
        # 이름은 fixture 에서 가져온다 — 리터럴로 적으면 시드 더미와 겹쳐
        # "여러 명이 있어요" 로 빠진다 (conftest 의 `application` 주석 참고).
        intent = DirectAction(
            "change_stage",
            {"_name_lookup": application.name, "to_stage": "interview"},
            is_write=True,
        )
        resp = _handle_direct(intent, db, admin_user)
        assert "먼저" in resp.reply and "서류 검토" in resp.reply
        assert resp.pending_action is not None
        assert resp.pending_action.tool_name == "change_stage"
        assert resp.pending_action.arguments["to_stage"] == "screening"  # 다음 단계 제안
        assert resp.pending_action.arguments["application_id"] == application.id
        assert resp.backend == "router"

    def test_valid_next_step_makes_normal_card(self, db, admin_user, application):
        from app.agent.intent_router import DirectAction
        from app.api.agent import _handle_direct
        intent = DirectAction(
            "change_stage",
            {"_name_lookup": application.name, "to_stage": "screening"},
            is_write=True,
        )
        resp = _handle_direct(intent, db, admin_user)
        assert resp.reply == ""
        assert resp.pending_action.arguments["to_stage"] == "screening"

    def test_same_stage_says_already(self, db, admin_user, application):
        from app.agent.intent_router import DirectAction
        from app.api.agent import _handle_direct
        intent = DirectAction(
            "change_stage",
            {"_name_lookup": application.name, "to_stage": "applied"},
            is_write=True,
        )
        resp = _handle_direct(intent, db, admin_user)
        assert "이미" in resp.reply and resp.pending_action is None


# ── /confirm ────────────────────────────────────────────────


class TestConfirm:
    """POST /api/v1/agent/confirm"""

    def test_success(self, client: TestClient):
        with patch("app.application.api.agent.execute_tool", return_value='{"ok": true}'):
            resp = client.post("/api/v1/agent/confirm", json={
                "tool_name": "change_stage",
                "arguments": {"application_id": 1, "to_stage": "interview_scheduled"},
            })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_invalid_tool_rejected(self, client: TestClient):
        resp = client.post("/api/v1/agent/confirm", json={
            "tool_name": "search_applications",
            "arguments": {},
        })
        assert resp.status_code == 400

    def test_tool_error_returns_422(self, client: TestClient):
        with patch("app.application.api.agent.execute_tool", return_value='{"error": "단계 전환 불가"}'):
            resp = client.post("/api/v1/agent/confirm", json={
                "tool_name": "change_stage",
                "arguments": {"application_id": 1, "to_stage": "applied"},
            })
        assert resp.status_code == 422

    def test_unauth_rejected(self, unauth_client: TestClient):
        resp = unauth_client.post("/api/v1/agent/confirm", json={
            "tool_name": "change_stage",
            "arguments": {},
        })
        assert resp.status_code == 401


# ── /stt ────────────────────────────────────────────────────


@dataclass
class FakeTranscription:
    text: str = "테스트 음성"
    duration: float = 5.0


class TestStt:
    """POST /api/v1/agent/stt"""

    def _fake_transcribe(self, text: str = "테스트 음성", duration: float = 5.0):
        return {
            "raw": text,
            "resolved": text,
            "duration_ms": 120,
            "audio_duration_sec": duration,
            "cost_usd": 0.0005,
        }

    def test_success(self, client: TestClient):
        with patch("app.agent.stt.transcribe", return_value=self._fake_transcribe()):
            resp = client.post(
                "/api/v1/agent/stt",
                files={"file": ("audio.webm", b"fake_audio", "audio/webm")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["raw"] == "테스트 음성"
        assert "cost_usd" in data

    def test_unsupported_media_type(self, client: TestClient):
        resp = client.post(
            "/api/v1/agent/stt",
            files={"file": ("test.txt", b"not audio", "text/plain")},
        )
        assert resp.status_code == 415

    def test_file_too_large(self, client: TestClient):
        big_audio = b"x" * (25 * 1024 * 1024 + 1)
        resp = client.post(
            "/api/v1/agent/stt",
            files={"file": ("big.webm", big_audio, "audio/webm")},
        )
        assert resp.status_code == 413

    def test_whisper_key_missing(self, client: TestClient):
        with patch("app.agent.stt.transcribe", side_effect=RuntimeError("OPENAI_API_KEY")):
            resp = client.post(
                "/api/v1/agent/stt",
                files={"file": ("audio.webm", b"fake", "audio/webm")},
            )
        assert resp.status_code == 503

    def test_unauth_rejected(self, unauth_client: TestClient):
        resp = unauth_client.post(
            "/api/v1/agent/stt",
            files={"file": ("audio.webm", b"fake", "audio/webm")},
        )
        assert resp.status_code == 401

    def test_no_file_rejected(self, client: TestClient):
        resp = client.post("/api/v1/agent/stt")
        assert resp.status_code == 422

    def test_zero_byte_file(self, client: TestClient):
        with patch("app.agent.stt.transcribe", return_value=self._fake_transcribe("", 0.0)):
            resp = client.post(
                "/api/v1/agent/stt",
                files={"file": ("empty.webm", b"", "audio/webm")},
            )
        assert resp.status_code == 200
        assert resp.json()["raw"] == ""

    def test_allowed_audio_types(self, client: TestClient):
        """wav, mpeg, ogg 등 허용 타입이 415 를 내지 않는지."""
        for mime in ("audio/wav", "audio/mpeg", "audio/ogg", "audio/flac"):
            with patch("app.agent.stt.transcribe", return_value=self._fake_transcribe()):
                resp = client.post(
                    "/api/v1/agent/stt",
                    files={"file": ("test", b"fake", mime)},
                )
            assert resp.status_code == 200, f"{mime} should be allowed"


# ── 엣지 케이스: /chat ──────────────────────────────────────


class TestChatEdgeCases:
    """채팅 엔드포인트 경계값·특수 입력."""

    def test_max_length_message(self, client: TestClient):
        """정확히 2000자 메시지는 통과해야 한다."""
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "가" * 2000,
                "history": [],
            })
        assert resp.status_code == 200

    def test_special_characters_in_message(self, client: TestClient):
        """SQL injection 패턴이 에러 없이 처리되는지."""
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "'; DROP TABLE applications; --",
                "history": [],
            })
        assert resp.status_code == 200

    def test_html_script_in_message(self, client: TestClient):
        """XSS 패턴이 에러 없이 처리되는지."""
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "<script>alert('xss')</script>",
                "history": [],
            })
        assert resp.status_code == 200

    def test_with_history(self, client: TestClient):
        """이전 대화 히스토리가 포함된 요청."""
        history = [
            {"role": "user", "content": "김도현 찾아줘"},
            {"role": "assistant", "content": "김도현 2명을 찾았습니다."},
        ]
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "첫 번째 사람 상세 보여줘",
                "history": history,
            })
        assert resp.status_code == 200

    def test_missing_message_field(self, client: TestClient):
        """message 필드 누락."""
        resp = client.post("/api/v1/agent/chat", json={"history": []})
        assert resp.status_code == 422

    def test_invalid_json_body(self, client: TestClient):
        resp = client.post(
            "/api/v1/agent/chat",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_다른_멤버도_채팅할_수_있다(self, other_member_client: TestClient):
        """에이전트 채팅은 로그인만 보면 된다 (ADR-0017)."""
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = other_member_client.post("/api/v1/agent/chat", json={
                "message": "검색해줘",
                "history": [],
            })
        assert resp.status_code == 200

    def test_cost_usd_is_numeric(self, client: TestClient):
        """cost_usd 가 숫자이고 음수가 아닌지."""
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "테스트",
                "history": [],
            })
        cost = resp.json()["cost_usd"]
        assert isinstance(cost, (int, float))
        assert cost >= 0

    def test_tool_calls_in_response(self, client: TestClient):
        """도구 호출 결과가 응답에 포함되는지."""
        result = FakeAgentResult(
            tool_calls=[{"name": "search_applications", "input": {"q": "김"}}],
        )
        with patch("app.application.api.agent.run_agent", return_value=result):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "김씨 찾아줘",
                "history": [],
            })
        assert resp.status_code == 200
        assert len(resp.json()["tool_calls"]) == 1
        assert resp.json()["tool_calls"][0]["name"] == "search_applications"


# ── 엣지 케이스: /confirm ───────────────────────────────────


class TestConfirmEdgeCases:
    """확인 엔드포인트 경계값."""

    def test_all_write_tools_accepted(self, client: TestClient):
        """모든 쓰기 도구가 400 없이 통과하는지."""
        for tool in ("change_stage", "assign_interviewer", "send_email", "create_schedule_proposal"):
            with patch("app.application.api.agent.execute_tool", return_value='{"ok": true}'):
                resp = client.post("/api/v1/agent/confirm", json={
                    "tool_name": tool,
                    "arguments": {},
                })
            assert resp.status_code == 200, f"{tool} should be accepted"

    def test_get_application_rejected(self, client: TestClient):
        resp = client.post("/api/v1/agent/confirm", json={
            "tool_name": "get_application",
            "arguments": {},
        })
        assert resp.status_code == 400

    def test_list_postings_rejected(self, client: TestClient):
        resp = client.post("/api/v1/agent/confirm", json={
            "tool_name": "list_postings",
            "arguments": {},
        })
        assert resp.status_code == 400

    def test_nonexistent_tool_rejected(self, client: TestClient):
        resp = client.post("/api/v1/agent/confirm", json={
            "tool_name": "delete_everything",
            "arguments": {},
        })
        assert resp.status_code == 400

    def test_empty_tool_name(self, client: TestClient):
        resp = client.post("/api/v1/agent/confirm", json={
            "tool_name": "",
            "arguments": {},
        })
        assert resp.status_code == 400

    def test_다른_멤버도_confirm_할_수_있다(self, other_member_client: TestClient):
        """confirm 은 로그인만 필요하다. 도구 안쪽에서 다시 권한을 본다."""
        with patch("app.application.api.agent.execute_tool", return_value='{"ok": true}'):
            resp = other_member_client.post("/api/v1/agent/confirm", json={
                "tool_name": "change_stage",
                "arguments": {"application_id": 1, "to_stage": "interview_scheduled"},
            })
        assert resp.status_code == 200


# ── 엣지 케이스: /summarize ─────────────────────────────────


class TestSummarizeEdgeCases:
    """요약 재생성 경계값."""

    def test_negative_id(self, client: TestClient):
        with patch("app.application.api.agent.generate_summary"):
            resp = client.post("/api/v1/agent/applications/-1/summarize")
        assert resp.status_code == 404

    def test_zero_id(self, client: TestClient):
        with patch("app.application.api.agent.generate_summary"):
            resp = client.post("/api/v1/agent/applications/0/summarize")
        assert resp.status_code == 404

    def test_string_id_rejected(self, client: TestClient):
        resp = client.post("/api/v1/agent/applications/abc/summarize")
        assert resp.status_code == 422

    def test_다른_멤버도_요약을_재생성할_수_있다(
        self, other_member_client: TestClient, application: Application
    ):
        """여기서 보는 것은 **권한**이다 — 백엔드 상태가 결과를 바꾸면 안 된다.

        `get_summary_backend()` 도 같이 mock 한다. 안 하면 키가 없는 환경(CI)에서
        권한 검사까지 가지 못하고 503 으로 떨어진다.
        """
        backend = MagicMock()
        backend.unavailable_reason.return_value = None
        with (
            patch("app.application.api.agent.get_summary_backend", return_value=backend),
            patch("app.application.api.agent.generate_summary", return_value='{"gist":"요약"}'),
        ):
            resp = other_member_client.post(
                f"/api/v1/agent/applications/{application.id}/summarize"
            )
        assert resp.status_code == 200


# ── 동명이인 선택지 (choices) ────────────────────────────────


def _twin(db, application):
    """fixture 지원자와 **같은 이름** 의 두 번째 지원자. 라우터 이름 조회가 2건이 된다."""
    from datetime import UTC, datetime
    from app.models import Application
    twin = Application(
        job_posting_id=application.job_posting_id,
        name=application.name,
        email="test-dohyun-2@fixture.local",
        phone="010-0000-0000",
        education="고려대 전자",
        career_years=7,
        skills=["Java"],
        current_stage="screening",
        privacy_agreed_at=datetime.now(UTC),
        source="form",
    )
    db.add(twin)
    db.flush()
    return twin


class TestChoices:
    """동명이인이면 되묻기만 하지 않고 **선택지 버튼** 재료(choices) 를 준다 (2026-09-08).
    버튼을 누르면 원래 요청 + application_id 가 다시 오고, 서버는 이름 조회를 건너뛴다."""

    def test_router_duplicate_name_returns_choices(self, db, admin_user, application):
        from app.agent.intent_router import DirectAction
        from app.api.agent import _handle_direct
        twin = _twin(db, application)
        intent = DirectAction(
            "change_stage",
            {"_name_lookup": application.name, "to_stage": "screening"},
            is_write=True,
        )
        original = f"{application.name}을 서류심사 단계로 변경해줘"
        resp = _handle_direct(intent, db, admin_user, original=original)
        assert resp.pending_action is None
        assert "골라" in resp.reply
        ids = {c.application_id for c in resp.choices}
        assert ids == {application.id, twin.id}
        for c in resp.choices:
            assert c.message == original
            assert f"(ID {c.application_id})" in c.label
        # 사람이 구분할 상세는 label 이 아니라 개별 필드로 온다 (2026-09-09, 카드 UI 도입).
        # label 은 짧게 "이름 (ID N)" 만 둔다.
        twin_choice = next(c for c in resp.choices if c.application_id == twin.id)
        assert twin_choice.education == "고려대 전자"
        assert twin_choice.stage_label == "서류 검토"
        assert twin_choice.career_years == 7
        assert twin_choice.email == twin.email
        # change_stage 규칙 라우터는 각 후보에 pending 을 첨부한다 (담당자 카드 딸깍 =
        # 원샷 실행). 원본 application (applied → screening) 은 정상 전환 → pending 붙음.
        # twin 은 이미 screening 이라 to_stage=screening 은 규칙 실패 → pending 없음 (폴백).
        app_choice = next(c for c in resp.choices if c.application_id == application.id)
        assert app_choice.pending_action is not None
        assert app_choice.pending_action.tool_name == "change_stage"
        assert app_choice.pending_action.arguments["application_id"] == application.id
        assert app_choice.pending_action.arguments["to_stage"] == "screening"
        assert twin_choice.pending_action is None

    def test_router_selected_id_skips_lookup(self, db, admin_user, application):
        from app.agent.intent_router import DirectAction
        from app.api.agent import _handle_direct
        twin = _twin(db, application)
        intent = DirectAction(
            "change_stage",
            {"_name_lookup": application.name, "to_stage": "screening"},
            is_write=True,
        )
        # twin 은 screening 이라 다음 칸인 interview 로 — 같은 단계면 "이미" 안내로 빠진다
        intent.args["to_stage"] = "interview"
        resp = _handle_direct(intent, db, admin_user, application_id=twin.id)
        # 동명이인이 있어도 되묻지 않고 고른 사람으로 카드가 만들어진다
        assert resp.choices == []
        assert resp.pending_action is not None
        assert resp.pending_action.arguments["application_id"] == twin.id

    def test_router_selected_unknown_id(self, db, admin_user, application):
        from app.agent.intent_router import DirectAction
        from app.api.agent import _handle_direct
        intent = DirectAction(
            "change_stage",
            {"_name_lookup": application.name, "to_stage": "screening"},
            is_write=True,
        )
        resp = _handle_direct(intent, db, admin_user, application_id=999_999)
        assert resp.pending_action is None and "찾지 못했" in resp.reply

    def test_llm_path_builds_choices_from_tool_results(self, client: TestClient):
        rows = [
            {"id": 11, "name": "백지안", "current_stage": "interview", "career_years": 5,
             "email": "jian.baek@example.com"},
            {"id": 28, "name": "백지안", "current_stage": "applied", "career_years": 5,
             "email": "jian.baek@example.com"},
            {"id": 3, "name": "서지호", "current_stage": "applied", "career_years": 2},
        ]
        fake = FakeAgentResult(
            reply="⚠️ 동명이인이 있습니다. 어떤 백지안 님의 이력서를 보시겠어요?",
            tool_results=[{"name": "search_applications", "input": {"q": "백지안"},
                           "output": {"results": rows, "count": 3}}],
        )
        with patch("app.application.api.agent.run_agent", return_value=fake):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "백지안 이력서 좀 보여줄래?",
                "history": [],
            })
        assert resp.status_code == 200
        choices = resp.json()["choices"]
        # 같은 이름이 둘인 백지안만 — 서지호는 선택지가 아니다
        assert [c["application_id"] for c in choices] == [11, 28]
        assert all(c["message"] == "백지안 이력서 좀 보여줄래?" for c in choices)
        # 상세는 label 이 아니라 개별 필드로 (카드 UI 로 나눔, 2026-09-09).
        assert choices[0]["stage_label"] == "면접" and choices[1]["stage_label"] == "지원 접수"
        # LLM 경로는 pending_action 을 아직 안 붙인다 (LLM 답변에서 목표 도구·arguments 를
        # 안전하게 뽑기 어렵다). 카드 클릭은 두 단계 폴백 흐름.
        assert all(c["pending_action"] is None for c in choices)

    def test_llm_path_no_choices_without_duplicate_notice(self, client: TestClient):
        rows = [{"id": 11, "name": "백지안"}, {"id": 28, "name": "백지안"}]
        fake = FakeAgentResult(
            reply="백지안 님 이력서입니다.",
            tool_results=[{"name": "search_applications", "input": {},
                           "output": {"results": rows, "count": 2}}],
        )
        with patch("app.application.api.agent.run_agent", return_value=fake):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "백지안 이력서 좀 보여줄래?", "history": [],
            })
        assert resp.json()["choices"] == []

    def test_llm_path_selected_id_is_passed_to_model(self, client: TestClient):
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()) as mock_run:
            resp = client.post("/api/v1/agent/chat", json={
                "message": "백지안 이력서 좀 보여줄래?", "history": [], "application_id": 28,
            })
        assert resp.status_code == 200
        sent = mock_run.call_args.kwargs["message"]
        assert sent.startswith("백지안 이력서 좀 보여줄래?") and "ID: 28" in sent

    def test_response_has_empty_choices_by_default(self, client: TestClient):
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "김도현에 대해 어떻게 생각해?", "history": [],
            })
        assert resp.json()["choices"] == []
