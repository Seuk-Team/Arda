"""ApplicationRepository (Port) · Repository 패턴 계약 · 유닛 테스트 (ADR-0035 §5).

이 테스트는 **DB 없이** 돈다. Repository 를 mock 으로 갈아치우고, 도메인 로직이
저장소 계약만 알면 된다는 것을 증명한다. `test_screening.py::TestSendPendingRejections`
는 통합 테스트로 DB 를 켜고, 이 파일은 그것과 짝을 이루는 단위 격리 테스트다.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.application import screening
from app.models import Application
from app.ports.output.application_repository import ApplicationRepository


def _fake_app(app_id: int, email: str) -> Application:
    """DB 없이 만드는 Application. commit 하지 않으므로 관계는 안 붙는다."""
    a = Application(
        job_posting_id=1,
        name=f"지원자{app_id}",
        email=email,
        phone="010",
        privacy_agreed_at=datetime.now(timezone.utc),
        current_stage="rejected",
        decision_source="agent",
    )
    a.id = app_id
    return a


class TestRepositoryContract:
    """ABC 계약 자체 검증."""

    def test_abc_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            ApplicationRepository()  # type: ignore[abstract]

    def test_concrete_impl_must_provide_all_methods(self):
        class Half(ApplicationRepository):
            def get(self, application_id):
                return None

        with pytest.raises(TypeError):
            Half()  # find_agent_rejected_pending_mail 없음

    def test_full_impl_works(self):
        class Full(ApplicationRepository):
            def get(self, application_id):
                return None

            def find_agent_rejected_pending_mail(self, posting_id):
                return []

        assert Full().find_agent_rejected_pending_mail(1) == []


class TestSendPendingRejectionsWithMockRepo:
    """`send_pending_rejections` 가 Repository 만 알고 SQL 을 직접 만지지 않음을 증명.

    통합 테스트(DB 켜기) 없이 이 경로의 행동을 검증할 수 있다는 것이 Repository 패턴의
    첫 번째 이득이다.
    """

    def test_empty_result_returns_zero_and_no_commit_writes(self, monkeypatch):
        """대상 0건이면 log 도 0건, 리턴도 0."""
        db = MagicMock()
        db.commit = MagicMock()

        repo = MagicMock(spec=ApplicationRepository)
        repo.find_agent_rejected_pending_mail.return_value = []

        # mail.create_log 이 호출되면 실패 (없어야 함)
        create_log = MagicMock()
        monkeypatch.setattr(screening.mail, "create_log", create_log)
        monkeypatch.setattr(screening, "publish_all", MagicMock())

        result = screening.send_pending_rejections(db, posting_id=42, application_repo=repo)

        assert result == 0
        repo.find_agent_rejected_pending_mail.assert_called_once_with(42)
        create_log.assert_not_called()

    def test_two_rows_creates_two_logs(self, monkeypatch):
        """대상 2건이면 mail.create_log 가 각각 한 번씩 · publish_all 은 그 id 들로 한 번."""
        db = MagicMock()
        repo = MagicMock(spec=ApplicationRepository)
        repo.find_agent_rejected_pending_mail.return_value = [
            _fake_app(101, "a@ex.com"),
            _fake_app(102, "b@ex.com"),
        ]

        # create_log 는 id 가 붙은 mock 을 돌려준다
        def fake_create_log(db, *, application_id, to_email, stage, actor_kind, actor_id):
            log = MagicMock()
            log.id = application_id * 10  # 임의 규칙
            return log

        create_log = MagicMock(side_effect=fake_create_log)
        publish_all = MagicMock()
        monkeypatch.setattr(screening.mail, "create_log", create_log)
        monkeypatch.setattr(screening, "publish_all", publish_all)

        result = screening.send_pending_rejections(db, posting_id=42, application_repo=repo)

        assert result == 2
        assert create_log.call_count == 2
        # id·이메일·stage·actor 모두 저장소가 준 값 그대로 전달됐는지
        call_args = [c.kwargs for c in create_log.call_args_list]
        assert {c["application_id"] for c in call_args} == {101, 102}
        assert {c["to_email"] for c in call_args} == {"a@ex.com", "b@ex.com"}
        assert all(c["stage"] == "rejected" for c in call_args)
        assert all(c["actor_kind"] == "agent" for c in call_args)
        assert all(c["actor_id"] is None for c in call_args)
        publish_all.assert_called_once_with([1010, 1020])

    def test_default_uses_pg_repository(self, monkeypatch):
        """`application_repo` 를 넣지 않으면 Pg 구현으로 폴백."""
        db = MagicMock()

        # Pg 구현의 생성자만 가로챈다 — 내부 쿼리는 mock 으로.
        pg_instance = MagicMock(spec=ApplicationRepository)
        pg_instance.find_agent_rejected_pending_mail.return_value = []
        pg_class = MagicMock(return_value=pg_instance)
        monkeypatch.setattr(
            "app.adapter.outbound.pg.application_pg_repository.PgApplicationRepository",
            pg_class,
        )
        monkeypatch.setattr(screening.mail, "create_log", MagicMock())
        monkeypatch.setattr(screening, "publish_all", MagicMock())

        result = screening.send_pending_rejections(db, posting_id=99)

        assert result == 0
        pg_class.assert_called_once_with(db)
        pg_instance.find_agent_rejected_pending_mail.assert_called_once_with(99)
