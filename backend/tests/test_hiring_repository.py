"""HiringRepository (Port) · 유닛 테스트 (ADR-0035 Phase 3b)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.ports.output.hiring_repository import HiringRepository


class TestHiringRepositoryContract:
    def test_abc_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            HiringRepository()  # type: ignore[abstract]

    def test_half_impl_fails(self):
        class Half(HiringRepository):
            def get_posting(self, posting_id):
                return None

        with pytest.raises(TypeError):
            Half()  # find_postings_by_ids 없음

    def test_full_impl_works(self):
        class Full(HiringRepository):
            def get_posting(self, posting_id):
                return None

            def find_postings_by_ids(self, ids):
                return []

        assert Full().get_posting(1) is None
        assert Full().find_postings_by_ids([1, 2]) == []


class TestPgHiringRepository:
    """Postgres 구현 · mock Session 으로 쿼리 호출 검증 (DB 없이)."""

    def test_get_posting_delegates_to_session_get(self):
        from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

        db = MagicMock()
        posting = MagicMock()
        posting.id = 5
        db.get.return_value = posting

        repo = PgHiringRepository(db)
        assert repo.get_posting(5) is posting
        # db.get 이 (JobPosting, 5) 로 호출됐는지
        assert db.get.call_args[0][1] == 5

    def test_find_postings_by_ids_empty_returns_empty_without_query(self):
        from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

        db = MagicMock()
        repo = PgHiringRepository(db)

        assert repo.find_postings_by_ids([]) == []
        db.scalars.assert_not_called()  # 빈 리스트면 쿼리 안 나감

    def test_find_postings_by_ids_returns_list(self):
        from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

        db = MagicMock()
        posting_a = MagicMock(id=1)
        posting_b = MagicMock(id=2)
        db.scalars.return_value = iter([posting_a, posting_b])

        repo = PgHiringRepository(db)
        result = repo.find_postings_by_ids([1, 2])

        assert result == [posting_a, posting_b]
        db.scalars.assert_called_once()
