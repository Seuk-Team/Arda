"""Application 컨텍스트 (★★★ 가장 큰 스타) · 지원 워크플로 · 서류·판정·단계 이력·평가·파일·인적성·메일 로그.

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
    JSON,
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
from app.models.constants import (
    APPLICATION_SOURCES,
    DECISION_SOURCES,
    DOC_DECISIONS,
    EMAIL_ACTOR_KINDS,
    EMAIL_LOG_STAGES,
    EMAIL_STATUSES,
    FILE_KINDS,
    STAGES,
    _in,
)

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None




# ── applications — 지원서 (C1·D1·D6) ★핵심 테이블 ────────────────────
class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    job_posting_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("job_postings.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    # 앱 로그인의 비밀번호 자리다 (이메일 + 생년월일 8자리, ADR-0033).
    # **값이 없으면 로그인이 안 된다** — 옛 지원서는 비워 두고 막는 쪽으로 떨어진다.
    birth_date: Mapped[date | None] = mapped_column(Date)
    education: Mapped[str | None] = mapped_column(String(100))
    career_years: Mapped[int | None] = mapped_column(SmallInteger)
    skills: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    self_intro: Mapped[str | None] = mapped_column(Text)

    # AI 요약: 접수 시 1회 생성해 저장한다. 패널을 열 때마다 생성하지 않는다.
    ai_summary: Mapped[str | None] = mapped_column(Text)
    ai_summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_summary_model: Mapped[str | None] = mapped_column(String(200))

    # 자동 심사 (0016, ADR-0034). 서류 100점 · 내역 · 판정 · 누가 정했나.
    # decision_source='human' 이면 아르는 더 이상 이 지원자의 단계를 옮기지 않는다.
    doc_score: Mapped[int | None] = mapped_column(SmallInteger)
    doc_score_detail: Mapped[dict | None] = mapped_column(JSON)
    doc_decision: Mapped[str | None] = mapped_column(String(20))
    doc_decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_source: Mapped[str | None] = mapped_column(String(10))

    current_stage: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'applied'")
    )
    privacy_agreed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'form'")
    )

    # 지원 현황 조회 링크 (신-1 지원자 포털). 지원자가 이메일을 넣으면 그때 발급해
    # 메일로 보낸다 — **접수 시점에 만들지 않는다.** 아무도 안 볼 링크를 미리 만들어
    # 두면 유효한 토큰이 계정 수만큼 상시 존재하게 된다.
    #
    # 지원자에게 비밀번호를 만들게 하지 않는 이유: 지원할 때마다 계정을 만들게 하면
    # 지원율이 떨어지고, 우리는 **지원하지 않을 수도 있는 사람의 비밀번호**까지 갖게
    # 된다. 나머지 공개 경로(면접·일정·인적성)와 같은 토큰 방식으로 맞춘다.
    portal_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    portal_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
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
        CheckConstraint(
            "doc_decision IS NULL OR " + _in("doc_decision", DOC_DECISIONS),
            name="ck_applications_doc_decision",
        ),
        CheckConstraint(
            "decision_source IS NULL OR " + _in("decision_source", DECISION_SOURCES),
            name="ck_applications_decision_source",
        ),
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
    # SES 가 준 MessageId. **`sent` 는 "SES 가 받아줬다"까지만 뜻한다** — 받은 뒤
    # 반송되거나, `MAIL_DRY_RUN` 이면 아예 안 나가고도 `sent` 가 된다.
    # 그래서 "보냈다는데 안 왔다"가 오면 이 값이 있어야 SES 쪽을 추적할 수 있다.
    #
    # 2026-09-07 에 추가했다. 그전에는 이 값을 **로그로만** 갖고 있었는데, 실제로
    # 그 상황이 왔을 때 서버 셸이 없는 사람은 확인할 방법이 없었다.
    # NULL 이면 아직 안 보냈거나 DRY_RUN 이거나 옛 행이다.
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
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
