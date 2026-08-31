"""공개 지원서 제출 (C2) — 특히 F1 → C2 파일 연결.

presign(F1)은 발급 시점에 지원서가 없어 `files` 행을 만들지 못한다
(`files.application_id` 가 NOT NULL). 그래서 접수 때 메타를 함께 받아 여기서 만든다.
그 고리가 비어 있으면 이력서가 S3 에만 뜨고 담당자는 영영 못 받는다.

키 검증을 접수 시점에 또 하는 이유는 presign 을 건너뛰고 이 엔드포인트만
두드리는 경우다 — 그때 키를 그냥 믿으면 남의 파일을 자기 지원서에 붙일 수 있다.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models import Application, File, JobPosting

PDF = "application/pdf"


def _key(kind: str = "resume", ext: str = "pdf") -> str:
    """서버가 발급하는 것과 같은 모양의 키 (files.py `_build_key`)."""
    return f"applications/{uuid.uuid4()}/{kind}.{ext}"


def _body(**over) -> dict:
    body = {
        "name": "김도현",
        "email": f"apply-{uuid.uuid4().hex[:8]}@example.com",
        "phone": "010-1234-5678",
        "privacy_agreed": True,
    }
    body.update(over)
    return body


def _file(**over) -> dict:
    item = {
        "s3_key": _key(),
        "filename": "김도현_이력서.pdf",
        "size_bytes": 1024,
        "content_type": PDF,
        "kind": "resume",
    }
    item.update(over)
    return item


@pytest.fixture()
def client(db: Session) -> TestClient:
    """공개 엔드포인트라 인증을 걸지 않는다."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


def _submit(client: TestClient, posting: JobPosting, **over):
    return client.post(f"/api/v1/public/postings/{posting.id}/applications", json=_body(**over))


class TestSubmitWithoutFiles:
    def test_파일_없이도_접수된다(self, client: TestClient, posting: JobPosting):
        # 파일은 선택이다 — 없다고 막으면 이력서를 메일로 보내는 지원자를 잃는다.
        res = _submit(client, posting)
        assert res.status_code == 201

    def test_동의하지_않으면_거절(self, client: TestClient, posting: JobPosting):
        res = _submit(client, posting, privacy_agreed=False)
        assert res.status_code == 422


class TestSubmitWithFiles:
    def test_files_행이_생긴다(self, client: TestClient, db: Session, posting: JobPosting):
        item = _file()
        res = _submit(client, posting, files=[item])
        assert res.status_code == 201

        rows = db.scalars(
            select(File).where(File.application_id == res.json()["id"])
        ).all()
        assert len(rows) == 1
        assert rows[0].s3_key == item["s3_key"]
        assert rows[0].kind == "resume"
        assert rows[0].filename == "김도현_이력서.pdf"

    def test_이력서와_자소서_둘_다(self, client: TestClient, db: Session, posting: JobPosting):
        files = [
            _file(),
            _file(
                s3_key=_key("cover_letter", "docx"),
                filename="김도현_자소서.docx",
                content_type=(
                    "application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"
                ),
                kind="cover_letter",
            ),
        ]
        res = _submit(client, posting, files=files)
        assert res.status_code == 201
        rows = db.scalars(
            select(File).where(File.application_id == res.json()["id"])
        ).all()
        assert {r.kind for r in rows} == {"resume", "cover_letter"}


class TestFileKeyIsNotTrusted:
    """키를 그냥 믿으면 남의 파일을 자기 지원서에 붙일 수 있다."""

    def test_서버가_낸_모양이_아니면_422(self, client: TestClient, posting: JobPosting):
        res = _submit(client, posting, files=[_file(s3_key="../../etc/passwd")])
        assert res.status_code == 422

    def test_키의_종류와_kind_가_다르면_422(self, client: TestClient, posting: JobPosting):
        # cover_letter 키를 resume 이라고 주장한다
        res = _submit(client, posting, files=[_file(s3_key=_key("cover_letter"))])
        assert res.status_code == 422

    def test_같은_종류_둘이면_422(self, client: TestClient, posting: JobPosting):
        res = _submit(client, posting, files=[_file(), _file()])
        assert res.status_code == 422

    def test_파일명_확장자가_키와_다르면_422(self, client: TestClient, posting: JobPosting):
        res = _submit(client, posting, files=[_file(filename="이력서.hwp")])
        assert res.status_code == 422

    def test_허용되지_않는_형식은_422(self, client: TestClient, posting: JobPosting):
        res = _submit(
            client,
            posting,
            files=[_file(s3_key=_key("resume", "exe"), filename="a.exe", content_type=PDF)],
        )
        assert res.status_code == 422

    def test_10MB_초과는_413(self, client: TestClient, posting: JobPosting):
        res = _submit(client, posting, files=[_file(size_bytes=11 * 1024 * 1024)])
        assert res.status_code == 413

    def test_거절되면_지원서도_남지_않는다(
        self, client: TestClient, db: Session, posting: JobPosting
    ):
        # 파일이 거절됐는데 지원서만 남으면, 담당자는 이력서 없는 지원서를 받는다.
        email = f"reject-{uuid.uuid4().hex[:8]}@example.com"
        res = _submit(client, posting, email=email, files=[_file(s3_key="bad")])
        assert res.status_code == 422
        assert db.scalar(select(Application).where(Application.email == email)) is None
