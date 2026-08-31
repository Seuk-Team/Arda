"""비밀번호 해시·검증 + JWT 인코드/디코드."""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

# 배포 환경 구분. 이 값 하나가 개발 편의 장치(기본 시크릿·공개 가입)를 켜고 끈다.
# **정확히 "dev" 일 때만 개발 동작이다. 미설정·오타는 전부 production 으로 잠근다** (#122).
# 전에는 기본값이 "dev" 라 fail-open 이었다 — 배포에서 APP_ENV 주입을 빠뜨리면 게이트
# 두 개가 조용히 꺼진 채 **정상 기동해서** 배포는 성공한 것처럼 보이고 공개 가입이 열렸다.
# 오타(`prod`·`Production`)도 같은 구멍이었다. 이제 그 경우 전부 잠기는 쪽으로 떨어진다.
#
# 그래서 **개발 환경은 APP_ENV=dev 를 명시해야 한다** — `backend/.env`(.env.example 참고),
# 루트 `docker-compose.yml`, `tests/conftest.py` 에 각각 들어 있다.
APP_ENV = "dev" if os.getenv("APP_ENV", "").strip() == "dev" else "production"

JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    if APP_ENV == "production":
        # 기본값으로 서명하면 누구나 토큰을 위조할 수 있다. 잘못 뜨느니 안 뜬다.
        raise RuntimeError(
            "JWT_SECRET 이 설정되지 않았습니다 — production 에서는 기동하지 않습니다. "
            "로컬 개발이라면 APP_ENV=dev 를 설정한다 (미설정은 production 으로 잠긴다, #122)"
        )
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
