"""DB 연결과 선언적 베이스.

스키마가 굳기 전까지는 마이그레이션을 쌓지 않는다 — `create_all` 로 만들고,
바뀌면 DB 를 지우고 다시 만든다. 더미 데이터뿐이라 잃을 것이 없다.
"""

import logging
import os

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/arda"
)

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


logger = logging.getLogger(__name__)

# 확장을 못 켜는 서버에서 매 커넥션마다 같은 경고를 쏟지 않게 한 번만 남긴다.
_pgvector_warned = False


@event.listens_for(engine, "connect")
def _enable_pgvector(dbapi_connection, connection_record):
    """pgvector 확장을 켠다. **없는 서버에서는 조용히 넘어간다.**

    운영 postgres 이미지에는 확장이 안 깔려 있다(2026-08-31 배포에서 API 가 기동 중
    죽었다 — 여기서 예외가 나면 커넥션이 통째로 실패해 앱이 아예 안 뜬다).
    시맨틱 검색(ADR-0021)만 꺼지고 나머지 API 는 그대로 떠야 한다 —
    embedder.py 도 같은 판단으로 "pgvector 미설치 — 임베딩 건너뜀" 폴백을 갖고 있다.
    """
    global _pgvector_warned
    try:
        with dbapi_connection.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        dbapi_connection.commit()
    except Exception:
        dbapi_connection.rollback()
        if not _pgvector_warned:
            _pgvector_warned = True
            logger.warning(
                "pgvector 확장을 켜지 못했다 — 시맨틱 검색이 꺼진 채로 뜬다. "
                "DB 이미지를 pgvector/pgvector 계열로 바꿔야 켜진다"
            )


def pgvector_ready() -> bool:
    """확장이 실제로 설치돼 있는지. 임베딩 테이블을 만들지 말지 정하는 데 쓴다."""
    try:
        with engine.connect() as conn:
            return bool(
                conn.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                ).scalar()
            )
    except Exception:
        return False


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI 의존성으로 쓴다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
