"""비밀번호 해시·검증 + JWT 인코드/디코드."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

# 배포 환경 구분. EC2 에서는 반드시 "production" 으로 둔다 — 이 값으로
# 개발 편의 장치(기본 시크릿·공개 가입)를 끈다.
APP_ENV = os.getenv("APP_ENV", "dev")

JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    if APP_ENV == "production":
        # 기본값으로 서명하면 누구나 토큰을 위조할 수 있다. 잘못 뜨느니 안 뜬다.
        raise RuntimeError("JWT_SECRET 이 설정되지 않았습니다 — production 에서는 기동하지 않습니다")
    JWT_SECRET = "dev-secret-change-me"
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = 60 * 12


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode(), hashed.encode())


def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
