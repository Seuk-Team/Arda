"""Hiring Repository · Postgres 구현 (ADR-0035 Phase 3b)."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobPosting
from app.ports.output.hiring_repository import HiringRepository


class PgHiringRepository(HiringRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_posting(self, posting_id: int) -> JobPosting | None:
        return self._db.get(JobPosting, posting_id)

    def find_postings_by_ids(self, ids: Iterable[int]) -> list[JobPosting]:
        id_list = list(ids)
        if not id_list:
            return []
        return list(
            self._db.scalars(select(JobPosting).where(JobPosting.id.in_(id_list)))
        )
