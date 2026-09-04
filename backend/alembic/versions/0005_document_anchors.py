"""제출물 무결성 앵커 — document_anchors (ADR-0028)

이력서·자소서의 지문(SHA-256)을 제출 시점에 떠서 append-only 사슬로 쌓는다.
원본은 S3 와 applications.self_intro 에 그대로 있고 여기에는 지문만 남는다.

**신규 테이블 하나만 만든다 — 기존 테이블은 건드리지 않는다.** 되돌리면
그대로 사라지고, 원본과 기존 기능에는 아무 영향이 없다.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_anchors",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("application_id", sa.BigInteger(), nullable=False),
        sa.Column("doc_type", sa.String(length=20), nullable=False),
        sa.Column("file_id", sa.BigInteger(), nullable=True),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("prev_chain_hash", sa.String(length=64), nullable=True),
        sa.Column("chain_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "anchored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "ots_status",
            sa.String(length=20),
            server_default=sa.text("'none'"),
            nullable=False,
        ),
        sa.Column("ots_proof", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq"),
        sa.UniqueConstraint("chain_hash"),
        sa.UniqueConstraint("file_id", name="uq_document_anchors_file"),
        sa.CheckConstraint(
            "doc_type IN ('resume', 'cover_letter', 'self_intro')",
            name="ck_document_anchors_doc_type",
        ),
        sa.CheckConstraint(
            "(doc_type = 'self_intro') = (file_id IS NULL)",
            name="ck_document_anchors_file_id",
        ),
    )
    # 자기소개는 file_id 가 NULL 이라 uq_document_anchors_file 이 안 걸린다
    # (Postgres 는 NULL 을 서로 다른 값으로 본다). 지원서당 하나로 여기서 막는다.
    op.create_index(
        "uq_document_anchors_self_intro",
        "document_anchors",
        ["application_id"],
        unique=True,
        postgresql_where=sa.text("doc_type = 'self_intro'"),
    )
    op.create_index(
        "ix_document_anchors_application",
        "document_anchors",
        ["application_id", "doc_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_anchors_application", table_name="document_anchors")
    op.drop_index("uq_document_anchors_self_intro", table_name="document_anchors")
    op.drop_table("document_anchors")
