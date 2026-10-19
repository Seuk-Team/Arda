"""공고별 서류 채점 기준 — 필수 요건·우대 사항 (2026-10-19).

`job_postings.requirements`·`preferred` 컬럼은 0013 부터 있었지만 공고 API 가 받지 않아
웹에서 만든 공고는 두 칸이 늘 비어 있었다. 그러면 채점 프롬프트에 우대가 "정보 없음" 으로
들어가 우대 점수가 근거 없이 매겨진다. API 로 넣고 고친 값이 채점 재료까지 가는지 본다.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import JobPosting, User


@pytest.fixture()
def client(db: Session, admin_user: User):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


REQ = "- Python 실서비스 API 3년 이상\n- Docker 배포 경험"
PREF = "- pgvector 벡터 검색"


class TestPostingCriteria:
    def test_등록할_때_요건과_우대를_받는다(self, client: TestClient, db: Session):
        res = client.post(
            "/api/v1/postings",
            json={"title": "백엔드 개발자", "requirements": REQ, "preferred": PREF},
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["requirements"] == REQ
        assert body["preferred"] == PREF
        row = db.get(JobPosting, body["id"])
        assert (row.requirements, row.preferred) == (REQ, PREF)

    def test_비워_두면_null_이다(self, client: TestClient):
        body = client.post("/api/v1/postings", json={"title": "백엔드 개발자"}).json()
        assert body["requirements"] is None
        assert body["preferred"] is None

    def test_등록한_뒤에도_고칠_수_있다(self, client: TestClient, posting: JobPosting):
        res = client.patch(f"/api/v1/postings/{posting.id}", json={"preferred": PREF})
        assert res.status_code == 200, res.text
        assert res.json()["preferred"] == PREF
        # 보낸 칸만 바뀐다 (exclude_unset)
        assert res.json()["title"] == posting.title

    def test_넣은_기준이_채점_프롬프트_재료로_간다(self, client: TestClient, db: Session):
        """API 로 넣은 값이 summarizer 가 2단계 채점에 쓰는 변수까지 이어지는지."""
        from app.agent.summarizer import _build_prompt_vars

        pid = client.post(
            "/api/v1/postings",
            json={"title": "백엔드 개발자", "description": "담당 업무", "requirements": REQ, "preferred": PREF},
        ).json()["id"]
        fake_app = SimpleNamespace(
            job_posting_id=pid, name="김도현", education=None, career_years=None,
            skills=[], self_intro="자기소개", files=[],
        )
        v = _build_prompt_vars(db, fake_app)
        assert REQ in v["posting_requirements"]
        assert v["posting_preferred"] == PREF
