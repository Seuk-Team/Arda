"""TalentRepository (Port) · 유닛 테스트 (ADR-0035 Phase 3c)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.ports.output.talent_repository import TalentRepository


class TestTalentRepositoryContract:
    def test_abc_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            TalentRepository()  # type: ignore[abstract]

    def test_half_impl_fails(self):
        class Half(TalentRepository):
            def get_user(self, user_id):
                return None

        with pytest.raises(TypeError):
            Half()  # find_users_by_ids 없음

    def test_full_impl_works(self):
        class Full(TalentRepository):
            def get_user(self, user_id):
                return None

            def find_users_by_ids(self, ids):
                return []

        assert Full().get_user(1) is None
        assert Full().find_users_by_ids([1, 2]) == []


class TestPgTalentRepository:
    def test_get_user_delegates_to_session(self):
        from app.adapter.outbound.pg.talent_pg_repository import PgTalentRepository

        db = MagicMock()
        user = MagicMock(id=5)
        db.get.return_value = user

        repo = PgTalentRepository(db)
        assert repo.get_user(5) is user
        assert db.get.call_args[0][1] == 5

    def test_find_users_by_ids_empty_short_circuits(self):
        from app.adapter.outbound.pg.talent_pg_repository import PgTalentRepository

        db = MagicMock()
        assert PgTalentRepository(db).find_users_by_ids([]) == []
        db.scalars.assert_not_called()

    def test_find_users_by_ids_returns_list(self):
        from app.adapter.outbound.pg.talent_pg_repository import PgTalentRepository

        db = MagicMock()
        u1, u2 = MagicMock(id=1), MagicMock(id=2)
        db.scalars.return_value = iter([u1, u2])

        result = PgTalentRepository(db).find_users_by_ids([1, 2])
        assert result == [u1, u2]
        db.scalars.assert_called_once()
