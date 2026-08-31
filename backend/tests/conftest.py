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

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.db import DATABASE_URL, Base  # noqa: E402
from app.models import Application, JobPosting, User  # noqa: E402


@pytest.fixture()
def db():
    """트랜잭션 격리 DB 세션. 테스트 끝나면 자동 롤백."""
    engine = create_engine(DATABASE_URL, future=True)
    Base.metadata.create_all(engine)
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
    app = Application(
        job_posting_id=posting.id,
        name="김도현",
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
