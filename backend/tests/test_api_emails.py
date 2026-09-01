"""메일 문구 편집·수동 발송 API (G4).

문구 편집은 **되돌릴 수 없는 발송에 직접 얹히는 입력**이다. 저장 시점 검증이
지원자에게 깨진 메일이 나가는 것을 막는 유일한 지점이라 그쪽에 무게를 둔다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.db import get_db
from app.deps import get_current_user
from app.main import app
from app.models import EmailLog, EmailTemplate, User


@pytest.fixture()
def as_user(db: Session, monkeypatch):
    # 실제 SQS 를 부르지 않는다. 발송 경로의 관심사는 "행이 남는가"다.
    monkeypatch.setattr(mail, "publish", lambda _id: None)

    def make(user: User) -> TestClient:
        app.dependency_overrides[get_db] = lambda: db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app, raise_server_exceptions=False)

    yield make
    app.dependency_overrides.clear()


class TestTemplateRead:
    def test_기본값이_나온다(self, as_user, member_user):
        res = as_user(member_user).get("/api/v1/email-templates")
        assert res.status_code == 200
        items = {t["stage"]: t for t in res.json()["items"]}
        assert set(items) == {"applied", "interview", "accepted", "rejected"}
        assert items["interview"]["source"] == "default"

    def test_screening_은_목록에_없다(self, as_user, member_user):
        """내부 검토 단계라 지원자에게 보내는 문구가 없다."""
        res = as_user(member_user).get("/api/v1/email-templates")
        assert "screening" not in {t["stage"] for t in res.json()["items"]}


class TestTemplateSave:
    def test_저장하면_source_가_custom(self, as_user, admin_user):
        res = as_user(admin_user).put(
            "/api/v1/email-templates/interview",
            json={"subject": "[{회사명}] 면접 안내", "body": "{지원자명} 님\n\n{서명}"},
        )
        assert res.status_code == 200
        assert res.json()["source"] == "custom"
        assert res.json()["updated_by_name"] == admin_user.name

    def test_member_는_403(self, as_user, member_user):
        res = as_user(member_user).put(
            "/api/v1/email-templates/interview",
            json={"subject": "x", "body": "y"},
        )
        assert res.status_code == 403

    def test_모르는_변수는_422(self, as_user, admin_user):
        res = as_user(admin_user).put(
            "/api/v1/email-templates/interview",
            json={"subject": "제목", "body": "{지원자명} 님, {면접장소} 로 오세요"},
        )
        assert res.status_code == 422
        assert "{면접장소}" in res.json()["message"]

    def test_오타난_변수도_422(self, as_user, admin_user):
        res = as_user(admin_user).put(
            "/api/v1/email-templates/interview",
            json={"subject": "제목", "body": "{지원자 명} 님"},
        )
        assert res.status_code == 422

    def test_서명이_없으면_자동으로_붙는다(self, as_user, admin_user, db):
        as_user(admin_user).put(
            "/api/v1/email-templates/rejected",
            json={"subject": "결과 안내", "body": "{지원자명} 님, 아쉽습니다."},
        )
        row = db.scalar(
            select(EmailTemplate).where(EmailTemplate.stage == "rejected")
        )
        assert row.body.endswith("{서명}")

    def test_편집할_문구가_없는_단계는_404(self, as_user, admin_user):
        res = as_user(admin_user).put(
            "/api/v1/email-templates/screening", json={"subject": "x", "body": "y"}
        )
        assert res.status_code == 404


class TestTemplateReset:
    def test_삭제하면_기본값으로_돌아온다(self, as_user, admin_user):
        client = as_user(admin_user)
        client.put(
            "/api/v1/email-templates/applied",
            json={"subject": "바뀐 제목", "body": "바뀐 본문 {서명}"},
        )
        res = client.delete("/api/v1/email-templates/applied")
        assert res.status_code == 200
        assert res.json()["source"] == "default"
        assert res.json()["subject"] != "바뀐 제목"

    def test_수정본이_없으면_404(self, as_user, admin_user):
        res = as_user(admin_user).delete("/api/v1/email-templates/accepted")
        assert res.status_code == 404

    def test_member_는_403(self, as_user, member_user):
        res = as_user(member_user).delete("/api/v1/email-templates/applied")
        assert res.status_code == 403


class TestPreview:
    def test_변수가_채워져_나온다(self, as_user, admin_user, application):
        res = as_user(admin_user).get(
            f"/api/v1/applications/{application.id}/emails/preview?stage=interview"
        )
        assert res.status_code == 200
        body = res.json()["body"]
        assert application.name in body
        assert "{지원자명}" not in body
        assert f"채용 담당자 {admin_user.name} 드림" in body


class TestManualSend:
    def test_행이_남고_수신자는_지원자_주소다(
        self, as_user, member_user, application, db
    ):
        res = as_user(member_user).post(
            f"/api/v1/applications/{application.id}/emails",
            json={"subject": "안내드립니다", "body": "본문입니다\n\n{서명}"},
        )
        assert res.status_code == 201
        log = db.get(EmailLog, res.json()["id"])
        assert log.to_email == application.email  # 본문·요청 어디에도 주소가 없다
        assert log.stage == "custom"
        assert log.actor_kind == "human"
        assert log.actor_id == member_user.id
        assert log.body.endswith(f"채용 담당자 {member_user.name} 드림")

    def test_없는_지원자는_404(self, as_user, member_user):
        res = as_user(member_user).post(
            "/api/v1/applications/999999/emails",
            json={"subject": "x", "body": "y"},
        )
        assert res.status_code == 404

    def test_빈_본문은_422(self, as_user, member_user, application):
        res = as_user(member_user).post(
            f"/api/v1/applications/{application.id}/emails",
            json={"subject": "제목", "body": ""},
        )
        assert res.status_code == 422

    def test_큐_발행이_실패해도_201(
        self, as_user, member_user, application, monkeypatch
    ):
        """행은 이미 커밋됐다 — 메일이 늦는 것이 발송 기록을 잃는 것보다 낫다."""

        def boom(_id):
            raise RuntimeError("큐 죽음")

        monkeypatch.setattr(mail, "publish", boom)
        res = as_user(member_user).post(
            f"/api/v1/applications/{application.id}/emails",
            json={"subject": "제목", "body": "본문"},
        )
        assert res.status_code == 201


class TestHistory:
    def test_자동_수동이_한_목록에_나온다(
        self, as_user, admin_user, application, db
    ):
        mail.create_log(
            db,
            application_id=application.id,
            to_email=application.email,
            stage="applied",
        )
        client = as_user(admin_user)
        client.post(
            f"/api/v1/applications/{application.id}/emails",
            json={"subject": "수동", "body": "수동 본문"},
        )
        res = client.get(f"/api/v1/applications/{application.id}/emails")
        assert res.status_code == 200
        stages = [i["stage"] for i in res.json()["items"]]
        assert "applied" in stages and "custom" in stages

    def test_주체_이름이_붙는다(self, as_user, admin_user, application):
        client = as_user(admin_user)
        client.post(
            f"/api/v1/applications/{application.id}/emails",
            json={"subject": "수동", "body": "수동 본문"},
        )
        res = client.get(f"/api/v1/applications/{application.id}/emails")
        assert res.json()["items"][0]["actor_name"] == admin_user.name
