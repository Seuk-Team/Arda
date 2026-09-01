"""최초 admin 계정 생성 — 배포 직후 1회 실행.

production 에서는 공개 가입이 잠겨 있어(auth.py signup) 첫 계정을 API 로 만들 수 없다.
서버에 접속할 수 있는 사람만 실행할 수 있는 이 스크립트가 그 부트스트랩이다.

사용:
    ADMIN_PASSWORD=<비밀번호> uv run python scripts/create_admin.py <email> <이름>

비밀번호를 인자가 아니라 환경변수로 받는 이유: 셸 히스토리에 남지 않게.
환경변수도 없으면 프롬프트로 묻는다(입력이 화면에 안 보인다).
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import Base, SessionLocal, engine, pgvector_ready  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("사용법: ADMIN_PASSWORD=<비밀번호> uv run python scripts/create_admin.py <email> <이름>")
        return 1

    email, name = sys.argv[1], sys.argv[2]
    password = os.getenv("ADMIN_PASSWORD") or getpass.getpass("admin 비밀번호: ")
    if len(password) < 8:
        print("비밀번호는 8자 이상이어야 합니다")
        return 1

    # pgvector 확장이 없는 DB 에서는 vector 컬럼 테이블을 만들 수 없다. 그대로 두면
    # CREATE 가 통째로 실패해 **users 테이블조차 안 만들어지고**, 최초 admin 을 못 만든다.
    # 이 스크립트는 "배포 직후 부트스트랩"이라 그 자리에서 막히면 우회로가 없다.
    # main.py lifespan · tests/conftest.py 와 같은 판단이다.
    tables = list(Base.metadata.sorted_tables)
    if not pgvector_ready():
        tables = [t for t in tables if t.name != "application_embeddings"]
        print("pgvector 확장이 없어 임베딩 테이블은 건너뛴다 (시맨틱 검색만 꺼진다)")
    Base.metadata.create_all(engine, tables=tables)

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == email).first():
            print(f"이미 존재하는 이메일입니다: {email}")
            return 1
        db.add(User(email=email, name=name, role="admin", password_hash=hash_password(password)))
        db.commit()
        print(f"admin 생성 완료: {email}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
