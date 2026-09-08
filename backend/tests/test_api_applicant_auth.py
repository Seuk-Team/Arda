"""지원자 앱 로그인 (ADR-0031) — 이메일 + 생년월일 8자리.

**틀렸을 때 남의 지원서가 열린다.** 그래서 규칙 하나에 테스트 하나를 붙인다.
특히 아래 넷은 무너져도 화면상 아무 일이 없어 보여서 제일 위험하다.

- **지원자 토큰이 직원 경로를 못 탄다.** 같은 키로 서명하므로 서명 검증은
  이걸 막지 못한다 — 토큰 종류(`typ`)만이 구분선이다
- **직원 토큰도 지원자 경로를 못 탄다.** 반대 방향도 막혀야 한다
- **없는 이메일과 틀린 생년월일이 같은 응답이다.** 다르면 "이 사람이 여기
  지원했는가"를 확인하는 도구가 된다
- **생년월일이 없는 옛 지원서는 로그인이 안 된다.** 빈 값끼리 맞아떨어지면 안 된다

나머지(잠금·여러 지원·단계 문구)는 흐름이 도는지를 본다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import applicant_auth
from app.db import get_db
from app.main import app
from app.models import Application, User
from app.security import create_access_token, create_applicant_token

LOGIN = "/api/v1/public/applicant/login"
ME = "/api/v1/applicant/me"


@pytest.fixture()
def client(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear_lock():
    """실패 횟수는 프로세스 메모리에 산다 — 테스트끼리 새게 두지 않는다."""
    applicant_auth._FAILS.clear()
    yield
    applicant_auth._FAILS.clear()


def _applicant(db: Session, application: Application, **kw) -> Application:
    """기존 지원서에 생년월일을 붙인다."""
    application.birth_date = kw.pop("birth_date", date(1998, 4, 12))
    for k, v in kw.items():
        setattr(application, k, v)
    db.flush()
    return application


class TestLogin:
    def test_이메일과_생년월일이_맞으면_토큰이_나온다(
        self, client, db: Session, application: Application
    ):
        a = _applicant(db, application)
        res = client.post(LOGIN, json={"email": a.email, "birth_date": "19980412"})

        assert res.status_code == 200
        body = res.json()
        assert body["access_token"]
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    def test_대소문자와_공백은_무시한다(
        self, client, db: Session, application: Application
    ):
        a = _applicant(db, application, email="Kwak@Example.com")
        # 지원 폼과 앱에서 같은 사람이 다르게 칠 수 있다
        a.email = "kwak@example.com"
        db.flush()
        res = client.post(LOGIN, json={"email": "  KWAK@Example.COM ", "birth_date": "19980412"})
        assert res.status_code == 200

    def test_틀린_생년월일과_없는_이메일이_같은_응답이다(
        self, client, db: Session, application: Application
    ):
        """**이게 갈리면 지원 사실 자체가 새어 나간다.**"""
        a = _applicant(db, application)
        wrong_birth = client.post(LOGIN, json={"email": a.email, "birth_date": "19990101"})
        no_such = client.post(LOGIN, json={"email": "nobody@example.com", "birth_date": "19980412"})

        assert wrong_birth.status_code == no_such.status_code == 401
        # `request_id` 는 요청마다 다른 값이라 비교에서 뺀다 — 유출이 아니다.
        strip = lambda r: {k: v for k, v in r.json().items() if k != "request_id"}  # noqa: E731
        assert strip(wrong_birth) == strip(no_such)

    def test_형식이_틀려도_422가_아니라_401이다(
        self, client, db: Session, application: Application
    ):
        """422 는 '형식은 맞다'는 신호가 되어 떠보는 데 쓰인다."""
        _applicant(db, application)
        res = client.post(LOGIN, json={"email": application.email, "birth_date": "98/04/12"})
        assert res.status_code == 401

    def test_생년월일이_없는_옛_지원서는_못_들어온다(
        self, client, db: Session, application: Application
    ):
        application.birth_date = None
        db.flush()
        res = client.post(LOGIN, json={"email": application.email, "birth_date": "19980412"})
        assert res.status_code == 401

    def test_다섯_번_틀리면_잠긴다(self, client, db: Session, application: Application):
        a = _applicant(db, application)
        for _ in range(applicant_auth.MAX_ATTEMPTS):
            assert client.post(LOGIN, json={"email": a.email, "birth_date": "19000101"}).status_code == 401

        # 잠긴 뒤에는 **맞는 값을 넣어도** 막힌다 — 그래야 시도 상한이 의미가 있다
        res = client.post(LOGIN, json={"email": a.email, "birth_date": "19980412"})
        assert res.status_code == 429

    def test_성공하면_실패_횟수가_지워진다(
        self, client, db: Session, application: Application
    ):
        a = _applicant(db, application)
        client.post(LOGIN, json={"email": a.email, "birth_date": "19000101"})
        assert client.post(LOGIN, json={"email": a.email, "birth_date": "19980412"}).status_code == 200
        assert a.email not in applicant_auth._FAILS


class TestTokenBoundary:
    """**같은 비밀키로 서명한다.** 토큰 종류만이 두 세계를 가른다."""

    def test_지원자_토큰으로_직원_경로를_못_탄다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        _applicant(db, application)
        token = create_applicant_token(application.email)
        res = client.get("/api/v1/applications", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401

    def test_sub_가_숫자여도_직원이_되지_않는다(
        self, client, db: Session, application: Application, admin_user: User
    ):
        """예전 `get_current_user` 는 sub 로 User 를 찾기만 했다 — 지원자 토큰의
        sub 가 어떤 User 의 id 와 같기만 해도 그 사람이 됐다."""
        token = create_applicant_token(str(admin_user.id))
        res = client.get("/api/v1/applications", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401

    def test_직원_토큰으로_지원자_경로를_못_탄다(
        self, client, db: Session, admin_user: User
    ):
        token = create_access_token(admin_user.id, admin_user.role)
        res = client.get(ME, headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401


class TestMe:
    def test_내_지원만_보인다(
        self, client, db: Session, application: Application
    ):
        a = _applicant(db, application)
        token = create_applicant_token(a.email)
        res = client.get(ME, headers={"Authorization": f"Bearer {token}"})

        assert res.status_code == 200
        body = res.json()
        assert body["email"] == a.email
        assert [x["id"] for x in body["applications"]] == [a.id]

    def test_평가나_담당자_정보가_없다(
        self, client, db: Session, application: Application
    ):
        a = _applicant(db, application)
        token = create_applicant_token(a.email)
        body = client.get(ME, headers={"Authorization": f"Bearer {token}"}).json()

        allowed = {"id", "posting_title", "stage_label", "applied_at"}
        assert set(body["applications"][0]) == allowed
        assert "ai_summary" not in body

    def test_불합격을_앱이_먼저_말하지_않는다(
        self, client, db: Session, application: Application
    ):
        """담당자가 통보하기 전에 화면이 앞질러 말하면 안 된다 (portal 과 같은 규칙)."""
        a = _applicant(db, application)
        a.current_stage = "rejected"
        db.flush()
        token = create_applicant_token(a.email)
        body = client.get(ME, headers={"Authorization": f"Bearer {token}"}).json()

        label = body["applications"][0]["stage_label"]
        assert label == "전형 종료"
        assert "불합격" not in label

    def test_토큰이_없으면_401(self, client):
        assert client.get(ME).status_code == 401

    def test_만료된_토큰은_거부한다(self, client, db: Session, application: Application):
        import jwt

        from app.security import JWT_ALGORITHM, JWT_SECRET, TYP_APPLICANT

        expired = jwt.encode(
            {
                "sub": application.email,
                "typ": TYP_APPLICANT,
                "exp": datetime.now(UTC) - timedelta(minutes=1),
            },
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
        res = client.get(ME, headers={"Authorization": f"Bearer {expired}"})
        assert res.status_code == 401
