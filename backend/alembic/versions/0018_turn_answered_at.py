"""답을 마친 시각 — interview_turns.answered_at

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-11

"지금 질문" 을 `transcript IS NULL` 인 가장 앞 칸으로 정하던 규칙을 `answered_at IS NULL`
로 바꾸기 위한 컬럼이다.

전사는 워커가 뒤에서 한 번에 하나씩 돌려(최대 180초) 몇 분씩 늦게 채워진다. 그 사이
재접속이나 앱의 확인 요청이 오면 지원자가 **이미 답한 질문으로 되돌아갔고**, 다시 한
답은 원래 답과 부딪혀 409 로 버려졌다 — 2026-09-11 시연에서 Q9 에서 Q1 로 돌아가
어떤 답도 저장되지 않았다. 전사가 빈 결과를 내면 그 칸은 영원히 NULL 이라 거기로
계속 되돌아갔다. "답했다" 와 "받아썼다" 를 나누면 둘 다 없어진다.

기존 행: 전사가 있는 칸은 답한 칸이다. 정확한 시각은 모르므로 행이 생긴 시각을 넣는다 —
이 값은 "가장 앞 빈칸" 을 고르는 데만 쓰이므로 NULL 인지 아닌지만 맞으면 된다.
롤백 시 컬럼 제거만 — 규칙은 코드를 되돌리면 예전으로 돌아간다.
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_turns",
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE interview_turns SET answered_at = created_at WHERE transcript IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("interview_turns", "answered_at")
