from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import Application, InterviewerAssignment, User
from app.schemas.assignment import (
    AssignRequest,
    AssignmentListOut,
    AssignmentOut,
    AssignResponse,
)

router = APIRouter(prefix="/api/v1", tags=["assignments"])

# 배정·해제는 어드민만 한다 — ADR-0013 "모든 배정 권한은 어드민 계정에 있다".
# 역할이 admin·member 둘로 줄어든 뒤에도 이 제한은 그대로다 (ADR-0017).
# 자동 배정(가중 라운드로빈)도 최종 확정은 어드민이 누르는 구조다.
require_admin = require_roles("admin")


@router.post("/applications/{application_id}/interviewers", response_model=AssignResponse)
def assign_interviewers(
    application_id: int,
    body: AssignRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """면접관 배정 (E3). 어드민만 (ADR-0013)."""
    # 지원자 존재 확인
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 대상 사용자 존재 확인. 역할 검사는 없다 — 누구나 면접관으로 배정될 수
    # 있다 (ADR-0017). "면접관"은 역할이 아니라 그 건에서 맡은 자리다.
    users = db.scalars(select(User).where(User.id.in_(body.interviewer_ids))).all()
    if len(users) != len(set(body.interviewer_ids)):
        raise HTTPException(HTTPStatus.NOT_FOUND, "없는 사용자가 있습니다")

    # 같은 사람을 두 번 배정하는 건 실수지 오류가 아니다.
    # UNIQUE 제약을 이용해 조용히 무시한다 (멱등성)
    db.execute(
        pg_insert(InterviewerAssignment)
        .values(
            [
                {
                    "application_id": application_id,
                    "interviewer_id": u.id,
                    # NOT NULL 이다. None 을 넣으면 커밋 시점에 500 이 난다.
                    "assigned_by": user.id,
                }
                for u in users
            ]
        )
        .on_conflict_do_nothing(
            index_elements=["application_id", "interviewer_id"]
        )
    )
    db.commit()

    return AssignResponse(assigned=[u.id for u in users])


@router.get(
    "/applications/{application_id}/interviewers",
    response_model=AssignmentListOut,
)
def list_interviewers(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """배정된 면접관 목록 (E3). 로그인한 사람이면 누구나 (ADR-0017)."""
    # 지원자 존재 확인
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 배정된 면접관 조회
    assignments = db.scalars(
        select(InterviewerAssignment)
        .where(InterviewerAssignment.application_id == application_id)
        .order_by(InterviewerAssignment.created_at.desc())
    ).all()

    return AssignmentListOut(
        items=[AssignmentOut.model_validate(a) for a in assignments],
        count=len(assignments),
    )


@router.delete(
    "/applications/{application_id}/interviewers/{user_id}",
    status_code=HTTPStatus.NO_CONTENT,
)
def unassign_interviewer(
    application_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
):
    """면접관 배정 해제 (E3). 어드민만 — 교체 결정은 어드민 몫이다 (ADR-0013)."""
    # 지원자 존재 확인
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 배정 관계 삭제
    assignment = db.scalar(
        select(InterviewerAssignment)
        .where(InterviewerAssignment.application_id == application_id)
        .where(InterviewerAssignment.interviewer_id == user_id)
    )
    if assignment is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "배정 관계를 찾을 수 없습니다")

    db.delete(assignment)
    db.commit()


@router.get("/interviewers/{user_id}/applications")
def get_assigned_applications(
    user_id: int,
    db: Session = Depends(get_db),
    viewer: User = Depends(get_current_user),
):
    """면접관이 배정받은 지원자 목록. 로그인한 사람이면 누구나 (ADR-0017).

    남의 배정 현황도 열어 둔다 — 지원자 자체를 전원이 볼 수 있게 된 이상,
    "누가 무엇을 맡았는지"만 가려 봐야 배정 조율에 방해만 된다.
    """
    # 사용자 존재 확인
    if db.get(User, user_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "사용자를 찾을 수 없습니다")

    # 배정받은 지원자 조회
    assignments = db.scalars(
        select(InterviewerAssignment)
        .where(InterviewerAssignment.interviewer_id == user_id)
        .order_by(InterviewerAssignment.created_at.desc())
    ).all()

    return {
        "assignments": [AssignmentOut.model_validate(a) for a in assignments],
        "count": len(assignments),
    }
