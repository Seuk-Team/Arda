"""Application Repository · Postgres 구현 (ADR-0035 Phase 1).

`ApplicationRepository` (Port) 를 SQLAlchemy Session 으로 구현한다. 도메인 로직이
쿼리를 조립하지 않게 여기에 모은다.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application, EmailLog
from app.ports.output.application_repository import ApplicationRepository


class PgApplicationRepository(ApplicationRepository):
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, application_id: int) -> Application | None:
        return self._db.get(Application, application_id)

    def find_agent_rejected_pending_mail(self, posting_id: int) -> list[Application]:
        already = select(EmailLog.application_id).where(EmailLog.stage == "rejected")
        return list(
            self._db.scalars(
                select(Application)
                .where(Application.job_posting_id == posting_id)
                .where(Application.current_stage == "rejected")
                .where(Application.decision_source == "agent")
                .where(Application.id.not_in(already))
                .order_by(Application.id)
            )
        )
