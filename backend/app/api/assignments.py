from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, InterviewerAssignment, User
from app.schemas.assignment import (
    AssignRequest,
    AssignmentListOut,
    AssignmentOut,
    AssignResponse,
)

router = APIRouter(prefix="/api/v1", tags=["assignments"])


@router.post("/applications/{application_id}/interviewers", response_model=AssignResponse)
def assign_interviewers(
    application_id: int, body: AssignRequest, db: Session = Depends(get_db)
):
    """면접관 배정 (E3)."""
    # 지원자 존재 확인
    if db.get(Application, application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 면접관 존재 및 role 확인
    users = db.scalars(select(User).where(User.id.in_(body.interviewer_ids))).all()
    if len(users) != len(set(body.interviewer_ids)):
        raise HTTPException(HTTPStatus.NOT_FOUND, "없는 사용자가 있습니다")

    # 면접관 역할 검증
    bad = [u.id for u in users if u.role != "interviewer"]
    if bad:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            f"면접관이 아닌 사용자입니다: {bad}",
        )

    # 같은 사람을 두 번 배정하는 건 실수지 오류가 아니다.
    # UNIQUE 제약을 이용해 조용히 무시한다 (멱등성)
    db.execute(
        pg_insert(InterviewerAssignment)
        .values(
            [
                {
                    "application_id": application_id,
                    "interviewer_id": u.id,
                    "assigned_by": None,  # TODO(A1): 토큰의 사용자로 채운다
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
    application_id: int, db: Session = Depends(get_db)
):
    """배정된 면접관 목록 (E3)."""
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
    application_id: int, user_id: int, db: Session = Depends(get_db)
):
    """면접관 배정 해제 (E3)."""
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
def get_assigned_applications(user_id: int, db: Session = Depends(get_db)):
    """면접관이 배정받은 지원자 목록 (A3가 쓸 경로)."""
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
