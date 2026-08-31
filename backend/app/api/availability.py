"""면접관 가용 시간 API — 일정 자동화(ADR-0016)의 1단계.

면접관이 "면접 가능한 시간대"를 등록하면, 담당자의 제안 생성이 여기서
후보 슬롯을 뽑는다.

권한 (ADR-0017): 읽기는 로그인한 사람 전체(제안을 만들려면 봐야 한다).
쓰기·삭제는 본인 또는 admin — **남의 가용 시간을 다루는 것은 admin 전용**이다.
본인 것은 역할과 무관하게 누구나 등록·삭제한다.
"""

from datetime import datetime, timezone
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import InterviewerAvailability, User
from app.schemas.availability import (
    AvailabilityCreate,
    AvailabilityListOut,
    AvailabilityOut,
)

router = APIRouter(prefix="/api/v1", tags=["availability"])


def _assert_target_exists(db: Session, user_id: int) -> User:
    """대상 사용자가 존재하는지 확인한다.

    역할 검사는 없다 — 누구나 면접관으로 배정될 수 있으므로(ADR-0017)
    누구의 가용 시간이든 의미가 있다.
    """
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "사용자를 찾을 수 없습니다")
    return target


@router.post(
    "/interviewers/{user_id}/availability",
    response_model=AvailabilityOut,
    status_code=HTTPStatus.CREATED,
)
def create_availability(
    user_id: int,
    body: AvailabilityCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """가용 시간 등록. 본인 또는 admin (ADR-0017).

    - 과거 시간은 422 — 지난 시간은 후보 슬롯이 될 수 없어 데이터만 오염시킨다.
    - 겹치는 구간은 막지 않는다 — 중복 정리는 후보 슬롯 생성 한 곳에서 한다.
      등록 시점에 병합·거부를 넣으면 UX 만 까다로워진다.
    """
    if actor.id != user_id and actor.role != "admin":
        raise HTTPException(HTTPStatus.FORBIDDEN, "본인의 가용 시간만 등록할 수 있습니다")
    _assert_target_exists(db, user_id)

    if body.end_at <= datetime.now(timezone.utc):
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY, "이미 지난 시간대는 등록할 수 없습니다"
        )

    row = InterviewerAvailability(
        interviewer_id=user_id, start_at=body.start_at, end_at=body.end_at
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return AvailabilityOut.model_validate(row)


@router.get(
    "/interviewers/{user_id}/availability",
    response_model=AvailabilityListOut,
)
def list_availability(
    user_id: int,
    from_at: datetime | None = Query(None, alias="from", description="이 시각 이후 종료분만"),
    to_at: datetime | None = Query(None, alias="to", description="이 시각 이전 시작분만"),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """가용 시간 목록. 로그인한 사람이면 누구나 (ADR-0017).

    기간 필터는 "구간이 조회 범위와 겹치는가" 기준이다 — from 은 end_at 과,
    to 는 start_at 과 비교해야 경계에 걸친 구간이 빠지지 않는다.
    """
    _assert_target_exists(db, user_id)

    query = (
        select(InterviewerAvailability)
        .where(InterviewerAvailability.interviewer_id == user_id)
        .order_by(InterviewerAvailability.start_at)
    )
    if from_at is not None:
        query = query.where(InterviewerAvailability.end_at > from_at)
    if to_at is not None:
        query = query.where(InterviewerAvailability.start_at < to_at)

    rows = db.scalars(query).all()
    return AvailabilityListOut(
        items=[AvailabilityOut.model_validate(r) for r in rows], count=len(rows)
    )


@router.delete("/availability/{availability_id}", status_code=HTTPStatus.NO_CONTENT)
def delete_availability(
    availability_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """가용 시간 삭제. 본인 또는 admin (ADR-0017).

    물리 삭제다 — 이미 나간 제안의 슬롯은 스냅샷(schedule_slots)이라
    여기를 지워도 지원자가 보는 선택지는 바뀌지 않는다.
    """
    row = db.get(InterviewerAvailability, availability_id)
    if row is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "가용 시간을 찾을 수 없습니다")
    if actor.id != row.interviewer_id and actor.role != "admin":
        raise HTTPException(HTTPStatus.FORBIDDEN, "본인의 가용 시간만 삭제할 수 있습니다")

    db.delete(row)
    db.commit()
