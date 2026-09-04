"""사슬 머리를 공개 블록체인에 못 박은 기록 — chain_publications (ADR-0028 2단계)

**사슬 머리 하나만 올리면 그 앞 전체가 덮인다.** `document_anchors` 의 각 고리는
앞 고리의 해시를 재료로 쓰므로, seq=20 의 `chain_hash` 는 1~20 전체에 대한 약속이다.
그래서 머클 트리도, 고리마다의 증명 파일도 필요 없다. 머리 하나를 올린다.

`ots_status`·`ots_proof` 를 뺀다. `0005` 에서 OpenTimestamps 를 예상하고 비워
뒀던 자리인데, 폴리곤으로 방향이 정해지면서 쓸 일이 없어졌다(2026-09-04 결정).
**아무도 쓴 적이 없는 컬럼이라 지우는 편이 낫다** — 남겨 두면 `0006` 트리거가
그 두 칸에 UPDATE 를 열어 둔 채로 있어야 하고, 그게 원장의 유일한 구멍이 된다.

그래서 이 리비전 뒤 `document_anchors` 는 **UPDATE 가 아예 안 되는 표**가 된다.
넣기만 되고, 고치는 문이 하나도 없다.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


# 고칠 수 있는 칸이 하나도 없다 — 0006 판과 다른 점이 이것뿐이다.
_APPEND_ONLY_STRICT = """
CREATE OR REPLACE FUNCTION document_anchors_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            '무결성 원장은 삭제할 수 없습니다 (document_anchors seq=%)', OLD.seq
            USING ERRCODE = 'restrict_violation';
    END IF;
    RAISE EXCEPTION
        '무결성 원장은 고쳐 쓸 수 없습니다 (document_anchors seq=%)', OLD.seq
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""

# 0006 판 — downgrade 에서 되돌릴 때 쓴다 (ots_* 두 칸을 다시 열어 준다).
_APPEND_ONLY_WITH_OTS = """
CREATE OR REPLACE FUNCTION document_anchors_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            '무결성 원장은 삭제할 수 없습니다 (document_anchors seq=%)', OLD.seq
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF ROW(NEW.id, NEW.seq, NEW.application_id, NEW.doc_type, NEW.file_id,
           NEW.content_sha256, NEW.prev_chain_hash, NEW.chain_hash, NEW.anchored_at)
       IS DISTINCT FROM
       ROW(OLD.id, OLD.seq, OLD.application_id, OLD.doc_type, OLD.file_id,
           OLD.content_sha256, OLD.prev_chain_hash, OLD.chain_hash, OLD.anchored_at)
    THEN
        RAISE EXCEPTION
            '무결성 원장은 고쳐 쓸 수 없습니다 (document_anchors seq=%). 바꿀 수 있는 것은 ots_status·ots_proof 뿐입니다', OLD.seq
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.create_table(
        "chain_publications",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("network", sa.String(length=30), nullable=False),
        sa.Column("covered_through_seq", sa.BigInteger(), nullable=False),
        sa.Column("chain_hash", sa.String(length=64), nullable=False),
        sa.Column("tx_hash", sa.String(length=66), nullable=True),
        sa.Column("block_number", sa.BigInteger(), nullable=True),
        sa.Column("from_address", sa.String(length=42), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tx_hash", name="uq_chain_publications_tx"),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'failed')",
            name="ck_chain_publications_status",
        ),
    )
    op.create_index(
        "ix_chain_publications_covered",
        "chain_publications",
        ["covered_through_seq"],
    )

    op.drop_column("document_anchors", "ots_status")
    op.drop_column("document_anchors", "ots_proof")
    op.execute(_APPEND_ONLY_STRICT)


def downgrade() -> None:
    op.add_column(
        "document_anchors",
        sa.Column("ots_proof", sa.Text(), nullable=True),
    )
    op.add_column(
        "document_anchors",
        sa.Column(
            "ots_status",
            sa.String(length=20),
            server_default=sa.text("'none'"),
            nullable=False,
        ),
    )
    op.execute(_APPEND_ONLY_WITH_OTS)
    op.drop_index("ix_chain_publications_covered", table_name="chain_publications")
    op.drop_table("chain_publications")
