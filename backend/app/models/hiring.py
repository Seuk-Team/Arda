"""Hiring 컨텍스트 · 채용 공고·회사·메일 템플릿.

ADR-0035 Phase 2 · models.py 분할."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.constants import (
    POSTING_STATUSES,
    SCREENING_MODES,
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
    # 자동 심사 가중치 (0016, ADR-0034). 키·기본값의 진실은
    # `app.application.screening.DEFAULT_WEIGHTS` 다 — 여기 값이 빈 객체라도
    # `screening.weights()` 가 기본값 위에 덮어쓰는 구조라 동작이 같다.
    #
    # **NOT NULL 이다** (0016 이 그렇게 만들었다). 2026-09-12 `alembic check` 에서
    # 모델만 nullable 로 적혀 있던 것을 발견해 실제 스키마에 맞췄다 — 이 칸이
    # 어긋나 있으면 테스트(create_all)는 NULL 을 받고 프로덕션(alembic)은 거부한다.
    scoring_weights: Mapped[dict] = mapped_column(
        JSON, nullable=False, server_default=text("'{}'::json")
    )
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


# ── integration_clients — 회사 통합 API key (ADR-0037) ──────────────────
class IntegrationClient(Base):
    """회사가 자기 시스템에서 Arda 로 지원자를 push 할 때 쓰는 API key.

    회사 하나에 여러 key 가능 — 시스템별 (Workday · 자체 폼 · 잡보드 어댑터)로
    나눠 발급하면 사용처를 추적하고 개별 회수할 수 있다. `revoked_at` 은 soft delete —
    감사(누가 언제 통합을 썼는지)를 위해 행은 남긴다.

    발급 시 원본 key 는 **딱 한 번** 응답으로 노출된다 (bcrypt 해시만 저장).
    관리 UI 는 `api_key_prefix` (앞 8~16자) 로만 식별한다 — 이건 노출돼도 안전.
    """

    __tablename__ = "integration_clients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("company_profile.id"), nullable=False
    )
    # bcrypt 해시. 원본 key 는 발급 순간만 응답에 실린다.
    api_key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # "arda_ak_" 접두어 + 8~16 자 · 관리 UI 표시용 (노출 안전)
    api_key_prefix: Mapped[str] = mapped_column(String(24), nullable=False)
    # "Workday integration" 등 별칭 — 관리 UI 에서 어느 시스템인지 구분
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # (선택) 상태 변경 시 회사에 콜백. HMAC-SHA256(webhook_secret) 서명
    webhook_url: Mapped[str | None] = mapped_column(String(500))
    webhook_secret: Mapped[str | None] = mapped_column(String(128))

    # Rate limit — 회사당 분당 요청 상한. 기본 60.
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("60")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # soft delete — 감사용 · 회수 후에도 행은 남긴다.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 최근 API 사용 시각 · 유휴 감시·인증 로그
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 이름을 이행 0021 과 맞춘다 (2026-09-17). 전에는 `company_id` 에 `index=True` 라
    # 모델만 `ix_integration_clients_company_id` 를 만들고, 인증 조회용 부분 인덱스는
    # 선언이 없었다 — 운영 DB 는 0021 을 따른다.
    __table_args__ = (
        Index("ix_integration_clients_company", "company_id"),
        Index(
            "ix_integration_clients_active_hash",
            "api_key_hash",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )
