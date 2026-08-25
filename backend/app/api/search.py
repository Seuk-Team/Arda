import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, scope_to_viewer
from app.models import STAGES, Application, JobPosting, User
from app.schemas.search import SearchResult

router = APIRouter(prefix="/api/v1/applications", tags=["search"])


@router.get("", response_model=SearchResult)
def search(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = None,
    stage: Annotated[list[str] | None, Query()] = None,
    posting_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    started = time.perf_counter()

    if stage:
        bad = [s for s in stage if s not in STAGES]
        if bad:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, f"알 수 없는 단계: {bad}")

    stmt = select(Application).join(JobPosting)
    if q:
        # 이름 또는 이메일 부분 일치. 검색 범위는 02-api.md 에서 이 둘로 확정돼 있다
        like = f"%{q}%"
        stmt = stmt.where(or_(Application.name.ilike(like), Application.email.ilike(like)))
    if stage:
        stmt = stmt.where(Application.current_stage.in_(stage))
    if posting_id:
        stmt = stmt.where(Application.job_posting_id == posting_id)

    # A3 — 면접관은 본인 배정 건만. total 도 이 뒤에서 세므로 건수·페이지네이션이
    # 함께 좁혀진다 (먼저 세면 "결과 없음인데 총 10만" 같은 화면이 나온다).
    stmt = scope_to_viewer(stmt, user)

    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(
        stmt.order_by(Application.created_at.desc()).limit(limit).offset(offset)
    ).all()

    # 화면이 "0.14초" 처럼 응답 시간을 보여준다. 튜닝 전/후 비교의 기준값이기도 하다
    took_ms = round((time.perf_counter() - started) * 1000, 1)
    return SearchResult(items=rows, total=total, took_ms=took_ms)
