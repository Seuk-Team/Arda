"""InterviewRepository (Port) · 유닛 테스트 (ADR-0035 Phase 3a).

DB 없이 mock 저장소로 `latest_interview_score` 경로 격리 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.interview import scoring as interview_scoring
from app.ports.output.interview_repository import InterviewRepository


class TestInterviewRepositoryContract:
    def test_abc_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            InterviewRepository()  # type: ignore[abstract]

    def test_half_impl_fails(self):
        class Half(InterviewRepository):
            def get_session(self, session_id):
                return None

        with pytest.raises(TypeError):
            Half()  # latest_ai_score_for_application 없음

    def test_full_impl_works(self):
        class Full(InterviewRepository):
            def get_session(self, session_id):
                return None

            def latest_ai_score_for_application(self, application_id):
                return None

        assert Full().latest_ai_score_for_application(1) is None


class TestLatestInterviewScoreWithMockRepo:
    def test_none_returns_none(self):
        repo = MagicMock(spec=InterviewRepository)
        repo.latest_ai_score_for_application.return_value = None
        assert interview_scoring.latest_interview_score(
            db=MagicMock(), application_id=1, interview_repo=repo
        ) is None
        repo.latest_ai_score_for_application.assert_called_once_with(1)

    def test_score_returned(self):
        repo = MagicMock(spec=InterviewRepository)
        repo.latest_ai_score_for_application.return_value = 78
        assert interview_scoring.latest_interview_score(
            db=MagicMock(), application_id=42, interview_repo=repo
        ) == 78
        repo.latest_ai_score_for_application.assert_called_once_with(42)

    def test_default_uses_pg_repository(self, monkeypatch):
        pg_instance = MagicMock(spec=InterviewRepository)
        pg_instance.latest_ai_score_for_application.return_value = None
        pg_class = MagicMock(return_value=pg_instance)
        monkeypatch.setattr(
            "app.adapter.outbound.pg.interview_pg_repository.PgInterviewRepository",
            pg_class,
        )
        db = MagicMock()
        assert interview_scoring.latest_interview_score(db=db, application_id=99) is None
        pg_class.assert_called_once_with(db)
        pg_instance.latest_ai_score_for_application.assert_called_once_with(99)
