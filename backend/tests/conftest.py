"""에이전트 테스트 공용 픽스처.

PostgreSQL 을 그대로 쓰되, 각 테스트를 트랜잭션으로 감싸 롤백한다.
DB 에 흔적이 남지 않으므로 운영 데이터와 섞이지 않는다.
"""

from __future__ import annotations

import os

# APP_ENV 미설정은 production 으로 잠긴다(#122). 테스트는 개발 환경이므로 명시한다 —
# `app.security` 를 import 하기 전에 해야 한다. 없으면 JWT_SECRET 미설정과 겹쳐
# 기동 자체가 막힌다(.env 는 git 에 없어서 새 클론·CI 에서 특히).
os.environ.setdefault("APP_ENV", "dev")

# 개발 편의로 `.env` 에 넣은 에이전트 백엔드 스위치가 pytest 프로세스로 유입되면
# mock 이 우회된다: `AGENT_CHAT_BACKEND=ollama` 면 `patch(...)` 가 anthropic 경로를
# 잡아도 실제 요청이 Ollama 로 나가고, `OLLAMA_CHAT_STRUCTURED=1` 은 mock 응답 파싱과
# 어긋난다. 그래서 지금까지는 매번
# `AGENT_CHAT_BACKEND=anthropic OLLAMA_CHAT_STRUCTURED= … pytest` 로 override 해야 했다.
#
# **한 발 늦다** — `app.main` 이 부르는 `load_dotenv()`(override=False 기본) 는 이미 있는
# 키는 안 건드리지만 **없는 키는 `.env` 값을 넣는다**. 그러니 여기서 "지우기"가 아니라
# 알려진 스위치를 빈 값으로 **선점**해야 뒤이은 load_dotenv 가 못 덮는다.
# 빈 값의 의미: backends/__init__ 은 빈 값을 `DEFAULT_BACKEND`(anthropic)로 폴백,
# ollama_backend 는 `== "1"` 비교라 빈 값은 꺼짐, intent_router 는 rules 로 떨어진다.
_TEST_SAFE_SWITCHES = (
    "AGENT_CHAT_BACKEND",
    "AGENT_SUMMARY_BACKEND",
    "AGENT_INTENT_ROUTER",
    "AGENT_CHAT_MODEL",
    "AGENT_SUMMARY_MODEL",
    "OLLAMA_CHAT_STRUCTURED",
    "OLLAMA_THINK",
    "OLLAMA_CHAT_MODEL",
    "OLLAMA_SUMMARY_MODEL",
    "OLLAMA_NUM_PREDICT",
    "OLLAMA_KEEP_ALIVE",
    # 2026-09-04 추가: 로컬 `.env` 에 이 키가 있으면 백엔드가 "사용 가능"으로
    # 보이지만 CI 에는 없어 503 으로 갈린다. 이 갈림 때문에 로컬 초록·CI 빨강
    # 사고가 났다 (d4580e2 로 사후 복구). 여기서 빈 값으로 선점해 로컬·CI
    # 동작을 맞춘다. 실제 키가 필요한 테스트는 `patch.dict` 로 자체 세팅.
    "ANTHROPIC_API_KEY",
)
for _key in _TEST_SAFE_SWITCHES:
    os.environ[_key] = ""

# `.env` 는 **여기서** 읽는다 — `app.db` 를 import 하기 전에.
#
# `app/db.py` 는 import 되는 순간 `os.getenv("DATABASE_URL", "…5432/arda")` 로 URL 을
# 고정하는데, `load_dotenv()` 는 `app/main.py` 에만 있어서 pytest 경로에서는 아예
# 불리지 않았다. 그래서 `.env` 에 다른 포트를 적어 둬도 무시되고 5432 로 붙는다.
# 그 자리에 네이티브 PostgreSQL 이 앉아 있는 PC 는 옛 스키마의 다른 `arda` DB 로
# 붙어 `users.is_active 칼럼 없음` 으로 수백 개가 error 가 났다 (2026-09-07 수택 보고).
# `08-local-setup.md` 에 함정으로 적어 뒀는데도 밟혔다 — 사람 기억에 맡기지 않고
# 코드로 막는다.
#
# **선점 루프 뒤에 부르는 것이 핵심이다.** `override=False`(기본) 라 위에서 빈 값으로
# 잡아 둔 스위치는 `.env` 가 못 덮는다. 새로 들어오는 것은 `DATABASE_URL` 처럼
# 선점하지 않은 키뿐이라, 로컬 초록·CI 빨강이 갈리던 조건은 그대로 유지된다.
from pathlib import Path  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from datetime import UTC, datetime  # noqa: E402
from uuid import uuid4  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.db import DATABASE_URL, Base, pgvector_ready  # noqa: E402
from app.models import Application, JobPosting, User  # noqa: E402


@pytest.fixture()
def db():
    """트랜잭션 격리 DB 세션. 테스트 끝나면 자동 롤백."""
    engine = create_engine(DATABASE_URL, future=True)
    # main.py lifespan 과 같은 판단: pgvector 확장이 없는 서버에서 vector 타입
    # 테이블을 만들려 들면 CREATE 가 실패해 **나머지 테이블까지 못 만든다** —
    # 그러면 DB 테스트가 통째로 죽는다. 확장이 없으면 그 테이블만 건너뛴다.
    tables = list(Base.metadata.sorted_tables)
    if not pgvector_ready():
        tables = [t for t in tables if t.name != "application_embeddings"]
    Base.metadata.create_all(engine, tables=tables)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
    engine.dispose()


@pytest.fixture()
def admin_user(db: Session) -> User:
    user = User(
        email="test-admin@fixture.local",
        password_hash="hashed",
        name="관리자",
        role="admin",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def member_user(db: Session) -> User:
    """일반 멤버. 배정과 무관한 쪽을 볼 때 쓴다 (ADR-0017)."""
    user = User(
        email="test-member@fixture.local",
        password_hash="hashed",
        name="멤버",
        role="member",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def interviewer_user(db: Session) -> User:
    """면접관으로 배정되는 멤버.

    이름을 그대로 두는 이유는 컬럼명 interviewer_id 와 같다 — "면접관"은 역할이
    아니라 그 건에서 맡은 자리다. 역할 값은 member 다 (ADR-0017).
    """
    user = User(
        email="test-interviewer@fixture.local",
        password_hash="hashed",
        name="면접관",
        role="member",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def posting(db: Session, admin_user: User) -> JobPosting:
    p = JobPosting(
        title="백엔드 개발자",
        description="Python, FastAPI 경험자",
        status="open",
        created_by=admin_user.id,
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture()
def application(db: Session, posting: JobPosting) -> Application:
    # 이름에 꼬리를 붙여 **매 실행마다 고유**하게 만든다. 고정값 "김도현" 이면
    # 시드 더미를 넣어 둔 로컬 DB 에서 같은 이름이 둘이 되고, 이름으로 찾는
    # 경로가 "여러 명이 있어요" 로 빠져 `TestDirectHandlerStageRule` 세 개가
    # 깨진다. CI 는 빈 DB 라 통과해서 **더미를 넣은 사람만** 밟았다
    # (2026-09-07 수택 보고 · 재현 확인).
    #
    # 이름을 쓰는 test 는 `application.name` 을 참조한다 — 여기 값을 바꿔도
    # 따라오게. 리터럴로 적으면 같은 함정이 다시 생긴다.
    app = Application(
        job_posting_id=posting.id,
        name=f"김도현-{uuid4().hex[:6]}",
        email="test-dohyun@fixture.local",
        phone="010-1234-5678",
        education="서울대 컴공",
        career_years=3,
        skills=["Python", "FastAPI", "AWS"],
        current_stage="applied",
        privacy_agreed_at=datetime.now(UTC),
        source="form",
    )
    db.add(app)
    db.flush()
    return app
