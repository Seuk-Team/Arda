"""agent_traces — 아르 대화 로그가 남고, 라벨 필드가 초기엔 비어 있는지.

**왜 이 테스트가 필요한가.** 학습 데이터는 이 표 없이는 못 모은다. 대화 한 번마다
한 행이 남아야 하고, 라벨은 사후에 채워져야 한다. 이 계약이 깨지면 QLoRA 학습셋
자체가 안 만들어진다.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import pytest

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import AgentTrace, User


@pytest.fixture()
def member(db: Session) -> User:
    from datetime import UTC, datetime
    from uuid import uuid4
    u = User(
        email=f"trace-{uuid4().hex[:6]}@arda.local",
        password_hash="x", name="Trace Tester", role="member",
    )
    db.add(u); db.flush()
    return u


@pytest.fixture()
def client(db: Session, member: User) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: member
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@dataclass
class FakeAgentResult:
    reply: str = "김도현 님 상세 정보입니다."
    tool_calls: list = None
    tool_results: list = None
    pending_action: object = None
    input_tokens: int = 100
    output_tokens: int = 50
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    model: str = "anthropic:claude-haiku-4-5-20251001"
    backend: str = "anthropic"
    cost_usd: float = 0.00035

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []
        if self.tool_results is None:
            self.tool_results = []


class TestAgentTracePersists:
    def test_llm_path_writes_one_row(self, client: TestClient, db):
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            resp = client.post("/api/v1/agent/chat", json={
                "message": "김도현에 대해 어떻게 생각해?",  # 라우터가 안 잡는 자유 질의
                "history": [],
                "session_id": "s-001",
            })
        assert resp.status_code == 200

        rows = db.execute(select(AgentTrace).order_by(AgentTrace.id.desc())).scalars().all()
        assert len(rows) >= 1
        row = rows[0]
        assert row.session_id == "s-001"
        assert row.user_message == "김도현에 대해 어떻게 생각해?"
        assert row.assistant_reply == "김도현 님 상세 정보입니다."
        assert row.backend == "anthropic"
        assert row.model_tag.startswith("anthropic:")
        # 라벨은 초기엔 전부 비어 있어야 함 — 나중에 사람이 채운다
        assert row.label_verdict is None
        assert row.label_correction is None
        assert row.label_by is None
        assert row.label_at is None

    def test_multi_turn_stores_history(self, client: TestClient, db):
        history = [
            {"role": "user", "content": "김도현 상세"},
            {"role": "assistant", "content": "..."},
        ]
        with patch("app.application.api.agent.run_agent", return_value=FakeAgentResult()):
            client.post("/api/v1/agent/chat", json={
                "message": "그럼 다음 단계는?",
                "history": history,
                "session_id": "s-002",
            })
        row = db.execute(
            select(AgentTrace).where(AgentTrace.session_id == "s-002")
        ).scalar_one()
        assert row.history == history
        assert row.turn_index == 1  # user·assistant 짝이므로 2 // 2 = 1

    def test_tool_calls_and_results_merged(self, client: TestClient, db):
        result = FakeAgentResult(
            tool_calls=[{"name": "search_applications", "input": {"q": "김"}}],
            tool_results=[{"name": "search_applications", "input": {"q": "김"},
                           "output": {"count": 3}}],
        )
        with patch("app.application.api.agent.run_agent", return_value=result):
            client.post("/api/v1/agent/chat", json={
                "message": "김씨 다 보여줘",
                "history": [],
            })
        row = db.execute(select(AgentTrace).order_by(AgentTrace.id.desc())).scalar()
        assert row.tool_calls[0]["name"] == "search_applications"
        assert row.tool_calls[0]["output"] == {"count": 3}

    def test_router_path_does_not_write_trace(self, client: TestClient, db):
        # 이름 검색은 규칙 라우터가 잡는다 → LLM 안 부르고 반환 → trace 안 남긴다.
        before = db.execute(select(AgentTrace)).scalars().all()
        resp = client.post("/api/v1/agent/chat", json={
            "message": "김도현 찾아줘",
            "history": [],
        })
        assert resp.status_code == 200
        after = db.execute(select(AgentTrace)).scalars().all()
        assert len(after) == len(before)


class TestLabelConstraints:
    def test_verdict_check_constraint(self, db):
        from app.models import AgentTrace
        import pytest
        from sqlalchemy.exc import IntegrityError

        db.add(AgentTrace(
            user_message="x", assistant_reply="y",
            label_verdict="invalid_value",
        ))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

    def test_label_verdict_accepts_good_bad_needs_fix(self, db):
        for v in ("good", "bad", "needs_fix"):
            db.add(AgentTrace(user_message=f"q-{v}", assistant_reply="a", label_verdict=v))
            db.flush()  # 각 값이 CHECK 를 통과하는지


class TestEvalCasesFile:
    """eval_cases.yaml 이 ADR-0023 형식과 맞는지, 20 케이스가 모두 유효한지."""

    def test_cases_load_and_are_20(self):
        import yaml
        from pathlib import Path
        p = Path(__file__).resolve().parents[2] / "docs" / "07_eval" / "eval_cases.yaml"
        assert p.exists(), f"{p} 가 없다"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert len(data["cases"]) == 20
        ids = [c["id"] for c in data["cases"]]
        assert len(ids) == len(set(ids)), "케이스 id 중복"
        for c in data["cases"]:
            assert "input" in c and c["input"]
            assert "expect" in c
            assert "category" in c
