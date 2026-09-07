"""SES MessageId 보관 칸 — email_logs.provider_message_id

`status='sent'` 는 **SES 가 받아줬다**까지만 뜻한다. 받은 뒤 반송될 수도 있고,
`MAIL_DRY_RUN` 이 켜져 있으면 SES 를 아예 안 부르고도 `sent` 가 된다.

그래서 "보냈다는데 안 왔다"가 오면 SES 쪽을 추적할 값이 필요한데, 지금까지는
그 MessageId 를 **로그로만** 갖고 있었다. 워커 코드에도 그렇게 적혀 있다:

    # SES 가 준 MessageId 를 남긴다. 스키마에 넣을 컬럼이 없어 로그로만 갖는다 —
    # "보냈는데 안 왔다"는 문의가 오면 이 값으로 SES 쪽을 추적한다.

2026-09-07 에 실제로 그 상황이 왔고, **서버 셸이 없는 사람은 확인할 방법이
없었다.** 로그는 사라지고 서버 접근은 한 사람만 가진다. 행에 남긴다.

NULL 인 경우: 아직 안 보냄 · DRY_RUN · 이 리비전 이전의 옛 행.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "email_logs",
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("email_logs", "provider_message_id")
