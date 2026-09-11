"""Interview Repository · Postgres 구현 (ADR-0035 Phase 3a)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InterviewSession
from app.ports.output.interview_repository import InterviewRepository


class PgInterviewRepository(InterviewRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_session(self, session_id: int) -> InterviewSession | None:
        return self._db.get(InterviewSession, session_id)

    def latest_ai_score_for_application(self, application_id: int) -> int | None:
        return self._db.scalar(
            select(InterviewSession.ai_score)
            .where(InterviewSession.application_id == application_id)
            .where(InterviewSession.status == "done")
            .where(InterviewSession.ai_score.is_not(None))
            .order_by(
                InterviewSession.ended_at.desc().nulls_last(),
                InterviewSession.id.desc(),
            )
            .limit(1)
        )
