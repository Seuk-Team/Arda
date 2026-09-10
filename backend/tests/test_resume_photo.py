"""이력서 증명사진 뽑기 — 대리응시 확인용 (회의 2026-09-09 3번).

**저장하지 않는 경로**라서 검증할 것이 둘이다: 맞는 그림을 고르는가,
그리고 **못 골랐을 때 조용히 넘어가는가**. 후자가 더 중요하다 — 사진 하나
때문에 면접이 멈추면 안 된다.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.agent import photo
from app.db import get_db
from app.main import app as fastapi_app
from app.models import Application, InterviewSession, JobPosting, User


def png(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (128, 128, 128)).save(buf, format="PNG")
    return buf.getvalue()


class FakeFile:
    def __init__(self, kind: str, key: str = "x/resume.pdf"):
        self.id = 1
        self.kind = kind
        self.s3_key = key


class FakeApp:
    def __init__(self, *files: FakeFile):
        self.files = list(files)


class TestPortraitOf:
    def test_증명사진_한_장이면_그것을_고른다(self, monkeypatch):
        shot = png(600, 767)
        monkeypatch.setattr(photo, "images_of", lambda f: [shot])
        assert photo.portrait_of(FakeApp(FakeFile("resume"))) == shot

    def test_로고와_섞여_있으면_큰_쪽을_고른다(self, monkeypatch):
        logo, shot = png(120, 90), png(600, 767)
        monkeypatch.setattr(photo, "images_of", lambda f: [logo, shot])
        assert photo.portrait_of(FakeApp(FakeFile("resume"))) == shot

    def test_아이콘만_있으면_없는_것으로_본다(self, monkeypatch):
        """구분선·도장은 한 변이 80px 도 안 된다 — 사진이라 우기면 오탐만 는다."""
        monkeypatch.setattr(photo, "images_of", lambda f: [png(20, 20), png(40, 8)])
        assert photo.portrait_of(FakeApp(FakeFile("resume"))) is None

    def test_스캔한_페이지_전체는_사진이_아니다(self, monkeypatch):
        monkeypatch.setattr(photo, "images_of", lambda f: [png(5000, 5000)])
        assert photo.portrait_of(FakeApp(FakeFile("resume"))) is None

    def test_자소서만_올렸으면_None(self, monkeypatch):
        monkeypatch.setattr(photo, "images_of", lambda f: [png(600, 767)])
        assert photo.portrait_of(FakeApp(FakeFile("cover_letter"))) is None

    def test_그림이_깨져_있어도_죽지_않는다(self, monkeypatch):
        monkeypatch.setattr(photo, "images_of", lambda f: [b"not-an-image"])
        assert photo.portrait_of(FakeApp(FakeFile("resume"))) is None


class TestImagesOf:
    def test_S3가_실패해도_예외를_안_던진다(self, monkeypatch):
        """이력서를 못 내려받는 것은 사고지만, 면접을 멈출 사고는 아니다."""
        import app.s3 as s3

        monkeypatch.setattr(s3, "_client", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        assert photo.images_of(FakeFile("resume")) == []

    def test_docx_는_word_media_에서_꺼낸다(self, monkeypatch):
        import app.s3 as s3

        shot = png(600, 767)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<xml/>")
            z.writestr("word/media/image1.png", shot)
        monkeypatch.setattr(s3, "_client", lambda: _Obj(buf.getvalue()))
        assert photo.images_of(FakeFile("resume", "x/이력서.docx")) == [shot]


class _Obj:
    def __init__(self, body: bytes):
        self.body = body

    def get_object(self, **kw):
        return {"Body": io.BytesIO(self.body)}


@pytest.fixture()
def client(db: Session, monkeypatch) -> TestClient:
    monkeypatch.setenv("ARDA_SERVICE_TOKEN", "test-token-x")
    fastapi_app.dependency_overrides[get_db] = lambda: db
    yield TestClient(fastapi_app, raise_server_exceptions=False)
    fastapi_app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def session_token(db: Session, admin_user: User) -> str:
    posting = JobPosting(
        title="공고", description="본문", status="open", created_by=admin_user.id
    )
    db.add(posting)
    db.flush()
    application = Application(
        job_posting_id=posting.id,
        name="지원자김",
        email="c@test.local",
        phone="010-0000-0000",
        privacy_agreed_at=datetime.now(UTC),
    )
    db.add(application)
    db.flush()
    db.add(
        InterviewSession(
            application_id=application.id,
            token="tok-photo",
            status="in_progress",
            expires_at=datetime.now(UTC) + timedelta(days=7),
            created_by=admin_user.id,
        )
    )
    db.flush()
    return "tok-photo"


HEAD = {"X-Service-Token": "test-token-x"}


class TestPortraitEndpoint:
    def test_토큰_없으면_401(self, client, session_token):
        assert client.get(f"/api/v1/internal/interview/{session_token}/portrait").status_code == 401

    def test_사진이_있으면_바이트를_준다(self, client, session_token, monkeypatch):
        shot = png(600, 767)
        monkeypatch.setattr(photo, "portrait_of", lambda a: shot)
        r = client.get(f"/api/v1/internal/interview/{session_token}/portrait", headers=HEAD)
        assert r.status_code == 200
        assert r.content == shot

    def test_사진이_없으면_404(self, client, session_token, monkeypatch):
        """워커는 이걸 보고 **확인을 건너뛴다** — 실패가 아니다."""
        monkeypatch.setattr(photo, "portrait_of", lambda a: None)
        r = client.get(f"/api/v1/internal/interview/{session_token}/portrait", headers=HEAD)
        assert r.status_code == 404

    def test_없는_세션이면_404(self, client):
        r = client.get("/api/v1/internal/interview/nope/portrait", headers=HEAD)
        assert r.status_code == 404
