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


# 시연 잠금 계정 (박제 온프레미스 · 2026-09-16). 쉼표로 구분한 이메일 목록.
# 여기 든 계정은 **비밀번호 변경(PATCH /auth/me)·역할/활성 변경(PATCH /users/{id})이 403** 이다.
# 심사위원이 로그인 화면의 "담당자 데모 로그인" 버튼으로 들어오는 계정이라, 누구든 한 번 바꾸면
# 이후 모든 심사위원의 자동 로그인이 막힌다. 비우면(기본) 아무 계정도 잠기지 않는다.
DEMO_LOCKED_EMAILS: frozenset[str] = frozenset(
    e.strip().lower() for e in os.getenv("DEMO_LOCKED_EMAILS", "").split(",") if e.strip()
)


def is_demo_locked(email: str | None) -> bool:
    return bool(email) and email.strip().lower() in DEMO_LOCKED_EMAILS


# 심사위원이 "지원자 데모 로그인" 버튼으로 공유해 쓰는 지원자 계정. 로그인할 때마다
# 그 지원자의 인적성·면접일정·AI면접 상태를 기준(fresh)으로 되돌려, 앞 심사위원이
# 끝내 놓아도 다음 심사위원이 세 화면을 처음부터 볼 수 있게 한다. 여기 든 이메일만
# 리셋되고 실제 지원자는 건드리지 않는다. 비우면(기본) 아무도 리셋되지 않는다.
DEMO_APPLICANT_EMAILS: frozenset[str] = frozenset(
    e.strip().lower() for e in os.getenv("DEMO_APPLICANT_EMAILS", "").split(",") if e.strip()
)


def is_demo_applicant(email: str | None) -> bool:
    return bool(email) and email.strip().lower() in DEMO_APPLICANT_EMAILS


def hash_password(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def verify_password(raw: str, hashed: str) -> bool:
    return bcrypt.checkpw(raw.encode(), hashed.encode())


# 토큰 종류. **같은 비밀키로 서명하므로 이 값이 유일한 구분선이다.**
#
# 지원자 토큰이 직원 토큰으로 통하면 지원자가 남의 지원서를 전부 보게 된다.
# `get_current_user` 는 예전에 `sub` 로 User 를 찾기만 했으므로, 지원자 토큰의
# `sub` 가 우연히 어떤 User 의 id 와 같기만 해도 그 사람이 됐다.
# 그래서 **토큰마다 종류를 박고 양쪽에서 종류를 확인한다** (deps.py).
TYP_STAFF = "staff"
TYP_APPLICANT = "applicant"

# 지원자 토큰은 짧게 둔다. 비밀번호가 생년월일이라 유출 시 되돌릴 방법이 없고,
# 지원자가 하는 일(현황 확인)은 오래 열어 둘 이유가 없다.
APPLICANT_EXPIRES_MINUTES = 60 * 2


def create_access_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": TYP_STAFF,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_applicant_token(email: str) -> str:
    """지원자용. **`sub` 가 이메일이지 User id 가 아니다.**

    지원자는 `users` 행이 없다. 한 사람이 여러 공고에 지원할 수 있으므로
    지원서 id 가 아니라 이메일로 묶는다 — 로그인 한 번으로 자기 지원 전부를 본다.
    """
    return jwt.encode(
        {
            "sub": email,
            "typ": TYP_APPLICANT,
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=APPLICANT_EXPIRES_MINUTES),
        },
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
