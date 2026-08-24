from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_current_user_optional
from app.models import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=http.HTTP_201_CREATED)
def signup(
    body: SignupRequest,
    db: Session = Depends(get_db),
    caller: User | None = Depends(get_current_user_optional),
):
    role = body.role if (caller and caller.role == "admin") else "recruiter"
    row = User(
        email=body.email,
        name=body.name,
        role=role,
        password_hash=hash_password(body.password),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(http.HTTP_409_CONFLICT, "이미 가입된 이메일입니다")
    db.commit()
    return UserOut.model_validate(row)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다")
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, token_type="bearer")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
