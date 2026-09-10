"""꼬리질문 자리 — interview_turns.generated_from_turn_id

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-10

지원자가 답한 뒤 아르가 그 답변을 재료로 만든 꼬리질문을 다음 자리에 삽입할 수
있게 한다. 컬럼은 nullable — 담당자가 미리 넣어 둔 사전 질문은 값이 없다.

값이 있으면 "이 질문은 아르가 turn_id 답변에서 만들었다" 는 뜻이고, 담당자 화면이
이 근거를 배지로 표시한다. 담당자가 근거를 볼 수 없으면 자동생성 여부를 모르고
지원자에게 다시 물을 근거도 사라진다 (ADR-0034 취지 유지 — 사람이 최종 판단).

기존 행에 영향 없음. 롤백 시 컬럼 제거만.
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_turns",
        sa.Column(
            "generated_from_turn_id",
            sa.BigInteger,
            sa.ForeignKey("interview_turns.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("interview_turns", "generated_from_turn_id")
