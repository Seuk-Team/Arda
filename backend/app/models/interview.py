"""Interview 컨텍스트 · 면접 배정·가용시간·일정 제안·세션·턴·발견.

ADR-0035 Phase 2 · models.py 분할."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Numeric,
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
    PROPOSAL_STATUSES,
    _in,
)

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    Vector = None



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

    # 면접 AI 점수 (0016, ADR-0034). 답변 대조 + 진위 일관성의 가중 합.
    # truth_samples 는 실시간 판정의 **집계값만** ({"n": 표본 수, "truth_sum": 합}) —
    # 프레임·개별 판정은 저장하지 않는다(ADR-0029 취지 유지).
    ai_score: Mapped[int | None] = mapped_column(SmallInteger)
    ai_score_detail: Mapped[dict | None] = mapped_column(JSON)
    truth_samples: Mapped[dict | None] = mapped_column(JSON)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    # 지원자가 이 질문에 **답을 마친 시각** (0018, 2026-09-11).
    #
    # `transcript` 와 따로 둔다. 전사는 워커가 뒤에서 한 번에 하나씩 돌려 몇 분씩
    # 늦게 채워지는데, "지금 질문" 을 `transcript IS NULL` 로 정하던 때는 그 사이
    # 재접속·앱의 확인 요청이 오면 지원자가 **이미 답한 질문으로 되돌아갔고**, 다시
    # 한 답은 원래 답과 부딪혀 409 로 버려졌다(2026-09-11 시연 실측). 이제 "답했다"는
    # 말이 끝나는 순간 여기에 남고, "지금 질문" 은 이게 NULL 인 가장 앞 칸이다.
    # 전사가 비어도(말이 안 담김) 답한 것은 답한 것이라 되돌아가지 않는다.
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_duration_sec: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    stt_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    # 아르가 어느 답변을 재료로 이 질문을 만들었나. 값이 있으면 "AI 자동 생성" 이고
    # 담당자 화면이 배지로 표시한다. 없으면 담당자가 미리 넣어 둔 사전 질문 (0017).
    generated_from_turn_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("interview_turns.id", ondelete="SET NULL")
    )
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
    # 어느 답변에서 나온 대조인가 (0019, 2026-09-11). 답변이 저장될 때마다 그 답변
    # 하나를 서류와 맞춰 여기에 붙인다 — 담당자 화상 방이 **그 답변 밑에** 띄운다.
    # NULL 이면 면접이 끝난 뒤 전체 전사로 만든 것이다(주로 확인필요).
    turn_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("interview_turns.id", ondelete="CASCADE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    session: Mapped["InterviewSession"] = relationship(back_populates="findings")
    turn: Mapped["InterviewTurn | None"] = relationship()

    @property
    def turn_seq(self) -> int | None:
        """화면은 회차를 번호(`seq`)로 안다 — `TurnOut` 에 id 가 없다."""
        return self.turn.seq if self.turn is not None else None
