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

    def test_success(self, client: TestClient, application: Application):
        with patch("app.api.agent.generate_summary", return_value='{"gist":"요약"}'):
            resp = client.post(f"/api/v1/agent/applications/{application.id}/summarize")
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data

    def test_not_found(self, client: TestClient):
        with patch("app.api.agent.generate_summary"):
            resp = client.post("/api/v1/agent/applications/999999/summarize")
        assert resp.status_code == 404

    def test_summary_generation_fails(self, client: TestClient, application: Application):
        with patch("app.api.agent.generate_summary", return_value=None):
            resp = client.post(f"/api/v1/agent/applications/{application.id}/summarize")
        assert resp.status_code == 422

    def test_unauth_rejected(self, unauth_client: TestClient, application: Application):
        resp = unauth_client.post(f"/api/v1/agent/applications/{application.id}/summarize")
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

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []


class TestChat:
    """POST /api/v1/agent/chat"""

    def test_success(self, client: TestClient):
        with patch("app.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "김도현 찾아줘",
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
        with patch("app.api.agent.run_agent", return_value=result):
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
        with patch("app.api.agent.run_agent", return_value=FakeAgentResult()) as mock_run:
            client.post("/api/v1/agent/chat", json={
                "message": "파이썬 이년 경력",
                "history": [],
            })
        call_kwargs = mock_run.call_args
        resolved_msg = call_kwargs.kwargs.get("message") or call_kwargs.args[0]
        assert "Python" in resolved_msg or "2년" in resolved_msg


# ── /confirm ────────────────────────────────────────────────


class TestConfirm:
    """POST /api/v1/agent/confirm"""

    def test_success(self, client: TestClient):
        with patch("app.api.agent.execute_tool", return_value='{"ok": true}'):
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
        with patch("app.api.agent.execute_tool", return_value='{"error": "단계 전환 불가"}'):
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
        with patch("app.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "가" * 2000,
                "history": [],
            })
        assert resp.status_code == 200

    def test_special_characters_in_message(self, client: TestClient):
        """SQL injection 패턴이 에러 없이 처리되는지."""
        with patch("app.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "'; DROP TABLE applications; --",
                "history": [],
            })
        assert resp.status_code == 200

    def test_html_script_in_message(self, client: TestClient):
        """XSS 패턴이 에러 없이 처리되는지."""
        with patch("app.api.agent.run_agent", return_value=FakeAgentResult()):
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
        with patch("app.api.agent.run_agent", return_value=FakeAgentResult()):
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
        with patch("app.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = other_member_client.post("/api/v1/agent/chat", json={
                "message": "검색해줘",
                "history": [],
            })
        assert resp.status_code == 200

    def test_cost_usd_is_numeric(self, client: TestClient):
        """cost_usd 가 숫자이고 음수가 아닌지."""
        with patch("app.api.agent.run_agent", return_value=FakeAgentResult()):
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
        with patch("app.api.agent.run_agent", return_value=result):
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
        for tool in ("change_stage", "assign_interviewer", "send_email"):
            with patch("app.api.agent.execute_tool", return_value='{"ok": true}'):
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
        with patch("app.api.agent.execute_tool", return_value='{"ok": true}'):
            resp = other_member_client.post("/api/v1/agent/confirm", json={
                "tool_name": "change_stage",
                "arguments": {"application_id": 1, "to_stage": "interview_scheduled"},
            })
        assert resp.status_code == 200


# ── 엣지 케이스: /summarize ─────────────────────────────────


class TestSummarizeEdgeCases:
    """요약 재생성 경계값."""

    def test_negative_id(self, client: TestClient):
        with patch("app.api.agent.generate_summary"):
            resp = client.post("/api/v1/agent/applications/-1/summarize")
        assert resp.status_code == 404

    def test_zero_id(self, client: TestClient):
        with patch("app.api.agent.generate_summary"):
            resp = client.post("/api/v1/agent/applications/0/summarize")
        assert resp.status_code == 404

    def test_string_id_rejected(self, client: TestClient):
        resp = client.post("/api/v1/agent/applications/abc/summarize")
        assert resp.status_code == 422

    def test_다른_멤버도_요약을_재생성할_수_있다(
        self, other_member_client: TestClient, application: Application
    ):
        with patch("app.api.agent.generate_summary", return_value='{"gist":"요약"}'):
            resp = other_member_client.post(
                f"/api/v1/agent/applications/{application.id}/summarize"
            )
        assert resp.status_code == 200
