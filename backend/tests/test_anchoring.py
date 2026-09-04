"""제출물 무결성 앵커 (ADR-0028).

원본을 바꿔치기했을 때 **실제로 드러나는가**를 본다. 해시 함수가 도는지가 아니라,
바뀐 것이 잡히고 안 바뀐 것이 안 잡히는지가 이 표의 존재 이유다.

S3 는 mock 이다 — 지문 계산에 필요한 것은 바이트뿐이라 실제 버킷이 필요 없다.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app import anchoring
from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import Application, DocumentAnchor, File, User

RESUME_BYTES = b"%PDF-1.4 \xea\xb9\x80\xeb\x8f\x84\xed\x98\x84 resume"
TAMPERED_BYTES = b"%PDF-1.4 \xea\xb9\x80\xeb\x8f\x84\xed\x98\x84 resume (\xea\xb3\xa0\xec\xb3\x90\xec\x84\x9c)"


@pytest.fixture()
def member(db: Session) -> User:
    user = User(
        email="anchor-member@fixture.local",
        password_hash="hashed",
        name="앵커멤버",
        role="member",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def client(db: Session, member: User) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: member
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def unauth_client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def with_intro(db: Session, application: Application) -> Application:
    application.self_intro = "저는 결제 시스템을 3년 만들었습니다."
    db.flush()
    return application


@pytest.fixture()
def resume(db: Session, application: Application) -> File:
    row = File(
        application_id=application.id,
        s3_key=f"applications/{'0' * 8}-0000-0000-0000-{'0' * 12}/resume.pdf",
        filename="이력서.pdf",
        size_bytes=len(RESUME_BYTES),
        content_type="application/pdf",
        kind="resume",
    )
    db.add(row)
    db.flush()
    return row


# ── 앵커 ──────────────────────────────────────────────────────────────


class TestAnchor:
    def test_자기소개_지문이_남는다(self, db: Session, with_intro: Application):
        made = anchoring.anchor_application(db, with_intro.id)

        assert [m.doc_type for m in made] == ["self_intro"]
        assert made[0].content_sha256 == anchoring.sha256_text(with_intro.self_intro)
        assert made[0].file_id is None

    def test_자기소개가_비어_있으면_앵커하지_않는다(
        self, db: Session, application: Application
    ):
        """없는 문서의 지문은 의미가 없다.

        떠 두면 나중에 지원자가 자기소개를 채워 넣은 것을 "바뀌었다"로 잡는다.
        """
        assert anchoring.anchor_application(db, application.id) == []

    def test_첨부_지문은_S3_본문에서_뜬다(
        self, db: Session, application: Application, resume: File
    ):
        """`size_bytes` 같은 신고값이 아니라 실제 바이트에서 떠야 한다."""
        with patch("app.anchoring.s3.read_object", return_value=RESUME_BYTES):
            made = anchoring.anchor_application(db, application.id)

        assert [m.doc_type for m in made] == ["resume"]
        assert made[0].content_sha256 == anchoring.sha256_bytes(RESUME_BYTES)
        assert made[0].file_id == resume.id

    def test_두_번_불러도_사슬이_부풀지_않는다(
        self, db: Session, with_intro: Application, resume: File
    ):
        """재시도·백필이 같은 문서를 두 번 쌓으면 원장이 못 쓰게 된다."""
        with patch("app.anchoring.s3.read_object", return_value=RESUME_BYTES):
            first = anchoring.anchor_application(db, with_intro.id)
            second = anchoring.anchor_application(db, with_intro.id)

        assert len(first) == 2
        assert second == []
        assert db.scalar(select(DocumentAnchor.seq).order_by(DocumentAnchor.seq.desc())) == 2

    def test_S3_를_못_읽어도_자기소개는_앵커된다(
        self, db: Session, with_intro: Application, resume: File
    ):
        """파일 하나가 실패했다고 나머지 지문까지 포기하지 않는다."""
        with patch("app.anchoring.s3.read_object", side_effect=OSError("S3 다운")):
            made = anchoring.anchor_application(db, with_intro.id)

        assert [m.doc_type for m in made] == ["self_intro"]

    def test_고리가_앞_고리를_재료로_쓴다(
        self, db: Session, with_intro: Application, resume: File
    ):
        """사슬의 핵심 — 이게 아니면 그냥 해시 목록이다."""
        with patch("app.anchoring.s3.read_object", return_value=RESUME_BYTES):
            made = anchoring.anchor_application(db, with_intro.id)

        assert made[0].prev_chain_hash is None  # 첫 고리
        assert made[1].prev_chain_hash == made[0].chain_hash


# ── 검증 ──────────────────────────────────────────────────────────────


class TestVerify:
    def test_안_바뀌었으면_ok(self, db: Session, with_intro: Application):
        anchoring.anchor_application(db, with_intro.id)
        anchor = db.scalar(select(DocumentAnchor))

        assert anchoring.verify_anchor(db, anchor)["status"] == "ok"

    def test_자기소개를_고치면_mismatch(self, db: Session, with_intro: Application):
        """이 표가 잡으려던 바로 그것."""
        anchoring.anchor_application(db, with_intro.id)
        anchor = db.scalar(select(DocumentAnchor))

        with_intro.self_intro = "저는 결제 시스템을 10년 만들었습니다."
        db.flush()

        assert anchoring.verify_anchor(db, anchor)["status"] == "mismatch"

    def test_첨부를_바꿔치기하면_mismatch(
        self, db: Session, application: Application, resume: File
    ):
        with patch("app.anchoring.s3.read_object", return_value=RESUME_BYTES):
            anchoring.anchor_application(db, application.id)
        anchor = db.scalar(select(DocumentAnchor))

        with patch("app.anchoring.s3.read_object", return_value=TAMPERED_BYTES):
            assert anchoring.verify_anchor(db, anchor)["status"] == "mismatch"

    def test_못_읽는_것과_바뀐_것을_가른다(
        self, db: Session, application: Application, resume: File
    ):
        """담당자가 할 일이 다르다 — 없어졌으면 다시 받고, 바뀌었으면 따진다."""
        with patch("app.anchoring.s3.read_object", return_value=RESUME_BYTES):
            anchoring.anchor_application(db, application.id)
        anchor = db.scalar(select(DocumentAnchor))

        with patch("app.anchoring.s3.read_object", side_effect=OSError("없음")):
            assert anchoring.verify_anchor(db, anchor)["status"] == "unreadable"


class TestChain:
    def test_손대지_않았으면_이어진다(
        self, db: Session, with_intro: Application, resume: File
    ):
        with patch("app.anchoring.s3.read_object", return_value=RESUME_BYTES):
            anchoring.anchor_application(db, with_intro.id)

        result = anchoring.verify_chain(db)
        assert result["intact"] is True
        assert result["length"] == 2

    def test_원장_한_줄을_고치면_깨진다(self, db: Session, with_intro: Application):
        """원본과 앵커를 **같이** 고쳐 개별 검증을 통과시켜도 사슬은 못 속인다.

        여기서는 **트리거를 끄고** 고친다 — 앱을 통해서는 이제 불가능하고
        (`TestAppendOnly`), 이 시나리오가 성립하려면 트리거를 끌 수 있는 권한자여야
        하기 때문이다. ADR-0028 이 "내부자는 못 막는다"고 적어 둔 그 자리를
        그대로 재현한 것이다.
        """
        anchoring.anchor_application(db, with_intro.id)
        anchor = db.scalar(select(DocumentAnchor))

        db.execute(
            text("ALTER TABLE document_anchors DISABLE TRIGGER trg_document_anchors_append_only")
        )
        with_intro.self_intro = "위조된 자기소개"
        anchor.content_sha256 = anchoring.sha256_text(with_intro.self_intro)
        db.flush()

        # 개별 검증은 통과한다 — 둘을 맞춰 놨으니까
        assert anchoring.verify_anchor(db, anchor)["status"] == "ok"
        # 그러나 고리를 다시 계산하면 안 나온다
        result = anchoring.verify_chain(db)
        assert result["intact"] is False
        assert result["broken_at"] == anchor.seq

    def test_빈_원장은_이어진_것으로_본다(self, db: Session):
        assert anchoring.verify_chain(db)["intact"] is True


# ── 추가 전용 잠금 ────────────────────────────────────────────────────


class TestAppendOnly:
    """원장을 DB 가 직접 지킨다 (alembic 0006).

    "고쳐 쓰지 않는다"가 코드의 약속이기만 하면 psql 한 줄이면 끝난다.
    여기서 보는 것은 **약속이 아니라 DB 가 거부하는가**다.
    """

    @pytest.fixture()
    def anchor(self, db: Session, with_intro: Application) -> DocumentAnchor:
        anchoring.anchor_application(db, with_intro.id)
        return db.scalar(select(DocumentAnchor))

    def test_지문을_고치면_거부된다(self, db: Session, anchor: DocumentAnchor):
        with pytest.raises(DBAPIError, match="고쳐 쓸 수 없습니다"):
            db.execute(
                text("UPDATE document_anchors SET content_sha256 = :h WHERE id = :i"),
                {"h": "0" * 64, "i": anchor.id},
            )

    def test_사슬_고리를_고치면_거부된다(self, db: Session, anchor: DocumentAnchor):
        with pytest.raises(DBAPIError, match="고쳐 쓸 수 없습니다"):
            db.execute(
                text("UPDATE document_anchors SET chain_hash = :h WHERE id = :i"),
                {"h": "1" * 64, "i": anchor.id},
            )

    def test_시각을_고치면_거부된다(self, db: Session, anchor: DocumentAnchor):
        """`anchored_at` 은 chain_hash 의 재료다. 여기가 뚫리면 사슬이 뚫린다.

        `now()` 로 쓰지 않는다 — 트랜잭션 안에서 `now()` 는 트랜잭션 시작 시각이라
        방금 넣은 값과 같아지고, 트리거는 "안 바뀌었다"로 보고 통과시킨다.
        (그게 맞는 동작이다. 값이 실제로 달라져야 막을 일이다.)
        """
        with pytest.raises(DBAPIError, match="고쳐 쓸 수 없습니다"):
            db.execute(
                text(
                    "UPDATE document_anchors SET anchored_at = anchored_at"
                    " + interval '1 day' WHERE id = :i"
                ),
                {"i": anchor.id},
            )

    def test_삭제가_거부된다(self, db: Session, anchor: DocumentAnchor):
        with pytest.raises(DBAPIError, match="삭제할 수 없습니다"):
            db.execute(
                text("DELETE FROM document_anchors WHERE id = :i"), {"i": anchor.id}
            )

    def test_비우기가_거부된다(self, db: Session, anchor: DocumentAnchor):
        """TRUNCATE 는 행 트리거를 타지 않는다 — 따로 막아야 한다."""
        with pytest.raises(DBAPIError, match="비울 수 없습니다"):
            db.execute(text("TRUNCATE document_anchors"))

    def test_ots_칸은_고칠_수_있다(self, db: Session, anchor: DocumentAnchor):
        """2단계(공개 타임스탬프)가 쓸 자리는 열어 둬야 한다.

        막아 두면 2단계에서 이 트리거를 걷어내게 되고, 그러면 잠금이 잠금이 아니다.
        """
        db.execute(
            text(
                "UPDATE document_anchors SET ots_status = 'pending', ots_proof = :p"
                " WHERE id = :i"
            ),
            {"p": "증명파일", "i": anchor.id},
        )
        db.expire(anchor)
        assert anchor.ots_status == "pending"

    def test_새_행은_계속_쌓인다(self, db: Session, anchor: DocumentAnchor, resume: File):
        """잠금이 append 까지 막으면 기능 자체가 죽는다."""
        with patch("app.anchoring.s3.read_object", return_value=RESUME_BYTES):
            made = anchoring.anchor_application(db, anchor.application_id)

        assert [m.doc_type for m in made] == ["resume"]


# ── API ───────────────────────────────────────────────────────────────


class TestIntegrityApi:
    def test_무인증은_401(self, unauth_client: TestClient, application: Application):
        resp = unauth_client.get(f"/api/v1/applications/{application.id}/integrity")
        assert resp.status_code == 401

    def test_없는_지원자는_404(self, client: TestClient):
        assert client.get("/api/v1/applications/999999/integrity").status_code == 404

    def test_앵커가_없으면_none(self, client: TestClient, application: Application):
        """`ok` 와 섞지 않는다 — "깨끗하다"가 아니라 "증명할 근거가 없다"다."""
        resp = client.get(f"/api/v1/applications/{application.id}/integrity")

        assert resp.status_code == 200
        assert resp.json()["verdict"] == "none"
        assert resp.json()["anchored"] is False

    def test_백필로_앵커를_만든다(self, client: TestClient, with_intro: Application):
        resp = client.post(f"/api/v1/applications/{with_intro.id}/integrity/anchor")

        assert resp.status_code == 201
        body = resp.json()
        assert body["verdict"] == "ok"
        assert [i["doc_type"] for i in body["items"]] == ["self_intro"]

    def test_바뀐_뒤_조회하면_mismatch(
        self, client: TestClient, db: Session, with_intro: Application
    ):
        client.post(f"/api/v1/applications/{with_intro.id}/integrity/anchor")

        with_intro.self_intro = "다른 내용으로 바꿔치기"
        db.flush()

        resp = client.get(f"/api/v1/applications/{with_intro.id}/integrity")
        assert resp.json()["verdict"] == "mismatch"

    def test_첨부_이름이_같이_내려온다(
        self, client: TestClient, application: Application, resume: File
    ):
        """담당자가 어느 파일이 어긋났는지 알아야 조치할 수 있다."""
        with patch("app.anchoring.s3.read_object", return_value=RESUME_BYTES):
            resp = client.post(f"/api/v1/applications/{application.id}/integrity/anchor")

        assert resp.json()["items"][0]["filename"] == "이력서.pdf"

    def test_사슬_조회(self, client: TestClient, with_intro: Application):
        client.post(f"/api/v1/applications/{with_intro.id}/integrity/anchor")

        resp = client.get("/api/v1/integrity/chain")
        assert resp.status_code == 200
        assert resp.json()["intact"] is True
        assert resp.json()["length"] == 1
