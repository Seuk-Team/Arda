"""지원 현황 조회 — 지원자용 (신-1 지원자 포털).

여기서 보는 것은 **지원 사실이 새어 나가지 않는가**다. 조회 링크 요청은 없는
주소로도 같은 답을 해야 하고, 링크로 여는 화면에는 담당자 쪽 정보가 없어야 한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app
from app.models import Application, EmailLog


@pytest.fixture()
def public(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture()
def submitted(db: Session, application: Application) -> Application:
    """메일 큐는 건드리지 않는다 — SQS 가 없는 CI 에서도 돌아야 한다."""
    db.commit()
    return application


class TestLookup:
    def test_링크를_보내면_토큰이_생긴다(self, public, db: Session, submitted):
        with patch("app.mail.publish") as pub:
            res = public.post(
                "/api/v1/public/applications/lookup", json={"email": submitted.email}
            )
        assert res.status_code == 202
        pub.assert_called_once()

        db.refresh(submitted)
        assert submitted.portal_token
        assert submitted.portal_token_expires_at > datetime.now(UTC)

    def test_없는_주소도_같은_응답이다(self, public, db: Session, submitted):
        """다르게 답하면 그것만으로 '이 사람이 여기 지원했는가' 확인 도구가 된다."""
        with patch("app.mail.publish") as pub:
            found = public.post(
                "/api/v1/public/applications/lookup", json={"email": submitted.email}
            )
            missing = public.post(
                "/api/v1/public/applications/lookup",
                json={"email": "nobody@nowhere.invalid"},
            )

        assert found.status_code == missing.status_code == 202
        assert found.json() == missing.json()  # 본문까지 같아야 한다
        assert pub.call_count == 1  # 없는 주소로는 메일이 안 나간다

    def test_대소문자가_달라도_찾는다(self, public, db: Session, submitted):
        with patch("app.mail.publish"):
            public.post(
                "/api/v1/public/applications/lookup",
                json={"email": submitted.email.upper()},
            )
        db.refresh(submitted)
        assert submitted.portal_token

    def test_다시_요청하면_지난_링크는_죽는다(self, public, db: Session, submitted):
        with patch("app.mail.publish"):
            public.post(
                "/api/v1/public/applications/lookup", json={"email": submitted.email}
            )
        db.refresh(submitted)
        first = submitted.portal_token

        with patch("app.mail.publish"):
            public.post(
                "/api/v1/public/applications/lookup", json={"email": submitted.email}
            )
        db.refresh(submitted)
        assert submitted.portal_token != first
        assert public.get(f"/api/v1/public/applications/status/{first}").status_code == 404

    def test_큐가_죽어도_토큰은_남는다(self, public, db: Session, submitted):
        """메일은 못 보내도 링크는 이미 만들어져 있다 — 다시 요청하면 된다."""
        with patch("app.mail.publish", side_effect=RuntimeError("SQS 죽음")):
            res = public.post(
                "/api/v1/public/applications/lookup", json={"email": submitted.email}
            )
        assert res.status_code == 202
        db.refresh(submitted)
        assert submitted.portal_token

    def test_메일_본문에_링크가_들어간다(self, public, db: Session, submitted):
        with patch("app.mail.publish"):
            public.post(
                "/api/v1/public/applications/lookup", json={"email": submitted.email}
            )
        db.refresh(submitted)
        log = db.scalar(
            select(EmailLog).where(EmailLog.application_id == submitted.id)
        )
        assert log is not None
        assert submitted.portal_token in log.body
        assert log.to_email == submitted.email


class TestStatus:
    @pytest.fixture()
    def linked(self, public, db: Session, submitted) -> Application:
        with patch("app.mail.publish"):
            public.post(
                "/api/v1/public/applications/lookup", json={"email": submitted.email}
            )
        db.refresh(submitted)
        return submitted

    def test_현황을_보여준다(self, public, linked):
        res = public.get(f"/api/v1/public/applications/status/{linked.portal_token}")
        assert res.status_code == 200
        body = res.json()
        assert body["applicant_name"] == linked.name
        assert body["stage_label"] == "접수 완료"  # applied

    def test_담당자_정보를_내려주지_않는다(self, public, linked):
        """평가·메모·불합격 사유는 지원자에게 갈 값이 아니다."""
        body = public.get(
            f"/api/v1/public/applications/status/{linked.portal_token}"
        ).json()
        assert set(body) == {
            "applicant_name",
            "posting_title",
            "stage_label",
            "submitted_at",
        }

    def test_불합격을_그대로_말하지_않는다(self, public, db: Session, linked):
        """담당자가 통보하기 전에 화면이 먼저 말하면 안 된다."""
        linked.current_stage = "rejected"
        db.commit()
        body = public.get(
            f"/api/v1/public/applications/status/{linked.portal_token}"
        ).json()
        assert body["stage_label"] == "전형 종료"
        assert "불합격" not in body["stage_label"]

    def test_없는_토큰은_404(self, public):
        assert public.get("/api/v1/public/applications/status/없는토큰").status_code == 404

    def test_기한이_지나면_410(self, public, db: Session, linked):
        """404 면 '그런 지원이 없다'로 읽혀서 지원자가 오해한다."""
        linked.portal_token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        res = public.get(f"/api/v1/public/applications/status/{linked.portal_token}")
        assert res.status_code == 410
