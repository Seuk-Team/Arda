"""테이블 정의 — docs/01-erd.md 를 그대로 옮긴 것.

문서와 이 파일이 어긋나면 **문서가 기준**이다. 컬럼을 여기서 임의로 추가하지 않는다.
표 순서도 문서와 같게 유지해 나란히 놓고 대조할 수 있게 한다.

단계·역할 같은 고정값은 DB enum 이 아니라 **체크 제약 + 아래 상수**로 관리한다
(01-erd.md "단계(stage) — 고정 enum" 참고. 값이 늘어도 마이그레이션이 필요 없다).
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
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
# 무결성 앵커가 지문을 뜨는 대상 (ADR-0028). 첨부 2종 + 폼에 직접 쓴 자기소개.
# `self_intro` 는 파일이 아니라 applications.self_intro 텍스트라 file_id 가 없다.
DOC_TYPES = FILE_KINDS + ("self_intro",)

# 메일 발송 (G4). email_logs 의 stage 는 단계 5종에 custom 이 하나 더 붙는다 —
# 수동·에이전트 발송은 단계 이동이 아니라서 STAGES 로는 표현할 값이 없다.
# **STAGES 자체를 늘리지 않는다.** applications.current_stage 는 그대로여야 한다.
EMAIL_LOG_STAGES = STAGES + ("custom",)
# 발송 주체. 서명과 회신 주소가 이 값으로 갈린다 (G4 결정 6·7)
#   human  — 사람이 화면에서 트리거·작성 (단계 변경·수동 발송·일정 제안)
#   agent  — 아르가 문안을 작성 (send_email 도구). actor_id 는 승인한 사람
#   system — 지원자 본인의 행동이 트리거 (접수 확인·일정 확정 통보)
EMAIL_ACTOR_KINDS = ("human", "agent", "system")
# 문구가 존재하는 단계. screening 은 내부 검토라 지원자에게 보내지 않고,
# custom 은 본문을 그때그때 쓰므로 템플릿이 없다.
TEMPLATE_STAGES = ("applied", "interview", "accepted", "rejected")


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


# ── document_anchors — 제출물 무결성 앵커 (ADR-0028) ──────────────────
class DocumentAnchor(Base):
    """제출 시점의 이력서·자소서 지문(SHA-256)을 한 줄씩 쌓는 append-only 원장.

    **이 표의 목적은 위조를 막는 것이 아니라 드러나게 하는 것이다.** 원본은 S3 와
    `applications.self_intro` 에 그대로 있고, 여기에는 지문만 남는다. 나중에 원본이
    바뀌면 지문이 안 맞으므로 "바뀌었다"가 증명된다.

    행끼리 사슬로 묶인다 — `chain_hash` 는 **앞 행의 `chain_hash` 를 재료로 쓴다**
    (`anchoring.compute_chain_hash`). 그래서 가운데 한 줄만 조용히 고쳐 쓸 수 없다.
    뒤따르는 모든 행의 `chain_hash` 가 동시에 어긋나기 때문이다. 공책의 각 장에
    앞장의 지문을 베껴 적어 두는 것과 같다 — 한 장을 찢으면 다음 장이 안 맞는다.

    **UPDATE·DELETE 를 하지 않는다.** 내용이 바뀌었으면 새 행을 쌓지도 않는다 —
    검증에서 어긋남으로 드러나는 것이 목적이기 때문이다. 재제출처럼 정말 새
    문서가 생긴 경우에만 새 `seq` 로 append 한다.

    `ots_*` 는 2단계(공개 타임스탬프)를 위해 비워 둔 자리다 — 지금은 우리 DB 안의
    사슬이라 "우리가 언제 봤다"까지만 증명한다. 제3자 증명은 이 컬럼들이 채워질 때
    생긴다. ADR-0028 "남은 것" 절.
    """

    __tablename__ = "document_anchors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 사슬에서의 자리. 1부터 빈틈없이 올라간다 — 빠진 번호가 있으면 그 자체가 사고다.
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    doc_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 첨부일 때만 채운다. self_intro 는 파일이 아니라 NULL.
    file_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("files.id"))
    # 원본 내용 자체의 지문. 파일은 S3 객체 바이트, 자기소개는 UTF-8 바이트.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # 사슬의 첫 행만 NULL. 그 외에는 앞 행의 chain_hash 와 같아야 한다.
    prev_chain_hash: Mapped[str | None] = mapped_column(String(64))
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    anchored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 2단계 자리 — 'none' | 'pending' | 'confirmed'
    ots_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'none'")
    )
    ots_proof: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(_in("doc_type", DOC_TYPES), name="ck_document_anchors_doc_type"),
        # 파일은 file_id 가 있고 자기소개는 없다. 뒤집힌 행이 들어오면 검증이
        # 조용히 건너뛰게 되므로 DB 에서 막는다.
        CheckConstraint(
            "(doc_type = 'self_intro') = (file_id IS NULL)",
            name="ck_document_anchors_file_id",
        ),
        # 같은 문서를 두 번 앵커하지 않는다 — 재실행(백필·재시도)이 사슬을 부풀리면
        # 안 된다. 파일은 file_id 로 유일하다.
        UniqueConstraint("file_id", name="uq_document_anchors_file"),
        # 자기소개는 file_id 가 NULL 이라 위 제약이 안 걸린다(Postgres 는 NULL 을
        # 서로 다른 값으로 본다). 지원서당 하나로 부분 인덱스에서 따로 막는다.
        Index(
            "uq_document_anchors_self_intro",
            "application_id",
            unique=True,
            postgresql_where=text("doc_type = 'self_intro'"),
        ),
        Index("ix_document_anchors_application", "application_id", "doc_type"),
    )


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
    # 확정 제목·본문 (G4). NULL 이면 **발송 시점 렌더**다 — 단계 자동 발송이
    # 그렇다. 면접 안내는 발송 시점에야 라이브 일정 링크를 알 수 있어서
    # (worker._interview_at) 미리 굳힐 수 없다.
    # 값이 있으면 워커가 렌더를 건너뛰고 그대로 보낸다 = 보낸 그대로의 기록.
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    # 발송 주체 (G4 결정 6). 서명·회신 주소가 이 값으로 갈린다.
    actor_kind: Mapped[str] = mapped_column(
        String(10), nullable=False, server_default=text("'system'")
    )
    # human·agent 일 때의 사람. agent 는 도구를 승인한 사람이다 (아르가 아니다 —
    # 아르는 users 행이 없고, 책임 주체는 승인자다). system 이면 NULL.
    actor_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id")
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
        CheckConstraint(_in("stage", EMAIL_LOG_STAGES), name="ck_email_logs_stage"),
        CheckConstraint(
            _in("actor_kind", EMAIL_ACTOR_KINDS), name="ck_email_logs_actor_kind"
        ),
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



# ── AI 면접 (ADR-0026) ────────────────────────────────────────────
# 지원자가 링크로 들어와 아르와 면접을 보고, 전사·근거 대조·평가 초안이 남는다.
# 설계는 docs/02_tasks/AI면접-설계.md.


class InterviewSession(Base):
    """AI 면접 한 건. 지원자 1명 · 담당자가 만든다.

    지원자는 로그인이 없으므로 ScheduleProposal 과 같은 토큰 공개 접근 패턴을 쓴다(B6).
    만료는 스케줄러 없이 조회 시점 판정 — B4 마감·일정 제안과 같은 방식이다.

    **영상을 저장하지 않는다** (ADR-0026). 음성만 S3 에 두고 전사한다 — 저장하는 순간
    민감정보 보관 의무가 붙는데 대리 응시 확인은 실시간 표시로 충분하다.
    """

    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    # 지원자 공개 접근 토큰. 메일 링크에 실린다
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # pending | in_progress | done | expired
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    # 녹음·전사·보관 동의 시각. **지원 폼의 개인정보 동의와 별개다** —
    # 값이 없으면 면접을 시작하지 않는다.
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    turns: Mapped[list["InterviewTurn"]] = relationship(
        back_populates="session", order_by="InterviewTurn.seq"
    )
    findings: Mapped[list["InterviewFinding"]] = relationship(back_populates="session")


class InterviewTurn(Base):
    """질문 하나와 그에 대한 답변 하나.

    답변 음성은 지원 서류와 같은 경로로 올라간다(F1 presigned) — 서버를 안 거친다.
    `audio_duration_sec`·`stt_cost_usd` 는 기존 원가 관측 규약을 그대로 따른다
    (SttResponse 와 같은 필드명).
    """

    __tablename__ = "interview_turns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_sessions.id"), nullable=False
    )
    seq: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    audio_s3_key: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    audio_duration_sec: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    stt_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["InterviewSession"] = relationship(back_populates="turns")

    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_interview_turns_seq"),
    )


class InterviewFinding(Base):
    """서류의 주장과 면접 발언을 맞춰 본 결과 한 건.

    **점수를 두지 않는다** (ADR-0026 · ADR-0003). 합불에 곱해지는 수치를 만들면
    "AI 는 추천까지만" 이 무너진다. 갈래는 셋뿐이고 판단은 사람이 한다.

    양쪽 원문을 그대로 담는 이유: **지원자가 반박할 수 있어야 한다.** 목소리에서
    심리 상태를 추론하지 않는 대신, 근거를 인용해 보여 주는 것이 이 기능의 값이다.
    """

    __tablename__ = "interview_findings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("interview_sessions.id"), nullable=False
    )
    # 어느 서류의 주장인가 — resume | self_intro
    claim_source: Mapped[str] = mapped_column(String(20), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)  # 원문 인용
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)  # 원문 인용
    # consistent | inconsistent | unverified
    verdict: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["InterviewSession"] = relationship(back_populates="findings")

# ── 인적성(사전 성향) 설문 — ADR-0027 ────────────────────────────────


class AptitudeSession(Base):
    """사전 성향 설문 한 건. 담당자가 발송하고 지원자가 토큰 링크로 응답한다.

    접수 후·서류검토 전에 보내 응답이 서류검토 참고자료가 된다 (ADR-0027).
    토큰 공개 접근·조회 시점 만료 판정은 interview_sessions 와 같은 패턴이고,
    재발송도 같은 철학이다 — 새 행을 만들고 옛 행은 남긴다.

    **AI 면접 테이블에 얹지 않는다** — 저쪽은 음성 전제(audio_s3_key·stt_cost)라
    구조화 응답인 이 기능과 스키마가 다르다 (ADR-0027 결정 5).
    """

    __tablename__ = "aptitude_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("applications.id"), nullable=False
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # pending | done | expired
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # AI 관찰 요약 — 응답 사실의 재서술 한 문단. 유형 판정·점수를 만들지 않는다
    # (ADR-0027 결정 3). 통계는 저장하지 않는다 — answers 에서 코드로 계산한다.
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_model: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    answers: Mapped[list["AptitudeAnswer"]] = relationship(
        back_populates="session", order_by="AptitudeAnswer.id"
    )


class AptitudeAnswer(Base):
    """문항 하나에 대한 리커트 응답 하나.

    `question_text` 를 응답 시점 그대로 박아 둔다 — 문항 상수가 나중에 바뀌어도
    지원자가 실제로 본 문장이 남는다. interview_findings 가 원문을 인용해 두는
    것과 같은 이유다: 지원자가 반박할 수 있어야 한다.
    """

    __tablename__ = "aptitude_answers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("aptitude_sessions.id"), nullable=False
    )
    question_key: Mapped[str] = mapped_column(String(50), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 리커트 1(전혀 그렇지 않다) ~ 5(매우 그렇다)
    value: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["AptitudeSession"] = relationship(back_populates="answers")

    __table_args__ = (
        UniqueConstraint("session_id", "question_key", name="uq_aptitude_answers_key"),
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

        __table_args__ = (
            # ADR-0021 확정 인덱스. 없으면 <=> 가 매번 전건 스캔이라
            # 10만 건에서 검색이 초 단위로 늘어진다.
            # 마이그레이션 파일을 쌓지 않는 규약(db.py)이라 create_all 이 만든다.
            Index(
                "ix_application_embeddings_hnsw",
                "embedding",
                postgresql_using="hnsw",
                postgresql_ops={"embedding": "vector_cosine_ops"},
            ),
        )
