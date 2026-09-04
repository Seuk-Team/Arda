"""OpenTimestamps 병행 게시 + GitHub Actions 경로 (ADR-0028 3단계).

**캘린더에 실제로 안 보낸다.** `app.ots` 를 mock 한다 — 테스트가 외부 서비스와
비트코인 블록 시간에 매달리면 CI 에서 무작위로 깨진다.

여기서 보는 것은 "OTS 라이브러리가 도는가"가 아니라 **우리 쪽 규칙**이다:
네트워크가 갈리는가 · 도장 직후를 confirmed 로 적지 않는가 · 폴리곤과 OTS 를
서로 다른 행으로 세는가 · 밖에서 서명한 결과를 제대로 기록하는가.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import anchoring, ots
from app.chain import ChainConfig, SentTx
from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import Application, ChainPublication, User

PROOF = "base64로된가짜증명=="
CONFIG = ChainConfig("https://rpc.invalid", "0x" + "11" * 32, "polygon-amoy")
TX = "0x" + "ab" * 32


@pytest.fixture()
def admin(db: Session) -> User:
    user = User(
        email="ots-admin@fixture.local", password_hash="h", name="OTS관리자", role="admin"
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def member(db: Session) -> User:
    user = User(
        email="ots-member@fixture.local", password_hash="h", name="OTS멤버", role="member"
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def admin_client(db: Session, admin: User) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: admin
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def member_client(db: Session, member: User) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: member
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def anchored(db: Session, application: Application) -> Application:
    application.self_intro = "저는 결제 시스템을 3년 만들었습니다."
    db.flush()
    anchoring.anchor_application(db, application.id)
    return application


# ── OTS 게시 ──────────────────────────────────────────────────────────


class TestPublishOts:
    def test_도장을_찍고_증명을_보관한다(self, db: Session, anchored: Application):
        """폴리곤은 tx_hash 만 있으면 되지만 **OTS 는 증명 파일이 근거**다."""
        with (
            patch("app.anchoring.ots.stamp", return_value=PROOF),
            patch("app.anchoring.ots.is_confirmed", return_value=False),
        ):
            row = anchoring.publish_ots(db)

        assert row.network == "opentimestamps"
        assert row.proof == PROOF
        assert row.tx_hash is None  # 거래가 아니다

    def test_도장_직후는_confirmed_가_아니다(self, db: Session, anchored: Application):
        """비트코인 블록에 아직 안 실렸다. 여기서 확정으로 적으면 **우리가 가진
        것보다 강한 주장**이 된다."""
        with (
            patch("app.anchoring.ots.stamp", return_value=PROOF),
            patch("app.anchoring.ots.is_confirmed", return_value=False),
        ):
            row = anchoring.publish_ots(db)

        assert row.status == "pending"
        assert row.confirmed_at is None

    def test_캘린더가_전부_죽으면_사유가_남는다(self, db: Session, anchored: Application):
        with patch(
            "app.anchoring.ots.stamp", side_effect=RuntimeError("모든 OTS 캘린더가 실패")
        ):
            with pytest.raises(RuntimeError):
                anchoring.publish_ots(db)

        row = db.scalar(select(ChainPublication))
        assert row.status == "failed"
        assert "캘린더" in row.error

    def test_같은_머리를_두_번_도장하지_않는다(self, db: Session, anchored: Application):
        with (
            patch("app.anchoring.ots.stamp", return_value=PROOF),
            patch("app.anchoring.ots.is_confirmed", return_value=False),
        ):
            anchoring.publish_ots(db)
            with pytest.raises(anchoring.NothingToPublish, match="이미 올렸습니다"):
                anchoring.publish_ots(db)

    def test_폴리곤과_OTS_는_서로_다른_행이다(self, db: Session, anchored: Application):
        """같은 사슬 머리라도 네트워크가 다르면 각각 올려야 한다.

        여기서 막히면 "폴리곤에 올렸으니 OTS 는 됐다"가 되어 **영구 증명이
        영영 안 생긴다.**
        """
        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch(
                "app.anchoring.chain.publish_hash",
                return_value=SentTx(TX, "0x" + "cd" * 20, 1, True),
            ),
            patch("app.anchoring.ots.stamp", return_value=PROOF),
            patch("app.anchoring.ots.is_confirmed", return_value=False),
        ):
            poly = anchoring.publish_head(db)
            stamped = anchoring.publish_ots(db)

        assert poly.chain_hash == stamped.chain_hash  # 같은 머리
        assert {poly.network, stamped.network} == {"polygon-amoy", "opentimestamps"}


class TestRefreshOts:
    def test_비트코인에_실리면_confirmed(self, db: Session, anchored: Application):
        with (
            patch("app.anchoring.ots.stamp", return_value=PROOF),
            patch("app.anchoring.ots.is_confirmed", return_value=False),
        ):
            anchoring.publish_ots(db)

        with (
            patch("app.anchoring.ots.upgrade", return_value=("완전한증명", True)),
            patch("app.anchoring.ots.bitcoin_height", return_value=870123),
        ):
            changed = anchoring.refresh_pending(db)

        assert changed[0].status == "confirmed"
        assert changed[0].block_number == 870123
        assert changed[0].proof == "완전한증명"

    def test_아직이면_건드리지_않는다(self, db: Session, anchored: Application):
        """몇 시간이 정상이다. 실패로 적으면 다시 도장을 찍게 된다."""
        with (
            patch("app.anchoring.ots.stamp", return_value=PROOF),
            patch("app.anchoring.ots.is_confirmed", return_value=False),
        ):
            anchoring.publish_ots(db)

        with patch("app.anchoring.ots.upgrade", return_value=(PROOF, False)):
            changed = anchoring.refresh_pending(db)

        assert changed == []
        assert db.scalar(select(ChainPublication)).status == "pending"


# ── GitHub Actions 경로 ────────────────────────────────────────────────


class TestExternalSignerFlow:
    """서버는 자리를 잡고 결과를 기록만 한다 — **서명은 밖에서** (팀장 검토 Q2)."""

    def test_자리를_먼저_잡는다(self, admin_client: TestClient, anchored):
        """보낸 뒤에 기록하면 '체인에는 있는데 우리는 모르는 거래'가 생긴다."""
        resp = admin_client.post(
            "/api/v1/integrity/publications/start?network=polygon-amoy"
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "pending"
        assert body["tx_hash"] is None  # 아직 안 보냈다
        assert len(body["chain_hash"]) == 64  # 올릴 값을 알려준다

    def test_올릴_것이_없으면_409(self, admin_client: TestClient, db: Session):
        resp = admin_client.post(
            "/api/v1/integrity/publications/start?network=polygon-amoy"
        )
        assert resp.status_code == 409

    def test_밖에서_서명한_결과를_기록한다(self, admin_client: TestClient, anchored):
        started = admin_client.post(
            "/api/v1/integrity/publications/start?network=polygon-amoy"
        ).json()

        resp = admin_client.post(
            f"/api/v1/integrity/publications/{started['id']}/result",
            json={
                "status": "confirmed",
                "tx_hash": TX,
                "block_number": 12345,
                "from_address": "0x" + "cd" * 20,
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "confirmed"
        assert body["tx_hash"] == TX
        assert body["explorer_url"] == f"https://amoy.polygonscan.com/tx/{TX}"

    def test_전송_실패도_기록된다(self, admin_client: TestClient, anchored):
        """조용히 사라지면 다음에 왜 안 됐는지 알 수 없다."""
        started = admin_client.post(
            "/api/v1/integrity/publications/start?network=polygon-amoy"
        ).json()

        resp = admin_client.post(
            f"/api/v1/integrity/publications/{started['id']}/result",
            json={"status": "failed", "error": "RPC 접속 실패"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "failed"
        assert "RPC 접속 실패" in resp.json()["error"]

    def test_없는_게시_id_는_404(self, admin_client: TestClient):
        resp = admin_client.post(
            "/api/v1/integrity/publications/999999/result", json={"status": "confirmed"}
        )
        assert resp.status_code == 404

    def test_모르는_상태값은_422(self, admin_client: TestClient, anchored):
        started = admin_client.post(
            "/api/v1/integrity/publications/start?network=polygon-amoy"
        ).json()
        resp = admin_client.post(
            f"/api/v1/integrity/publications/{started['id']}/result",
            json={"status": "대충성공"},
        )
        assert resp.status_code == 422

    def test_member_는_자리를_못_잡는다(self, member_client: TestClient, anchored):
        resp = member_client.post(
            "/api/v1/integrity/publications/start?network=polygon-amoy"
        )
        assert resp.status_code == 403

    def test_member_는_결과를_못_적는다(self, member_client: TestClient, anchored):
        resp = member_client.post(
            "/api/v1/integrity/publications/1/result", json={"status": "confirmed"}
        )
        assert resp.status_code == 403


class TestOtsApi:
    def test_member_는_도장을_못_찍는다(self, member_client: TestClient, anchored):
        assert member_client.post("/api/v1/integrity/publish/ots").status_code == 403

    def test_도장_성공(self, admin_client: TestClient, anchored):
        with (
            patch("app.anchoring.ots.stamp", return_value=PROOF),
            patch("app.anchoring.ots.is_confirmed", return_value=False),
        ):
            resp = admin_client.post("/api/v1/integrity/publish/ots")

        assert resp.status_code == 201
        body = resp.json()
        assert body["network"] == "opentimestamps"
        assert body["status"] == "pending"
        # 확정 전에는 가리킬 블록이 없다
        assert body["explorer_url"] is None

    def test_확정되면_비트코인_블록을_가리킨다(self, admin_client: TestClient, anchored):
        with (
            patch("app.anchoring.ots.stamp", return_value=PROOF),
            patch("app.anchoring.ots.is_confirmed", return_value=True),
            patch(
                "app.api.integrity.ots.explorer_url",
                return_value="https://mempool.space/block/870123",
            ),
        ):
            resp = admin_client.post("/api/v1/integrity/publish/ots")

        assert resp.json()["explorer_url"] == "https://mempool.space/block/870123"

    def test_캘린더_실패는_502(self, admin_client: TestClient, anchored):
        with patch("app.anchoring.ots.stamp", side_effect=RuntimeError("전부 실패")):
            resp = admin_client.post("/api/v1/integrity/publish/ots")
        assert resp.status_code == 502


class TestOtsModule:
    def test_사슬_머리를_다시_해시하지_않는다(self):
        """검증하는 쪽이 우리 DB 의 값과 그대로 맞춰볼 수 있어야 한다."""
        chain_hash = "ab" * 32
        assert ots._digest(chain_hash) == bytes.fromhex(chain_hash)

    def test_캘린더가_여럿이다(self):
        """하나만 쓰면 그 운영자가 사라질 때 그 기간 증명이 통째로 뜬다."""
        assert len(ots.CALENDARS) >= 2
