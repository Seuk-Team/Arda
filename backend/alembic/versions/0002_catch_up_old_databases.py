"""오래된 DB 따라잡기 — 역할 2종화 · ai_summary_model 폭

alembic 도입 이전에 `create_all` 로 만들어져 **코드와 어긋난 채 남아 있는** DB 를
현재 모델에 맞춘다. `08-local-setup.md` 의 이행 목록을 코드로 옮긴 것이다.

**갓 만든 DB 에서는 전부 no-op 이다** — 0001 이 이미 올바른 모양으로 만든다.
그래서 신규·기존 어느 쪽이든 `alembic upgrade head` 하나로 끝난다.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None

# ADR-0017 로 역할이 3종 → 2종이 됐다.
_OLD_ROLES = ("recruiter", "interviewer")


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1) ai_summary_model 폭 (2026-09-01) ──────────────────────────
    # varchar(50) 이면 정상 요약의 모델 태그(81자)가 안 들어가 commit 에서 죽는다.
    # 증상이 고약하다 — Claude 호출 3번을 끝낸 뒤 저장에서 죽어 **돈은 쓰고 결과는
    # 버린다.** BackgroundTasks 라 화면에는 아무 에러도 안 뜬다.
    width = bind.execute(
        sa.text(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_name='applications' AND column_name='ai_summary_model'"
        )
    ).scalar()
    if width is not None and width < 200:
        op.alter_column(
            "applications",
            "ai_summary_model",
            type_=sa.String(length=200),
            existing_nullable=True,
        )

    # ── 2) 역할 2종화 (ADR-0017) ────────────────────────────────────
    # 제약을 먼저 떼야 UPDATE 가 옛 제약에 걸리지 않는다.
    stale = bind.execute(
        sa.text("SELECT count(*) FROM users WHERE role = ANY(:old)"),
        {"old": list(_OLD_ROLES)},
    ).scalar()
    if stale:
        op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
        op.execute(
            "UPDATE users SET role='member' WHERE role IN ('recruiter','interviewer')"
        )
        op.execute(
            "ALTER TABLE users ADD CONSTRAINT ck_users_role "
            "CHECK (role IN ('admin','member'))"
        )


def downgrade() -> None:
    """되돌리지 않는다.

    역할 3종은 이미 버린 구분이라 되살릴 근거가 없고(어떤 member 가 옛 recruiter
    였는지 알 방법이 없다), 컬럼을 다시 좁히면 저장된 요약이 잘린다.
    """
    raise NotImplementedError("이 이행은 되돌리지 않는다 — docstring 참고")
