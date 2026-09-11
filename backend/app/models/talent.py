"""Talent 컨텍스트 · 내부 사용자 (직원).

ADR-0035 Phase 2 · models.py 분할."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DDL,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.constants import (
    APPLICATION_SOURCES,
    DECISION_SOURCES,
    DOC_DECISIONS,
    DOC_TYPES,
    EMAIL_ACTOR_KINDS,
    EMAIL_LOG_STAGES,
    EMAIL_STATUSES,
    FILE_KINDS,
    POSTING_STATUSES,
    PROPOSAL_STATUSES,
    PUBLICATION_STATUSES,
    ROLES,
    SCREENING_MODES,
    STAGES,
    TEMPLATE_STAGES,
    _in,
)

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None



# ── users — 내부 사용자 (A1·A2) ──────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # 비활성 계정은 로그인도 토큰 사용도 막힌다 (A4). 삭제 대신 이것을 쓴다 —
    # users.id 가 created_by·evaluator_id·assigned_by·changed_by 로 도처에 박혀
    # 있어서 물리 삭제는 이력을 부순다.
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_users_role"),)
