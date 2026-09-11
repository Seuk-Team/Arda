"""Talent Repository · Postgres 구현 (ADR-0035 Phase 3c)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.ports.output.talent_repository import TalentRepository


class PgTalentRepository(TalentRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_user(self, user_id: int) -> User | None:
        return self._db.get(User, user_id)

    def find_users_by_ids(self, ids: Iterable[int]) -> list[User]:
        id_list = list(ids)
        if not id_list:
            return []
        return list(
            self._db.scalars(select(User).where(User.id.in_(id_list)))
        )
