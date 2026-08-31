"""역할 2종화 이후의 권한 경계 (ADR-0017).

새 규칙은 세 줄로 요약된다:

1. **조회는 로그인만 하면 전부 허용** — 옛 A3(면접관은 배정된 지원자만)는 폐지됐다.
2. **admin 전용**: 면접관 배정/해제, 계정 생성, 메일 템플릿, *남의* 가용 시간.
3. **member 제한**: 평가 작성은 자기에게 배정된 건만. 그 외 조작은 admin 과 동일.

규칙이 라우터 여러 곳에 흩어져 있어 하나를 고치면 다른 곳이 조용히 어긋난다.
그래서 "무엇이 열렸는가"와 "무엇이 남았는가"를 한 파일에서 같이 본다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import Application, InterviewerAssignment, User


@pytest.fixture()
def as_user(db: Session):
    """주어진 사용자로 인증된 TestClient 를 만든다."""

    def make(user: User) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


@pytest.fixture()
def assigned_member(db: Session, application: Application, admin_user: User) -> User:
    """이 지원자의 면접관으로 배정된 멤버."""
    user = User(
        email="assigned-member@fixture.local",
        password_hash="hashed",
        name="배정된멤버",
        role="member",
    )
    db.add(user)
    db.flush()
    db.add(
        InterviewerAssignment(
            application_id=application.id,
            interviewer_id=user.id,
            assigned_by=admin_user.id,
        )
    )
    db.flush()
    return user


# ── 1. 조회는 전원 허용 (구 A3 폐지) ─────────────────────────────────


class TestViewIsOpenToEveryone:
    """배정되지 않은 멤버가 지원자 정보를 전부 볼 수 있어야 한다.

    옛 규칙에서 이 다섯 곳은 모두 403 이었다. 하나라도 403 으로 돌아오면
    A3 장치가 어딘가에 남아 있다는 뜻이다.
    """

    def test_지원자_상세(self, as_user, member_user: User, application: Application):
        res = as_user(member_user).get(f"/api/v1/applications/{application.id}")
        assert res.status_code == 200
        assert res.json()["name"] == application.name

    def test_공고별_지원자_목록(self, as_user, member_user: User, application: Application):
        res = as_user(member_user).get(
            f"/api/v1/postings/{application.job_posting_id}/applications"
        )
        assert res.status_code == 200
        assert [r["id"] for r in res.json()] == [application.id]

    def test_단계_이력(self, as_user, member_user: User, application: Application):
        res = as_user(member_user).get(f"/api/v1/applications/{application.id}/history")
        assert res.status_code == 200

    def test_평가_목록(self, as_user, member_user: User, application: Application):
        res = as_user(member_user).get(f"/api/v1/applications/{application.id}/evaluations")
        assert res.status_code == 200

    def test_배정_현황(self, as_user, member_user: User, application: Application):
        res = as_user(member_user).get(f"/api/v1/applications/{application.id}/interviewers")
        assert res.status_code == 200

    def test_검색(self, as_user, member_user: User, application: Application):
        res = as_user(member_user).get("/api/v1/applications", params={"q": application.name})
        assert res.status_code == 200
        assert application.id in [r["id"] for r in res.json()["items"]]

    def test_인증이_없으면_여전히_401(self, db: Session, application: Application):
        """열린 것은 "로그인한 사람 전체"이지 "누구나"가 아니다."""
        app.dependency_overrides[get_db] = lambda: db
        try:
            res = TestClient(app, raise_server_exceptions=False).get(
                f"/api/v1/applications/{application.id}"
            )
        finally:
            app.dependency_overrides.clear()
        assert res.status_code == 401


# ── 2. member 제한: 평가 작성은 배정된 건만 ──────────────────────────


class TestEvaluationWrite:
    def test_배정되지_않은_멤버는_평가를_쓸_수_없다(
        self, as_user, member_user: User, application: Application
    ):
        res = as_user(member_user).post(
            f"/api/v1/applications/{application.id}/evaluations",
            json={"score": 4, "comment": "좋았습니다"},
        )
        assert res.status_code == 403

    def test_배정된_멤버는_평가를_쓸_수_있다(
        self, as_user, assigned_member: User, application: Application
    ):
        res = as_user(assigned_member).post(
            f"/api/v1/applications/{application.id}/evaluations",
            json={"score": 4, "comment": "좋았습니다"},
        )
        assert res.status_code == 201
        assert res.json()["evaluator_id"] == assigned_member.id

    def test_admin_은_배정_없이도_평가를_쓸_수_있다(
        self, as_user, admin_user: User, application: Application
    ):
        res = as_user(admin_user).post(
            f"/api/v1/applications/{application.id}/evaluations",
            json={"score": 5},
        )
        assert res.status_code == 201

    def test_없는_지원자는_404가_먼저다(self, as_user, member_user: User):
        """권한 판정보다 존재 확인이 앞선다 — 없는 건에 403 을 주면 헷갈린다."""
        res = as_user(member_user).post(
            "/api/v1/applications/99999999/evaluations", json={"score": 3}
        )
        assert res.status_code == 404


# ── 3. admin 전용으로 남은 것 ────────────────────────────────────────


class TestAdminOnly:
    def test_멤버는_배정할_수_없다(
        self, as_user, member_user: User, interviewer_user: User, application: Application
    ):
        res = as_user(member_user).post(
            f"/api/v1/applications/{application.id}/interviewers",
            json={"interviewer_ids": [interviewer_user.id]},
        )
        assert res.status_code == 403

    def test_admin_은_배정할_수_있다(
        self, as_user, admin_user: User, interviewer_user: User, application: Application
    ):
        res = as_user(admin_user).post(
            f"/api/v1/applications/{application.id}/interviewers",
            json={"interviewer_ids": [interviewer_user.id]},
        )
        assert res.status_code == 200
        assert res.json()["assigned"] == [interviewer_user.id]

    def test_멤버는_배정을_해제할_수_없다(
        self, as_user, member_user: User, assigned_member: User, application: Application
    ):
        res = as_user(member_user).delete(
            f"/api/v1/applications/{application.id}/interviewers/{assigned_member.id}"
        )
        assert res.status_code == 403

    def test_멤버는_남의_가용_시간을_등록할_수_없다(
        self, as_user, member_user: User, interviewer_user: User
    ):
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        res = as_user(member_user).post(
            f"/api/v1/interviewers/{interviewer_user.id}/availability",
            json={
                "start_at": (now + timedelta(days=1)).isoformat(),
                "end_at": (now + timedelta(days=1, hours=2)).isoformat(),
            },
        )
        assert res.status_code == 403

    def test_본인_가용_시간은_멤버도_등록할_수_있다(self, as_user, member_user: User):
        """면접관 role 검사는 폐지됐다 — 본인 것은 누구나 등록한다 (ADR-0017)."""
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        res = as_user(member_user).post(
            f"/api/v1/interviewers/{member_user.id}/availability",
            json={
                "start_at": (now + timedelta(days=1)).isoformat(),
                "end_at": (now + timedelta(days=1, hours=2)).isoformat(),
            },
        )
        assert res.status_code == 201


# ── 4. member 도 할 수 있는 조작 (admin 과 동일) ──────────────────────


class TestMemberCanOperate:
    """옛 규칙에서 recruiter+ 였던 것들. 이제 member 도 같다 (ADR-0017)."""

    def test_공고를_만들_수_있다(self, as_user, member_user: User):
        res = as_user(member_user).post(
            "/api/v1/postings", json={"title": "프론트엔드 개발자", "status": "draft"}
        )
        assert res.status_code == 201

    def test_단계를_바꿀_수_있다(self, as_user, member_user: User, application: Application):
        res = as_user(member_user).patch(
            f"/api/v1/applications/{application.id}/stage", json={"to_stage": "screening"}
        )
        assert res.status_code == 200

    def test_메모를_쓸_수_있다(self, as_user, member_user: User, application: Application):
        res = as_user(member_user).post(
            f"/api/v1/applications/{application.id}/notes", json={"body": "전화 통화함"}
        )
        assert res.status_code == 201
