"""게시 증명 보관 칸 — chain_publications.proof (ADR-0028 3단계)

OpenTimestamps 는 폴리곤과 달리 **증명 파일을 우리가 들고 있어야** 한다.
폴리곤은 `tx_hash` 만 있으면 탐색기에서 누구나 확인하지만, OTS 는 그
`.ots` 증명(수백 바이트)이 있어야 "비트코인 블록 어디에 걸려 있는지"를
따라갈 수 있다. 잃어버리면 다시 못 만든다 — 도장을 다시 찍어야 하고,
그러면 시각이 그때로 밀린다.

base64 문자열로 넣는다. 수백 바이트짜리라 bytea 를 쓸 만큼 크지 않고,
API 응답·로그에 그대로 실어도 깨지지 않는 편이 다루기 쉽다.

폴리곤 행에서는 항상 NULL 이다.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chain_publications", sa.Column("proof", sa.Text(), nullable=True))
    # 같은 사슬 머리를 같은 네트워크에 두 번 올리지 않는다. 폴리곤과 OTS 는
    # 서로 다른 행이므로 network 를 포함해야 한다 — 안 그러면 한쪽만 올라간다.
    op.create_index(
        "uq_chain_publications_network_hash",
        "chain_publications",
        ["network", "chain_hash"],
        unique=True,
        postgresql_where=sa.text("status <> 'failed'"),
    )


def downgrade() -> None:
    op.drop_index("uq_chain_publications_network_hash", table_name="chain_publications")
    op.drop_column("chain_publications", "proof")
