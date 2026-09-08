"""FastAPI 의존성 — 현재 사용자와 접근 제어 (ADR-0017)."""

from fastapi import Depends, HTTPException, status as http
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import InterviewerAssignment, User
from app.security import TYP_APPLICANT, TYP_STAFF, decode_access_token

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
    # **지원자 토큰을 여기서 막는다.** 아래는 `sub` 로 User 를 찾을 뿐이라,
    # 종류를 안 보면 지원자 토큰의 sub 가 어떤 User 의 id 와 같기만 해도
    # 그 사람이 된다. 같은 키로 서명하므로 서명 검증은 이걸 못 막는다.
    if payload.get("typ") != TYP_STAFF:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "유효하지 않은 토큰입니다")
    try:
        user = db.get(User, int(payload["sub"]))
    except (TypeError, ValueError):
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "유효하지 않은 토큰입니다")
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


# ── 지원자 인증 ────────────────────────────────────────────────────────
# 지원자는 `users` 행이 없다. 직원과 **완전히 다른 축**이라 의존성을 따로 둔다 —
# 하나로 합치면 어느 한쪽 분기를 빠뜨렸을 때 조용히 권한이 넘어간다.


def get_current_applicant_email(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    """지원자 토큰에서 이메일을 꺼낸다. DB 를 보지 않는다 — 무엇을 볼지는 부르는 쪽이 정한다."""
    if creds is None:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    try:
        payload = decode_access_token(creds.credentials)
    except Exception:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "다시 로그인해 주세요")
    # 직원 토큰으로 지원자 경로를 타는 것도 막는다. 통과시키면 직원의 이메일과
    # 같은 주소로 지원한 사람의 지원서가 열린다.
    if payload.get("typ") != TYP_APPLICANT:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "다시 로그인해 주세요")
    email = payload.get("sub")
    if not isinstance(email, str) or not email:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "다시 로그인해 주세요")
    return email
