"""file_blobs 스트리밍 다운로드 (온프레미스 경로).

핵심: presign_download 가 `file_blobs` 존재 여부로 두 경로로 갈리는 것을 굳혀 둔다 —
- 있으면 티켓 URL (온프레미스, 서버 스트리밍)
- 없으면 기존 S3 URL (AWS)

티켓은 60초 1회용이므로 재사용은 401, file_id 를 바꿔 넣어도 401.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models import Application, File, FileBlob, User
from app.security import create_access_token, hash_password


@pytest.fixture()
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def staff(db: Session) -> User:
    u = User(email="fb-staff@fixture.local", name="시연", role="admin",
             is_active=True, password_hash=hash_password("passw0rd"))
    db.add(u); db.flush()
    return u


def _login_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role)}"}


def _mk_file(db: Session, application: Application, name: str = "이력서.pdf",
             kind: str = "resume", content: bytes = b"HELLO") -> File:
    f = File(application_id=application.id, s3_key=f"a/{name}",
             filename=name, size_bytes=len(content), content_type="application/pdf", kind=kind)
    db.add(f); db.flush()
    db.add(FileBlob(file_id=f.id, content=content, size_bytes=len(content),
                    sha256="a" * 64))
    db.commit()
    return f


def test_presign_download_로컬_저장분은_티켓_URL_로_돌려준다(
    client: TestClient, db: Session, staff: User, application: Application
):
    body = b"HELLO"
    f = _mk_file(db, application, content=body)

    res = client.get(f"/api/v1/files/{f.id}/presign-download", headers=_login_headers(staff))
    assert res.status_code == 200, res.text
    url = res.json()["download_url"]
    # 온프레미스 경로는 우리 API 를 가리켜야 한다 — S3/MinIO 호스트가 들어오면 브라우저가 못 푼다
    assert f"/api/v1/files/{f.id}/download?ticket=" in url
    ticket = url.split("ticket=")[1]

    # 실제 스트리밍 — 티켓만 있으면 로그인 없이도(브라우저 새 탭 시나리오) 200 이어야 한다
    dl = client.get(f"/api/v1/files/{f.id}/download?ticket={ticket}")
    assert dl.status_code == 200
    assert dl.content == body
    cd = dl.headers.get("content-disposition", "")
    assert "attachment" in cd and "filename*=UTF-8''" in cd

    # 같은 티켓 재사용은 막힌다 (1회용)
    again = client.get(f"/api/v1/files/{f.id}/download?ticket={ticket}")
    assert again.status_code == 401


def test_티켓은_다른_file_id_에_통하지_않는다(
    client: TestClient, db: Session, staff: User, application: Application
):
    a = _mk_file(db, application, name="a.pdf", kind="resume", content=b"A")
    b = _mk_file(db, application, name="b.pdf", kind="cover_letter", content=b"B")

    res = client.get(f"/api/v1/files/{a.id}/presign-download", headers=_login_headers(staff))
    ticket_for_a = res.json()["download_url"].split("ticket=")[1]

    # b 로 쓰면 401 이어야 한다 — 티켓이 file_id 에 묶여야 아무 이력서든 열리지 않는다
    other = client.get(f"/api/v1/files/{b.id}/download?ticket={ticket_for_a}")
    assert other.status_code == 401


def test_로그인_없이_presign_은_401(
    client: TestClient, db: Session, application: Application
):
    f = _mk_file(db, application)
    res = client.get(f"/api/v1/files/{f.id}/presign-download")
    assert res.status_code == 401
