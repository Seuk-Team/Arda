"""DB 연결과 선언적 베이스.

스키마가 굳기 전까지는 마이그레이션을 쌓지 않는다 — `create_all` 로 만들고,
바뀌면 DB 를 지우고 다시 만든다. 더미 데이터뿐이라 잃을 것이 없다.
"""

import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/arda"
)

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def _enable_pgvector(dbapi_connection, connection_record):
    with dbapi_connection.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    dbapi_connection.commit()


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 의존성으로 쓴다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
