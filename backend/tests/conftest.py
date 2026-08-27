"""에이전트 테스트 공용 픽스처.

PostgreSQL 을 그대로 쓰되, 각 테스트를 트랜잭션으로 감싸 롤백한다.
DB 에 흔적이 남지 않으므로 운영 데이터와 섞이지 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import DATABASE_URL, Base
from app.models import Application, JobPosting, User


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
def recruiter_user(db: Session) -> User:
    user = User(
        email="test-recruiter@fixture.local",
        password_hash="hashed",
        name="담당자",
        role="recruiter",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture()
def interviewer_user(db: Session) -> User:
    user = User(
        email="test-interviewer@fixture.local",
        password_hash="hashed",
        name="면접관",
        role="interviewer",
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
