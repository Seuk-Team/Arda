"""답변마다 대조 — interview_findings.turn_id

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-11

서류 주장 ↔ 면접 발언 대조를 면접이 끝날 때 한 번만 만들던 것을, **답변이 저장될
때마다 그 답변 하나로도** 만든다. 담당자 화상 방이 대조를 **그 답변 밑에** 띄우려면
어느 답변에서 나온 대조인지 알아야 한다.

NULL 이면 면접이 끝난 뒤 전체 전사로 만든 것이다(주로 확인필요 — 면접에서 다루지
않은 주장). 기존 행은 전부 그쪽이라 NULL 그대로 둔다.

답변이 지워지면 그 답변의 대조도 같이 지운다(CASCADE) — 근거가 사라진 대조가
남으면 면접관이 원문을 찾지 못한다. 롤백 시 컬럼 제거만.
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_findings",
        sa.Column(
            "turn_id",
            sa.BigInteger,
            sa.ForeignKey("interview_turns.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_findings", "turn_id")
