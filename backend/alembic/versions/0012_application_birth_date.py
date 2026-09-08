"""applications.birth_date — 지원자 앱 로그인 (생년월일 8자리)

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-08

지원자가 앱에서 **이메일 + 생년월일 8자리**로 로그인한다. 그 비밀번호에 해당하는
값을 담을 자리다.

**해시하지 않고 날짜로 둔다.** 비밀번호처럼 쓰이지만 실제로는 생년월일이라,
해시해 두면 나중에 나이·연령대를 쓸 수 없게 되면서 보안은 거의 안 는다 —
탐색 공간이 만 단위라 해시를 떠도 대조로 뚫린다. 방어는 해시가 아니라
**시도 횟수 제한**이 한다 (app/api/applicant_auth.py).
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("birth_date", sa.Date(), nullable=True))
    # 로그인이 이메일로 찾는다. 지원자가 늘면 이메일 조회가 매 로그인마다 돈다.
    op.create_index("ix_applications_email", "applications", ["email"])


def downgrade() -> None:
    op.drop_index("ix_applications_email", table_name="applications")
    op.drop_column("applications", "birth_date")
