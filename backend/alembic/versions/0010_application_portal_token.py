"""지원 현황 조회 링크 — applications.portal_token (신-1 지원자 포털)

지원자가 "내 지원 어떻게 됐나"를 볼 수 있게 하는 링크의 토큰이다.
이메일을 넣으면 그때 발급해 메일로 보낸다.

**접수 시점에 미리 만들지 않는다.** 아무도 안 볼 링크를 전건에 만들어 두면
유효한 토큰이 지원자 수만큼 상시 존재하게 된다. 필요할 때 만들고 기한을 둔다.

**비밀번호를 만들게 하지 않는 이유**: 지원할 때마다 계정을 만들게 하면 지원율이
떨어지고, 지원하지 않을 수도 있는 사람의 비밀번호까지 우리가 갖게 된다.
나머지 공개 경로(면접·일정·인적성)와 같은 토큰 방식으로 맞춘다.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("portal_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column(
            "portal_token_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    # 토큰으로 찾는 경로가 유일한 조회 방법이라 인덱스가 곧 성능이고,
    # unique 로 둬야 재발급이 남의 링크를 덮는 일이 생기지 않는다.
    op.create_unique_constraint(
        "uq_applications_portal_token", "applications", ["portal_token"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_applications_portal_token", "applications", type_="unique"
    )
    op.drop_column("applications", "portal_token_expires_at")
    op.drop_column("applications", "portal_token")
