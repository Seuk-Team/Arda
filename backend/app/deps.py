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
