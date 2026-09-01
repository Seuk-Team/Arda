"""사용자 관리 API (A4) — 설정 화면 "사용자·권한" 탭의 데이터 소스.

계정 **생성**은 여기가 아니라 기존 `POST /auth/signup` 이다 (ADR-0017, admin 전용).
화면의 "사용자 추가"도 그것을 부른다 — 같은 일을 하는 경로를 둘로 만들지 않는다.

**삭제가 없다.** `users.id` 는 `created_by`·`evaluator_id`·`assigned_by`·
`changed_by` 로 도처에 박혀 있어 물리 삭제가 이력을 부순다. 비활성화가 그 자리를
대신한다.
"""

from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import User
from app.schemas.user import UserItemOut, UserListOut, UserPatch

router = APIRouter(prefix="/api/v1", tags=["users"])


@router.get("/users", response_model=UserListOut)
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """사용자 목록. 로그인한 사람이면 누구나 (ADR-0017 — 조회는 열려 있다).

    화면이 admin 전용이라 목록도 admin 전용으로 두고 싶어지지만, 그러면 면접관
    배정·담당자 표시처럼 "이름을 보여줘야 하는" 다른 화면이 각자 우회로를 판다.
    """
    rows = db.scalars(select(User).order_by(User.id)).all()
    return UserListOut(
        items=[UserItemOut.model_validate(r) for r in rows], count=len(rows)
    )


def _active_admin_count(db: Session, exclude_id: int | None = None) -> int:
    query = select(func.count(User.id)).where(
        User.role == "admin", User.is_active.is_(True)
    )
    if exclude_id is not None:
        query = query.where(User.id != exclude_id)
    return db.scalar(query) or 0


@router.patch("/users/{user_id}", response_model=UserItemOut)
def update_user(
    user_id: int,
    body: UserPatch,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
):
    """역할·활성 변경. admin 전용 (ADR-0017 — 계정 관리는 admin 넷 중 하나).

    **활성 admin 을 0 명으로 만드는 변경은 409 다.** 강등이든 비활성화든, 자기
    자신이든 남이든 같은 규칙이다 — "자기 강등 금지"로 쪼개면 admin 이 둘일 때의
    정당한 조작까지 막고, 정작 마지막 한 명을 남이 강등하는 경로는 열려 있다.
    막아야 하는 것은 **아무도 admin 이 아닌 상태**뿐이다.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "사용자를 찾을 수 없습니다")

    new_role = body.role if body.role is not None else target.role
    new_active = body.is_active if body.is_active is not None else target.is_active

    was_active_admin = target.role == "admin" and target.is_active
    will_be_active_admin = new_role == "admin" and new_active
    if was_active_admin and not will_be_active_admin:
        if _active_admin_count(db, exclude_id=target.id) == 0:
            raise HTTPException(
                HTTPStatus.CONFLICT,
                "마지막 관리자입니다 — 다른 관리자를 먼저 지정하세요",
            )

    target.role = new_role
    target.is_active = new_active
    db.commit()
    db.refresh(target)
    return UserItemOut.model_validate(target)
