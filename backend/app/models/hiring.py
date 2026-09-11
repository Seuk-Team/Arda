"""Hiring 컨텍스트 · 채용 공고·회사·메일 템플릿.

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



# ── job_postings — 채용 공고 (B1·B2) ─────────────────────────────────
class JobPosting(Base):
    __tablename__ = "job_postings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date)  # 마감일 (B4). NULL = 상시 접수
    # 공개 지원 링크 토큰 (B6). NULL = 미발급
    public_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    # 상세 필드 (0013 마이그레이션). 전부 nullable — 값이 없으면 아르가 "미공개" 로 안내.
    location: Mapped[str | None] = mapped_column(String(200))
    employment_type: Mapped[str | None] = mapped_column(String(30))
    experience_min: Mapped[int | None] = mapped_column(SmallInteger)
    experience_max: Mapped[int | None] = mapped_column(SmallInteger)
    # 급여는 만원 단위 정수. 협의는 둘 다 NULL. 상한만 NULL 이면 "최소 X 이상".
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    remote_policy: Mapped[str | None] = mapped_column(String(100))
    requirements: Mapped[str | None] = mapped_column(Text)
    preferred: Mapped[str | None] = mapped_column(Text)
    benefits: Mapped[str | None] = mapped_column(Text)

    # 자동 심사 (0016, ADR-0034). doc_score 가 이 값 이상이면 아르가 면접 단계로,
    # 미만이면 불합격으로 옮긴다. screening_mode='manual' 이면 점수만 매기고 안 옮긴다.
    pass_threshold: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("60")
    )
    screening_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'auto'")
    )

    # 기본 면접관 풀 — 자동 배정의 재료 (0016). 컬럼이 아니라 관계다.
    interviewers: Mapped[list["PostingInterviewer"]] = relationship(
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(_in("status", POSTING_STATUSES), name="ck_job_postings_status"),
        CheckConstraint(
            _in("screening_mode", SCREENING_MODES), name="ck_job_postings_screening_mode"
        ),
        CheckConstraint(
            "pass_threshold BETWEEN 0 AND 100", name="ck_job_postings_pass_threshold"
        ),
    )


# ── posting_interviewers — 공고별 기본 면접관 풀 (0016, ADR-0034) ─────
# 서류 합격이 자동으로 나면 이 풀에서 가용 시간이 있고 배정이 가장 적은 사람이
# 자동 배정된다. 수동 배정·변경은 여전히 admin(ADR-0013).
class PostingInterviewer(Base):
    __tablename__ = "posting_interviewers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("job_posting_id", "user_id", name="uq_posting_interviewers"),
    )


# ── company_profile — 회사 소개 (단일 행, 0013) ─────────────────────
# 아르 시스템 프롬프트에 회사 배경으로 붙고, 메일 {회사명} 치환의 원본이 된다.
# 다른 회사가 이 코드를 갈아 끼울 때 이 표만 채우면 대부분의 회사 관련 답변이
# 자동으로 그 회사의 것으로 바뀐다. 자세한 절 구성은 docs/06_company/00-회사-소개.md.
class CompanyProfile(Base):
    __tablename__ = "company_profile"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 빈 문자열 = "아직 정하지 않음". NULL 은 마이그레이션이 막는다.
    name: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    tagline: Mapped[str | None] = mapped_column(String(200))
    hr_email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    # 회사 전체 이야기 — 아르 프롬프트 뒤에 그대로 붙는 마크다운.
    narrative: Mapped[str | None] = mapped_column(Text)
    # 자동 심사 가중치 (0016, ADR-0034). 키·기본값은 app/screening.py DEFAULT_WEIGHTS.
    scoring_weights: Mapped[dict | None] = mapped_column(JSON)
    # 인재상 원문 — 서류·면접 채점의 "문화 적합" 재료. 회사 소개 §8 을 옮긴 것.
    talent_profile: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_company_profile_singleton"),
    )


# ── email_templates — 메일 문구 오버라이드 (G4) ──────────────────────
class EmailTemplate(Base):
    """담당자가 편집한 메일 문구. **행이 없으면 코드 기본값**(mail._TEMPLATES).

    문구를 통째로 DB 로 옮기지 않은 이유: 시드가 선행돼야 메일이 나가게 되고,
    시드 누락이 곧 발송 전면 실패다. 오버라이드만 두면 create_all 이 빈 테이블을
    만드는 것으로 끝나고, 행을 지우면 기본 문구로 돌아온다.
    """

    __tablename__ = "email_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 단계당 하나. 오버라이드가 여러 개면 "지금 어느 것이 나가는가"를 알 수 없다
    stage: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            _in("stage", TEMPLATE_STAGES), name="ck_email_templates_stage"
        ),
    )
