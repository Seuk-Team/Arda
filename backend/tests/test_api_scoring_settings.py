"""관리자 채점 기준 설정 (GET·PUT /settings/scoring, 2026-10-19).

관리자 화면 「채점 기준」 탭이 쓰는 API. 비중을 저장하면 서류·면접·최종 합산
(`screening.weights`)이 그 값을 읽는지, 한 묶음을 전부 0 으로 보내면 막히는지 본다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.application import screening
from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import User


@pytest.fixture()
def client(db: Session, admin_user: User):
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: admin_user
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _weights(**override: int) -> dict[str, int]:
    return {**screening.DEFAULT_WEIGHTS, **override}


class TestScoringSettings:
    def test_처음엔_기본값이_온다(self, client: TestClient):
        res = client.get("/api/v1/settings/scoring")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["weights"] == screening.DEFAULT_WEIGHTS
        assert body["defaults"] == screening.DEFAULT_WEIGHTS

    def test_저장한_비중을_합산이_읽는다(self, client: TestClient, db: Session):
        # 진위 일관성을 0 으로 — 면접 점수는 답변 내용만으로 100 환산된다
        res = client.put("/api/v1/settings/scoring", json={"weights": _weights(itv_truth=0)})
        assert res.status_code == 200, res.text
        assert res.json()["weights"]["itv_truth"] == 0

        w = screening.weights(db)
        assert w["itv_truth"] == 0
        assert screening.interview_score_from(80, 20, w) == 80

    @pytest.mark.parametrize(
        "zeroed",
        [
            {"doc_requirements": 0, "doc_preferred": 0, "doc_culture": 0},
            {"itv_answers": 0, "itv_truth": 0},
            {"doc": 0, "interview": 0},
        ],
    )
    def test_한_묶음이_전부_0이면_422(self, client: TestClient, db: Session, zeroed: dict):
        res = client.put("/api/v1/settings/scoring", json={"weights": _weights(**zeroed)})
        assert res.status_code == 422, res.text
        # 막혔으면 저장도 안 됐다
        assert screening.weights(db) == screening.DEFAULT_WEIGHTS

    def test_관리자가_아니면_못_바꾼다(self, client: TestClient, admin_user: User, db: Session):
        admin_user.role = "member"
        db.flush()
        res = client.put("/api/v1/settings/scoring", json={"weights": _weights(itv_truth=0)})
        assert res.status_code == 403, res.text
