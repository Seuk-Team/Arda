"""사슬 머리를 공개 체인에 못 박기 (ADR-0028 2단계).

**체인에는 실제로 안 보낸다.** `app.chain` 을 mock 한다 — 테스트가 외부
네트워크·가스·블록 시간에 매달리면 CI 에서 무작위로 깨지고, 무엇보다 테스트가
진짜 거래를 보내면 안 된다.

여기서 보는 것은 "web3 가 도는가"가 아니라 **우리 쪽 규칙**이다:
같은 값을 두 번 올리지 않는가 · 실패해도 기록이 남는가 · 보냈는데 확정을
못 본 것을 실패로 적지 않는가 · 권한이 좁혀져 있는가.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import anchoring
from app.chain import ChainConfig, SentTx
from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import Application, ChainPublication, User

CONFIG = ChainConfig(
    rpc_url="https://rpc-amoy.example.invalid",
    private_key="0x" + "11" * 32,  # 테스트용 더미. 실제 지갑이 아니다
    network="polygon-amoy",
)
TX = "0x" + "ab" * 32
ADDR = "0x" + "cd" * 20


def _sent(confirmed: bool = True, block: int | None = 12345, tx: str = TX) -> SentTx:
    return SentTx(tx_hash=tx, from_address=ADDR, block_number=block, confirmed=confirmed)


@pytest.fixture()
def admin(db: Session) -> User:
    user = User(
        email="chain-admin@fixture.local",
        password_hash="hashed",
        name="체인관리자",
        role="admin",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def member(db: Session) -> User:
    user = User(
        email="chain-member@fixture.local",
        password_hash="hashed",
        name="체인멤버",
        role="member",
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
    """고리 하나가 쌓인 원장."""
    application.self_intro = "저는 결제 시스템을 3년 만들었습니다."
    db.flush()
    anchoring.anchor_application(db, application.id)
    return application


# ── 게시 ──────────────────────────────────────────────────────────────


class TestPublishHead:
    def test_머리_하나를_올린다(self, db: Session, anchored: Application):
        """올리는 값은 언제나 **사슬 머리 하나**다 — 그게 앞을 전부 덮는다."""
        head = db.scalar(select(anchoring.DocumentAnchor).order_by(
            anchoring.DocumentAnchor.seq.desc()
        ))
        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch("app.anchoring.chain.publish_hash", return_value=_sent()) as sent,
        ):
            row = anchoring.publish_head(db)

        assert sent.call_args.args[1] == head.chain_hash  # 머리 그대로
        assert row.status == "confirmed"
        assert row.tx_hash == TX
        assert row.covered_through_seq == head.seq
        assert row.network == "polygon-amoy"

    def test_같은_머리를_두_번_올리지_않는다(self, db: Session, anchored: Application):
        """가스만 쓰고 증명력은 하나도 안 는다."""
        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch("app.anchoring.chain.publish_hash", return_value=_sent()),
        ):
            anchoring.publish_head(db)
            with pytest.raises(anchoring.NothingToPublish, match="새 고리가 없습니다"):
                anchoring.publish_head(db)

    def test_빈_원장은_올릴_것이_없다(self, db: Session):
        with patch("app.anchoring.chain.load_config", return_value=CONFIG):
            with pytest.raises(anchoring.NothingToPublish, match="비어 있습니다"):
                anchoring.publish_head(db)

    def test_새_고리가_쌓이면_다시_올린다(
        self, db: Session, anchored: Application, posting
    ):
        # 거래마다 해시가 다르다 — 실제 체인도 그렇다 (tx_hash 는 UNIQUE).
        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch(
                "app.anchoring.chain.publish_hash",
                side_effect=[_sent(), _sent(tx="0x" + "ef" * 32)],
            ),
        ):
            first = anchoring.publish_head(db)

            other = Application(
                job_posting_id=posting.id,
                name="다음지원자",
                email="chain-next@fixture.local",
                phone="010-0000-0000",
                current_stage="applied",
                privacy_agreed_at=first.created_at,
                source="form",
                self_intro="새 자기소개",
            )
            db.add(other)
            db.flush()
            anchoring.anchor_application(db, other.id)

            second = anchoring.publish_head(db)

        assert second.covered_through_seq > first.covered_through_seq

    def test_보내다_실패하면_사유가_남는다(self, db: Session, anchored: Application):
        """다음 시도의 유일한 단서다. 조용히 사라지면 안 된다."""
        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch(
                "app.anchoring.chain.publish_hash",
                side_effect=ConnectionError("RPC 접속 실패"),
            ),
        ):
            with pytest.raises(ConnectionError):
                anchoring.publish_head(db)

        row = db.scalar(select(ChainPublication))
        assert row.status == "failed"
        assert "RPC 접속 실패" in row.error
        assert row.tx_hash is None

    def test_확정을_못_봤어도_실패가_아니다(self, db: Session, anchored: Application):
        """보낸 것은 보낸 것이다. 실패로 적으면 같은 값을 두 번 보내게 된다."""
        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch(
                "app.anchoring.chain.publish_hash",
                return_value=_sent(confirmed=False, block=None),
            ),
        ):
            row = anchoring.publish_head(db)

        assert row.status == "pending"
        assert row.tx_hash == TX  # 거래 해시는 남아 있다 — 나중에 다시 확인한다

    def test_설정이_없으면_거래를_만들지_않는다(self, db: Session, anchored: Application):
        with patch("app.anchoring.chain.load_config", return_value=None):
            with pytest.raises(RuntimeError):
                anchoring.publish_head(db)

        assert db.scalar(select(ChainPublication)) is None


class TestRefresh:
    def test_뒤늦게_확정되면_바뀐다(self, db: Session, anchored: Application):
        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch(
                "app.anchoring.chain.publish_hash",
                return_value=_sent(confirmed=False, block=None),
            ),
        ):
            row = anchoring.publish_head(db)
        assert row.status == "pending"

        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch("app.anchoring.chain.fetch_status", return_value=_sent()),
        ):
            changed = anchoring.refresh_pending(db)

        assert [c.status for c in changed] == ["confirmed"]
        assert changed[0].block_number == 12345

    def test_체인이_되돌린_거래는_failed(self, db: Session, anchored: Application):
        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch(
                "app.anchoring.chain.publish_hash",
                return_value=_sent(confirmed=False, block=None),
            ),
        ):
            anchoring.publish_head(db)

        with (
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch(
                "app.anchoring.chain.fetch_status",
                return_value=_sent(confirmed=False, block=999),
            ),
        ):
            changed = anchoring.refresh_pending(db)

        assert changed[0].status == "failed"
        assert "되돌렸습니다" in changed[0].error


# ── API ───────────────────────────────────────────────────────────────


class TestPublishApi:
    def test_member_는_올릴_수_없다(self, member_client: TestClient, anchored):
        """돈이 나가고 되돌릴 수 없는 바깥 행위라 admin 으로 좁혔다."""
        assert member_client.post("/api/v1/integrity/publish").status_code == 403

    def test_설정이_없으면_503(self, admin_client: TestClient, anchored):
        """왜 안 되는지 상태 코드로 갈린다 — 409(올릴 것 없음)와 다른 사유다."""
        with patch("app.api.integrity.chain.unavailable_reason", return_value="CHAIN_RPC_URL 미설정"):
            resp = admin_client.post("/api/v1/integrity/publish")

        assert resp.status_code == 503
        assert "CHAIN_RPC_URL" in resp.json()["message"]

    def test_올릴_것이_없으면_409(self, admin_client: TestClient, db: Session):
        with (
            patch("app.api.integrity.chain.unavailable_reason", return_value=None),
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
        ):
            resp = admin_client.post("/api/v1/integrity/publish")

        assert resp.status_code == 409

    def test_성공하면_탐색기_링크가_같이_온다(self, admin_client: TestClient, anchored):
        """발표에서 이 링크를 그대로 연다."""
        with (
            patch("app.api.integrity.chain.unavailable_reason", return_value=None),
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch("app.anchoring.chain.publish_hash", return_value=_sent()),
        ):
            resp = admin_client.post("/api/v1/integrity/publish")

        assert resp.status_code == 201
        body = resp.json()
        assert body["tx_hash"] == TX
        assert body["explorer_url"] == f"https://amoy.polygonscan.com/tx/{TX}"

    def test_체인_조회에_게시_상태가_붙는다(self, admin_client: TestClient, anchored):
        """'우리 DB 안의 주장'과 '밖에서 확인되는 사실'을 한 화면에서 가른다."""
        before = admin_client.get("/api/v1/integrity/chain").json()
        assert before["published"] is None
        assert before["unpublished_count"] == 1

        with (
            patch("app.api.integrity.chain.unavailable_reason", return_value=None),
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch("app.anchoring.chain.publish_hash", return_value=_sent()),
        ):
            admin_client.post("/api/v1/integrity/publish")

        after = admin_client.get("/api/v1/integrity/chain").json()
        assert after["published"]["tx_hash"] == TX
        assert after["unpublished_count"] == 0

    def test_목록_조회(self, admin_client: TestClient, anchored):
        with (
            patch("app.api.integrity.chain.unavailable_reason", return_value=None),
            patch("app.anchoring.chain.load_config", return_value=CONFIG),
            patch("app.anchoring.chain.publish_hash", return_value=_sent()),
        ):
            admin_client.post("/api/v1/integrity/publish")

        rows = admin_client.get("/api/v1/integrity/publications").json()
        assert len(rows) == 1
        assert rows[0]["covered_through_seq"] == 1


# ── 설정 읽기 ─────────────────────────────────────────────────────────


class TestConfig:
    def test_환경변수가_없으면_꺼진_상태다(self, monkeypatch):
        """꺼진 것이 정상 상태다 — 설정이 없다고 접수가 막히면 안 된다."""
        from app import chain

        monkeypatch.delenv("CHAIN_RPC_URL", raising=False)
        monkeypatch.delenv("CHAIN_PRIVATE_KEY", raising=False)

        assert chain.load_config() is None
        assert chain.unavailable_reason() == "CHAIN_RPC_URL 미설정"

    def test_키가_이상하면_사유를_말한다(self, monkeypatch):
        from app import chain

        monkeypatch.setenv("CHAIN_RPC_URL", "https://x.invalid")
        monkeypatch.setenv("CHAIN_PRIVATE_KEY", "이건키가아니다")

        reason = chain.unavailable_reason()
        assert reason is not None and "CHAIN_PRIVATE_KEY" in reason

    def test_메인넷만_메인넷으로_본다(self):
        """보수적으로 판단한다 — 확실할 때만 메인넷이라고 한다."""
        from app import chain

        amoy = ChainConfig("u", "k", "polygon-amoy")
        main = ChainConfig("u", "k", "polygon-mainnet")
        assert amoy.is_testnet is True
        assert main.is_testnet is False
        assert chain.DEFAULT_NETWORK == "polygon-amoy"  # 기본이 테스트넷이어야 한다
