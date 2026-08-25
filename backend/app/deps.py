"""FastAPI 의존성 — 현재 사용자."""

from fastapi import Depends, HTTPException, status as http
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import User
from app.security import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "인증이 필요합니다")
    try:
        payload = decode_access_token(creds.credentials)
    except Exception:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "유효하지 않은 토큰입니다")
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "유효하지 않은 토큰입니다")
    return user


def get_current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if creds is None:
        return None
    try:
        return get_current_user(creds, db)
    except HTTPException:
        return None


def require_roles(*allowed: str):
    """지정한 역할만 통과시키는 의존성을 만든다.

    역할 위계는 admin > recruiter > interviewer (02-api.md). 상속을 코드로 두지 않고
    허용 역할을 그때그때 나열한다 — 위계가 세 단계뿐이고, 나열하는 편이 각 엔드포인트에서
    누가 통과하는지 바로 보인다.

    인증 실패는 401(get_current_user), 역할 부족은 403 으로 나눈다.
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(http.HTTP_403_FORBIDDEN, "권한이 없습니다")
        return user

    return dependency
