"""FastAPI 의존성 — 현재 사용자와 접근 제어 (A3)."""

from fastapi import Depends, HTTPException, status as http
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, exists, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, InterviewerAssignment, User
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


# ── A3 지원자 접근 제어 ──────────────────────────────────────────────
# 면접관은 본인이 배정된 지원자만 볼 수 있다 (02-api.md · 01-erd.md).
# admin·recruiter 는 전부 볼 수 있다.
#
# 규칙을 각 엔드포인트에 흩어 쓰면 새 엔드포인트가 생길 때마다 빠뜨린다.
# 목록/검색은 쿼리를 좁히는 쪽(scope_to_viewer)으로, 단건은 확인하는 쪽
# (assert_can_view_application)으로 나눠 두 함수만 기억하면 되게 한다.


def _assigned_application_ids(user: User) -> Select:
    return select(InterviewerAssignment.application_id).where(
        InterviewerAssignment.interviewer_id == user.id
    )


def scope_to_viewer(stmt: Select, user: User) -> Select:
    """Application 을 고르는 SELECT 에 A3 제한을 건다.

    면접관이 아니면 그대로 돌려준다. 목록·검색에서 쓴다 — 못 보는 건은 애초에
    결과에 담기지 않으므로 건수·페이지네이션도 자동으로 맞는다.
    """
    if user.role != "interviewer":
        return stmt
    return stmt.where(Application.id.in_(_assigned_application_ids(user)))


def assert_can_view_application(db: Session, user: User, application_id: int) -> None:
    """단건 조회 권한을 확인한다. 배정되지 않았으면 403.

    404 로 숨기지 않는 이유: 이용자가 전부 내부 직원이라 지원서의 존재 자체를
    감출 필요가 없고, 403 이 "왜 안 보이는지"를 담당자에게 바로 알려준다.
    """
    if user.role != "interviewer":
        return
    assigned = db.scalar(
        select(
            exists().where(
                InterviewerAssignment.application_id == application_id,
                InterviewerAssignment.interviewer_id == user.id,
            )
        )
    )
    if not assigned:
        raise HTTPException(
            http.HTTP_403_FORBIDDEN, "본인에게 배정된 지원자만 조회할 수 있습니다"
        )
