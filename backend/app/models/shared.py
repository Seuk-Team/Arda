"""Shared / Cross-cutting · 에이전트 흔적·문서 앵커·체인 발행. 특정 컨텍스트에 종속되지 않는 감사·관측 축.

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



# ── agent_traces — 아르 대화 로그 (0014, ADR-0024 Qwen 학습·평가) ────
# 매 대화의 요청·도구·답변·비용을 남기고, 담당자가 나중에 라벨한 것만 학습셋으로.
# 상세 논거는 마이그레이션 0014 헤더 참고.
class AgentTrace(Base):
    __tablename__ = "agent_traces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    turn_index: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    user_message: Mapped[str] = mapped_column(Text, nullable=False)
    assistant_reply: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    history: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'::json"))
    tool_calls: Mapped[list] = mapped_column(JSON, nullable=False, server_default=text("'[]'::json"))
    pending_action: Mapped[dict | None] = mapped_column(JSON)
    backend: Mapped[str] = mapped_column(String(50), nullable=False, server_default="")
    model_tag: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 라벨
    label_verdict: Mapped[str | None] = mapped_column(String(20))
    label_correction: Mapped[str | None] = mapped_column(Text)
    label_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    label_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "label_verdict IS NULL OR label_verdict IN ('good','bad','needs_fix')",
            name="ck_agent_traces_label_verdict",
        ),
        Index("ix_agent_traces_verdict_created", "label_verdict", "created_at"),
    )


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
    # 이 표에는 고칠 수 있는 칸이 하나도 없다 (alembic 0008). 공개 체인에 못 박은
    # 기록은 chain_publications 로 뺐다 — 여기 컬럼을 두면 그 칸이 원장의 유일한
    # 구멍이 되기 때문이다.

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


# ── document_anchors 를 DB 단에서 추가 전용으로 잠근다 (ADR-0028) ─────
#
# "고쳐 쓰지 않는다"가 코드의 약속이기만 하면, 앱을 거치지 않는 손(psql·관리도구)
# 에는 아무 구속력이 없다. DB 가 직접 거부하게 한다.
#
# 허용: INSERT 뿐이다.
# 거부: UPDATE · DELETE · TRUNCATE — **고칠 수 있는 칸이 하나도 없다** (0008).
#       0006 에서는 2단계용으로 ots_* 두 칸을 열어 뒀었는데, 공개 체인 기록을
#       chain_publications 로 빼면서 그 예외가 필요 없어졌다. 예외가 없는 편이
#       낫다 — 열린 칸 하나가 곧 원장의 유일한 구멍이다.
#
# **한계**: 트리거를 끌 수 있는 권한자는 이것도 우회한다. 봉인이 아니라 문턱이다.
# 진짜 봉인은 우리가 못 고치는 곳에 못 박을 때 생긴다 (ADR-0028 2단계).
#
# 같은 내용이 alembic `0006`·`0008` 에도 있다 — 여기는 **새로 만드는 DB**
# (create_all), 저기는 **이미 있는 DB** 를 위한 것이다. 마이그레이션은 그 시점의
# 스냅샷이라 여기서 import 하지 않는다. 한쪽을 고치면 다른 쪽도 고쳐야 한다.
_APPEND_ONLY_FN = DDL("""
CREATE OR REPLACE FUNCTION document_anchors_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            '무결성 원장은 삭제할 수 없습니다 (document_anchors seq=%%)', OLD.seq
            USING ERRCODE = 'restrict_violation';
    END IF;
    RAISE EXCEPTION
        '무결성 원장은 고쳐 쓸 수 없습니다 (document_anchors seq=%%)', OLD.seq
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
""")

# TRUNCATE 는 행 트리거를 타지 않는다. 따로 막지 않으면 위의 것을 전부 통과해
# 원장이 한 번에 비워진다.
_NO_TRUNCATE_FN = DDL("""
CREATE OR REPLACE FUNCTION document_anchors_no_truncate() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '무결성 원장은 비울 수 없습니다 (document_anchors TRUNCATE)'
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
""")

_TRIGGERS = DDL("""
CREATE TRIGGER trg_document_anchors_append_only
BEFORE UPDATE OR DELETE ON document_anchors
FOR EACH ROW EXECUTE FUNCTION document_anchors_append_only();

CREATE TRIGGER trg_document_anchors_no_truncate
BEFORE TRUNCATE ON document_anchors
FOR EACH STATEMENT EXECUTE FUNCTION document_anchors_no_truncate();
""")

for _ddl in (_APPEND_ONLY_FN, _NO_TRUNCATE_FN, _TRIGGERS):
    event.listen(
        DocumentAnchor.__table__,
        "after_create",
        _ddl.execute_if(dialect="postgresql"),
    )


# ── chain_publications — 사슬 머리를 공개 체인에 못 박은 기록 (ADR-0028 2단계) ──
class ChainPublication(Base):
    """사슬 머리 하나를 공개 블록체인에 올린 기록. 한 줄이 한 건의 거래다.

    **머리 하나로 그 앞 전체가 덮인다.** `document_anchors` 의 각 고리가 앞
    고리의 해시를 재료로 쓰기 때문에, seq=20 의 `chain_hash` 는 1~20 전부에 대한
    약속이다. 그래서 머클 트리도, 고리마다의 증명도 필요 없다 — **올리는 값은
    언제나 딱 하나**다.

    이 표 자체는 append-only 가 아니다. 보낸 뒤 확정될 때까지 `pending` 이었다가
    블록에 실리면 `confirmed` 로 바뀌기 때문이다. 그래도 상관없다 — **여기 적힌
    것이 진실이 아니라, 체인에 실린 것이 진실이다.** 이 표는 "어디를 보면
    되는지"를 가리키는 영수증일 뿐이고, `tx_hash` 로 누구나 직접 확인한다.

    그래서 이 표를 통째로 위조해도 소용이 없다. 체인의 값과 안 맞으면 그만이다.
    """

    __tablename__ = "chain_publications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 어느 체인인가. 테스트넷과 메인넷을 섞어 놓고 나중에 헷갈리지 않도록 남긴다.
    network: Mapped[str] = mapped_column(String(30), nullable=False)
    # 이 거래가 덮는 범위 — 1 부터 이 seq 까지.
    covered_through_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 실제로 체인에 실어 보낸 값 (그 시점 사슬 머리).
    chain_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(String(66), unique=True)
    block_number: Mapped[int | None] = mapped_column(BigInteger)
    from_address: Mapped[str | None] = mapped_column(String(42))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'pending'")
    )
    # 실패 사유를 지운 채로 두지 않는다 — 왜 못 올렸는지가 다음 시도의 단서다.
    error: Mapped[str | None] = mapped_column(Text)
    # OTS 증명(base64). 폴리곤 행에서는 항상 NULL.
    # **잃어버리면 다시 못 만든다** — 도장을 다시 찍어야 하고 시각이 밀린다.
    proof: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            _in("status", PUBLICATION_STATUSES), name="ck_chain_publications_status"
        ),
        UniqueConstraint("tx_hash", name="uq_chain_publications_tx"),
        Index("ix_chain_publications_covered", "covered_through_seq"),
        # 같은 사슬 머리를 같은 네트워크에 두 번 올리지 않는다. 폴리곤과 OTS 는
        # 서로 다른 행이라 network 를 포함해야 한다 — 빼면 한쪽만 올라간다.
        # 실패한 것은 다시 시도해야 하므로 제외한다.
        Index(
            "uq_chain_publications_network_hash",
            "network",
            "chain_hash",
            unique=True,
            postgresql_where=text("status <> 'failed'"),
        ),
    )
