"""사용자 관리 (A4) — 목록·역할 변경·비활성화.

여기서 지키는 것은 둘이다.

1. **잠금 사고 방지** — 활성 admin 이 0 명이 되는 변경은 막는다. 이게 뚫리면
   아무도 계정을 관리할 수 없는 상태가 되고, 복구는 서버에 들어가
   `scripts/create_admin.py` 를 돌리는 것뿐이다.
2. **비활성 계정의 즉시 차단** — 로그인만 막고 토큰을 살려 두면 비활성화가
   "지금부터 못 들어온다"가 아니라 "12시간 뒤부터"가 된다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import User
from app.security import hash_password


@pytest.fixture()
def as_user(db: Session):
    def make(user: User) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


@pytest.fixture()
def anon(db: Session):
    """인증 오버라이드 없이 — 로그인 라우트를 그대로 탄다."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture()
def second_admin(db: Session) -> User:
    user = User(
        email="second-admin@fixture.local",
        password_hash="hashed",
        name="관리자2",
        role="admin",
    )
    db.add(user)
    db.flush()
    return user


class TestList:
    def test_로그인하면_누구나_본다(self, as_user, member_user, admin_user):
        res = as_user(member_user).get("/api/v1/users")
        assert res.status_code == 200
        emails = {u["email"] for u in res.json()["items"]}
        assert admin_user.email in emails

    def test_비밀번호_해시는_안_나간다(self, as_user, admin_user):
        res = as_user(admin_user).get("/api/v1/users")
        assert "password_hash" not in res.json()["items"][0]


class TestPatch:
    def test_admin_만_바꾼다(self, as_user, member_user, admin_user):
        res = as_user(member_user).patch(
            f"/api/v1/users/{admin_user.id}", json={"role": "member"}
        )
        assert res.status_code == 403

    def test_역할_변경(self, as_user, admin_user, member_user, second_admin):
        res = as_user(admin_user).patch(
            f"/api/v1/users/{member_user.id}", json={"role": "admin"}
        )
        assert res.status_code == 200
        assert res.json()["role"] == "admin"

    def test_비활성화(self, as_user, admin_user, member_user):
        res = as_user(admin_user).patch(
            f"/api/v1/users/{member_user.id}", json={"is_active": False}
        )
        assert res.status_code == 200
        assert res.json()["is_active"] is False

    def test_없는_사용자는_404(self, as_user, admin_user):
        assert (
            as_user(admin_user).patch("/api/v1/users/999999", json={"role": "member"})
        ).status_code == 404

    def test_빈_본문은_422(self, as_user, admin_user, member_user):
        res = as_user(admin_user).patch(f"/api/v1/users/{member_user.id}", json={})
        assert res.status_code == 422

    def test_모르는_역할은_422(self, as_user, admin_user, member_user):
        res = as_user(admin_user).patch(
            f"/api/v1/users/{member_user.id}", json={"role": "superuser"}
        )
        assert res.status_code == 422


@pytest.fixture()
def sole_admin(db: Session, admin_user: User) -> User:
    """admin_user 가 **유일한 활성 admin** 이 되게 만든다.

    테스트 DB 는 개발용 DB 와 같은 것이라 실제 admin 계정이 여러 개 들어 있다.
    전역 개수에 기대는 검증은 그대로 두면 남의 데이터에 따라 통과·실패가 갈린다.
    트랜잭션 안에서만 바꾸므로 테스트가 끝나면 롤백된다.
    """
    others = db.scalars(
        select(User).where(
            User.role == "admin", User.is_active.is_(True), User.id != admin_user.id
        )
    ).all()
    for u in others:
        u.is_active = False
    db.flush()
    return admin_user


class TestLastAdminGuard:
    """활성 admin 을 0 명으로 만드는 변경은 전부 409. 자기 자신인지는 상관없다."""

    def test_마지막_admin_강등은_409(self, as_user, sole_admin, admin_user, member_user):
        res = as_user(admin_user).patch(
            f"/api/v1/users/{admin_user.id}", json={"role": "member"}
        )
        assert res.status_code == 409

    def test_마지막_admin_비활성화도_409(self, as_user, sole_admin, admin_user):
        res = as_user(admin_user).patch(
            f"/api/v1/users/{admin_user.id}", json={"is_active": False}
        )
        assert res.status_code == 409

    def test_남이_마지막_admin_을_내려도_409(
        self, as_user, sole_admin, admin_user, member_user, db
    ):
        """member 는 애초에 403 이라, 두 번째 admin 이 마지막 하나를 내리는 경우."""
        other = User(
            email="temp-admin@fixture.local",
            password_hash="hashed",
            name="임시관리자",
            role="admin",
        )
        db.add(other)
        db.flush()
        # other 를 먼저 비활성화 → 활성 admin 은 admin_user 하나
        as_user(admin_user).patch(f"/api/v1/users/{other.id}", json={"is_active": False})
        res = as_user(other).patch(
            f"/api/v1/users/{admin_user.id}", json={"role": "member"}
        )
        assert res.status_code == 409

    def test_admin_이_둘이면_자기_강등도_된다(
        self, as_user, admin_user, second_admin
    ):
        res = as_user(admin_user).patch(
            f"/api/v1/users/{admin_user.id}", json={"role": "member"}
        )
        assert res.status_code == 200


class TestInactiveBlocked:
    def test_비활성_계정은_로그인_401(self, anon, db):
        user = User(
            email="inactive@fixture.local",
            password_hash=hash_password("password123"),
            name="비활성",
            role="member",
            is_active=False,
        )
        db.add(user)
        db.flush()
        res = anon.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "password123"},
        )
        assert res.status_code == 401
        assert "비활성" in res.json()["message"]

    def test_비활성_계정은_기존_토큰도_막힌다(self, anon, db):
        """로그인만 막으면 토큰 만료까지 그대로 쓴다 — 그건 차단이 아니다."""
        from app.security import create_access_token

        user = User(
            email="inactive2@fixture.local",
            password_hash=hash_password("password123"),
            name="비활성2",
            role="member",
        )
        db.add(user)
        db.flush()
        token = create_access_token(user.id, user.role)  # 활성일 때 받아 둔 토큰

        user.is_active = False
        db.flush()

        res = anon.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401


class TestPatchMe:
    """member 가 설정 화면에서 실제로 저장할 수 있는 유일한 것 (G4 결정 5)."""

    def test_이름_변경(self, as_user, member_user):
        res = as_user(member_user).patch("/api/v1/auth/me", json={"name": "새이름"})
        assert res.status_code == 200
        assert res.json()["name"] == "새이름"

    def test_현재_비밀번호_틀리면_401(self, as_user, db, member_user):
        member_user.password_hash = hash_password("password123")
        db.flush()
        res = as_user(member_user).patch(
            "/api/v1/auth/me",
            json={"current_password": "wrong", "new_password": "newpassword1"},
        )
        assert res.status_code == 401

    def test_비밀번호_변경(self, as_user, db, member_user):
        from app.security import verify_password

        member_user.password_hash = hash_password("password123")
        db.flush()
        res = as_user(member_user).patch(
            "/api/v1/auth/me",
            json={"current_password": "password123", "new_password": "newpassword1"},
        )
        assert res.status_code == 200
        assert verify_password("newpassword1", member_user.password_hash)

    def test_현재_비밀번호_없이_변경은_422(self, as_user, member_user):
        res = as_user(member_user).patch(
            "/api/v1/auth/me", json={"new_password": "newpassword1"}
        )
        assert res.status_code == 422

    def test_역할은_못_바꾼다(self, as_user, member_user):
        """스키마에 없는 필드는 무시된다 — 역할이 올라가지 않는다."""
        res = as_user(member_user).patch(
            "/api/v1/auth/me", json={"name": "x", "role": "admin"}
        )
        assert res.status_code == 200
        assert res.json()["role"] == "member"
