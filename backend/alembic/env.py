"""alembic 실행 환경.

접속 정보는 `alembic.ini` 가 아니라 **`DATABASE_URL` 환경변수**에서 온다 —
앱과 같은 값을 쓰고, 비밀번호가 저장소에 남지 않게 하려는 것이다.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# backend/ 를 import 경로에 올린다 — alembic 은 backend/ 에서 실행한다.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Base  # noqa: E402
from app import models  # noqa: E402,F401  — 모델을 import 해야 메타데이터가 채워진다

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit(
        "DATABASE_URL 이 필요하다. 예:\n"
        '  DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/arda" '
        "uv run alembic upgrade head"
    )


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    """임베딩 테이블은 pgvector 확장이 있는 DB 에서만 다룬다.

    확장이 없는 환경(순정 postgres 이미지)에서 `vector` 타입을 만들려 들면
    실패하는데, alembic 은 한 트랜잭션으로 묶여 있어 **나머지 테이블까지 통째로
    롤백된다.** `create_all` 쪽에서 이미 같은 판단을 하고 있다(main.py·conftest).
    """
    if name == "application_embeddings":
        from app.db import pgvector_ready

        return pgvector_ready()
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool, future=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            # 컬럼 폭 변경(varchar(50) → 200)을 잡으려면 타입 비교가 켜져 있어야 한다.
            # 2026-09-01 사고가 정확히 그 종류였다.
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
