"""FastAPI 의존성 — 현재 사용자와 접근 제어 (ADR-0017)."""

from fastapi import Depends, HTTPException, status as http
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import InterviewerAssignment, User
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
    # 비활성 계정은 **이미 발급된 토큰도** 막는다 (A4). 로그인에서만 막으면
    # 비활성화한 사람이 토큰 만료(기본 12시간)까지 그대로 쓴다 — 차단이 아니다.
    if not user.is_active:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "비활성화된 계정입니다")
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

    역할은 **admin·member 둘뿐**이다 (ADR-0017). 위계가 아니라 조작 권한의 유무다:

    - **조회는 로그인만 하면 전부 열린다.** 역할로 가리지 않는다.
    - **admin 전용**은 넷뿐이다 — 면접관 배정/해제, 계정 생성, 메일 템플릿,
      *남의* 가용 시간 조작.
    - **member 제한**은 하나뿐 — 평가 작성은 배정된 건만(assert_can_evaluate).
      나머지 조작(공고 CRUD·단계 변경·일괄 변경·일정 제안·에이전트)은 admin 과 같다.

    그래서 실질적으로 `require_roles("admin")` 한 가지로만 쓰인다. 인자를 남겨 두는
    이유는 역할이 다시 늘어날 때 호출부만 고치면 되게 하기 위함이다.

    인증 실패는 401(get_current_user), 역할 부족은 403 으로 나눈다.
    """

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(http.HTTP_403_FORBIDDEN, "권한이 없습니다")
        return user

    return dependency


# ── 평가 작성 제한 ────────────────────────────────────────────────────
# 조회 제한(구 A3 — 면접관은 배정된 지원자만 조회)은 폐지됐다 (ADR-0017).
# 전원이 내부 직원이고, 남의 건을 못 보게 막은 탓에 "왜 안 보이냐"는 문의와
# 화면 분기만 늘었다. 남은 배정 기반 제한은 **평가 작성 하나뿐**이다 —
# 평가는 면접을 본 사람이 남기는 기록이라 배정과 묶어야 의미가 지켜진다.


def is_assigned_interviewer(db: Session, user: User, application_id: int) -> bool:
    """그 지원자의 면접관으로 배정돼 있는가."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    InterviewerAssignment.application_id == application_id,
                    InterviewerAssignment.interviewer_id == user.id,
                )
            )
        )
    )


def assert_can_evaluate(db: Session, user: User, application_id: int) -> None:
    """평가 작성 권한을 확인한다. admin 은 무제한, member 는 배정된 건만.

    404 로 숨기지 않는 이유: 지원자 자체는 누구나 조회할 수 있으므로 감출 것이
    없고, 403 이 "왜 못 쓰는지"를 바로 알려준다.
    """
    if user.role == "admin":
        return
    if not is_assigned_interviewer(db, user, application_id):
        raise HTTPException(
            http.HTTP_403_FORBIDDEN, "본인에게 배정된 지원자만 평가할 수 있습니다"
        )
