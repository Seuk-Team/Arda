"""테이블 정의 — docs/01-erd.md 를 그대로 옮긴 것.

문서와 이 파일이 어긋나면 **문서가 기준**이다. 컬럼을 여기서 임의로 추가하지 않는다.
표 순서도 문서와 같게 유지해 나란히 놓고 대조할 수 있게 한다.

단계·역할 같은 고정값은 DB enum 이 아니라 **체크 제약 + 아래 상수**로 관리한다
(01-erd.md "단계(stage) — 고정 enum" 참고. 값이 늘어도 마이그레이션이 필요 없다).
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None

# ── 고정값 (코드 상수) ────────────────────────────────────────────────
STAGES = ("applied", "screening", "interview", "accepted", "rejected")
ROLES = ("admin", "member")
POSTING_STATUSES = ("draft", "open", "closed")
APPLICATION_SOURCES = ("form", "manual")
FILE_KINDS = ("resume", "cover_letter")
EMAIL_STATUSES = ("queued", "sent", "failed")
PROPOSAL_STATUSES = ("proposed", "confirmed", "expired", "canceled")


def _in(column: str, values: tuple[str, ...]) -> str:
    """체크 제약 문구를 만든다. 예: role IN ('admin', 'member')"""
    joined = ", ".join("'" + v + "'" for v in values)
    return column + " IN (" + joined + ")"


# ── users — 내부 사용자 (A1·A2) ──────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_users_role"),)


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

    __table_args__ = (
        CheckConstraint(_in("status", POSTING_STATUSES), name="ck_job_postings_status"),
    )


# ── applications — 지원서 (C1·D1·D6) ★핵심 테이블 ────────────────────
class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job_postings.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    education: Mapped[str | None] = mapped_column(String(100))
    career_years: Mapped[int | None] = mapped_column(SmallInteger)
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    self_intro: Mapped[str | None] = mapped_column(Text)

    # AI 요약: 접수 시 1회 생성해 저장한다. 패널을 열 때마다 생성하지 않는다.
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_summary_model: Mapped[str | None] = mapped_column(String(200))

    current_stage: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'applied'")
    )
    privacy_agreed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'form'")
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

    # ORM 관계 — 컬럼이 아니다. 스키마(01-erd.md)는 그대로이고 마이그레이션도 없다.
    # 상세 조회(D1·D4)의 selectinload 용. 자식 → 부모 방향은 필요해질 때 추가한다.
    stage_history: Mapped[list["StageHistory"]] = relationship(
        order_by="StageHistory.created_at.desc()"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship()
    notes: Mapped[list["ApplicationNote"]] = relationship(
        order_by="ApplicationNote.created_at.desc()"
    )
    files: Mapped[list["File"]] = relationship()

    __table_args__ = (
        # 중복 지원 방지 (C6)
        UniqueConstraint("job_posting_id", "email", name="uq_applications_posting_email"),
        CheckConstraint(_in("current_stage", STAGES), name="ck_applications_stage"),
        CheckConstraint(_in("source", APPLICATION_SOURCES), name="ck_applications_source"),
        # 칸반·단계 필터 (H2)
        Index("ix_applications_posting_stage", "job_posting_id", "current_stage"),
        # 최신순 목록·커서 페이지네이션 (H4·H5) — 측정 근거: docs/perf-search.md (#68)
        Index("ix_applications_created_id", text("created_at DESC"), text("id DESC")),
    )


# ── stage_history — 단계 변경 이력 (D5) ──────────────────────────────
class StageHistory(Base):
    __tablename__ = "stage_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    from_stage: Mapped[str | None] = mapped_column(String(20))  # 최초 접수 시 NULL
    to_stage: Mapped[str] = mapped_column(String(20), nullable=False)
    # NULL = 시스템(외부 지원 접수)
    changed_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"))
    reason: Mapped[str | None] = mapped_column(Text)  # 불합격 사유 (D8). rejected 진입 시 기록
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(_in("to_stage", STAGES), name="ck_stage_history_to_stage"),
    )


# ── evaluations — 평가 (E1·E2) ───────────────────────────────────────
class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    evaluator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (CheckConstraint("score BETWEEN 1 AND 5", name="ck_evaluations_score"),)


# ── application_notes — 담당자 메모 (기능 번호 미지정) ────────────────
class ApplicationNote(Base):
    """평가와 분리한다. 평가는 점수가 필수라 점수 없는 기록이 섞이면 평균이 오염된다.

    각자 자기 행을 추가하는 구조라 동시 편집 충돌 처리가 필요 없다 (ADR-0005).
    """

    __tablename__ = "application_notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    author_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
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
        # 상세 패널 최신순 표시
        Index(
            "ix_application_notes_app_created",
            "application_id",
            text("created_at DESC"),
        ),
    )


# ── files — 이력서 파일 (F1·F2) ──────────────────────────────────────
class File(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    s3_key: Mapped[str] = mapped_column(String(500), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)  # 원본 파일명
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (CheckConstraint(_in("kind", FILE_KINDS), name="ck_files_kind"),)


# ── email_logs — 메일 발송 (G1~G3) ───────────────────────────────────
class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    to_email: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'queued'")
    )
    retry_count: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("0")
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(_in("status", EMAIL_STATUSES), name="ck_email_logs_status"),
        CheckConstraint(_in("stage", STAGES), name="ck_email_logs_stage"),
    )


# ── interviewer_assignments — 면접관 배정 (E3) ───────────────────────
class InterviewerAssignment(Base):
    """"이 지원자의 면접관은 누구인가"를 담는 관계 테이블.

    조회 제한(구 A3)은 폐지됐다 — 로그인한 사람은 모든 지원자를 본다 (ADR-0017).
    이 관계가 남기는 제한은 하나뿐: member 는 배정된 건만 평가할 수 있다.
    배정·해제 자체는 여전히 admin 전용 (ADR-0013).

    interviewer_id 는 역할이 아니라 "그 건의 면접관"이라는 관계다 — 역할이
    admin·member 둘로 줄어든 뒤에도 컬럼명은 그대로 둔다.
    """

    __tablename__ = "interviewer_assignments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    interviewer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    assigned_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("application_id", "interviewer_id", name="uq_interviewer_assignments"),
    )


# ── interviewer_availability — 면접관 가용 시간 (일정 자동화 · v1.2) ──
class InterviewerAvailability(Base):
    """면접관이 등록하는 "면접 가능한 시간대". 후보 슬롯 생성의 입력이다 (ADR-0016).

    반복 규칙(매주 화 14~18시 등)은 두지 않는다 — 구간 행을 여러 개 넣는 것으로 갈음.
    """

    __tablename__ = "interviewer_availability"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 누구나 면접관이 될 수 있다 — 대상 role 검사는 없다 (ADR-0017)
    interviewer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("start_at < end_at", name="ck_interviewer_availability_range"),
        # 면접관별 기간 조회
        Index("ix_interviewer_availability_user_start", "interviewer_id", "start_at"),
    )


# ── schedule_proposals — 면접 일정 제안 (일정 자동화 · v1.2) ─────────
class ScheduleProposal(Base):
    """지원자 1명에게 보내는 "이 중에서 고르세요" 제안 한 건.

    지원자는 로그인이 없으므로 public_token(B6)과 같은 토큰 공개 접근 패턴을 쓴다.
    재제안 시 새 행을 만들고 이전 행은 canceled — 이력이 남는다(stage_history와 같은 철학).
    만료는 스케줄러 없이 조회 시점 판정(B4 마감과 같은 방식).
    """

    __tablename__ = "schedule_proposals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    # 지원자 공개 접근 토큰. 메일 링크에 실린다
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'proposed'")
    )
    # 지원자가 고른 슬롯. confirmed 때만 값 존재.
    # slots가 이 테이블을 FK로 참조하는 순환 관계라 use_alter로 ALTER 분리 생성.
    confirmed_slot_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "schedule_slots.id",
            use_alter=True,
            name="fk_schedule_proposals_confirmed_slot",
        ),
    )
    # 선택 기한. 지나면 조회 시점 판정으로 expired
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(
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

    # 지원자 공개 페이지·상세 조회용. FK 경로가 둘(proposal_id / confirmed_slot_id)이라 명시.
    slots: Mapped[list["ScheduleSlot"]] = relationship(
        foreign_keys="ScheduleSlot.proposal_id", order_by="ScheduleSlot.start_at"
    )

    __table_args__ = (
        CheckConstraint(_in("status", PROPOSAL_STATUSES), name="ck_schedule_proposals_status"),
        # 지원자 상세에서 최신 제안 표시
        Index(
            "ix_schedule_proposals_app_created",
            "application_id",
            text("created_at DESC"),
        ),
    )


# ── schedule_slots — 제안에 묶인 후보 슬롯 (일정 자동화 · v1.2) ──────
class ScheduleSlot(Base):
    """슬롯은 생성 시점의 가용 시간 스냅샷이다 — 이후 면접관이 가용 시간을 지워도
    이미 나간 제안은 유효하다(지원자가 보고 있는 선택지가 바뀌면 안 된다).
    확정 시점에 겹침(같은 면접관의 다른 confirmed 슬롯)만 재검증한다.
    """

    __tablename__ = "schedule_slots"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    proposal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("schedule_proposals.id"), nullable=False
    )
    # 이 슬롯에 들어갈 면접관
    interviewer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("start_at < end_at", name="ck_schedule_slots_range"),
        # 같은 제안 안 중복 슬롯 방지
        UniqueConstraint(
            "proposal_id", "interviewer_id", "start_at", name="uq_schedule_slots"
        ),
    )


# ── application_embeddings — 시맨틱 검색용 벡터 (ADR-0017) ─────────
EMBEDDING_DIM = 768

if Vector is not None:
    class ApplicationEmbedding(Base):
        """지원자 self_intro + skills 를 임베딩한 벡터.

        지원서 제출 시 1회 생성한다. 모델이나 텍스트가 바뀌면 재생성한다.
        """

        __tablename__ = "application_embeddings"

        id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
        application_id: Mapped[int] = mapped_column(
            BigInteger, ForeignKey("applications.id"), unique=True, nullable=False
        )
        embedding = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
        model_name: Mapped[str] = mapped_column(String(100), nullable=False)
        created_at: Mapped[datetime] = mapped_column(
            DateTime(timezone=True), nullable=False, server_default=func.now()
        )
