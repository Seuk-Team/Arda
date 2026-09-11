"""지원자 통합 검색 (H1·H2) + 정렬·커서 페이지네이션 (H4·H5)."""

import base64
import binascii
import json
import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status as http
from sqlalchemy import Select, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import STAGES, Application, Evaluation, JobPosting, User
from app.schemas.search import ApplicationListItem, SearchResult

router = APIRouter(prefix="/api/v1/applications", tags=["search"])

SORTS = ("created_at", "score")
ORDERS = ("desc", "asc")

# 평가가 없는 지원자를 정렬에서 어디에 둘지 정하는 값. 실제 점수는 1~5 이므로
# 내림차순에서는 -1 이 맨 뒤, 오름차순에서는 100 이 맨 뒤가 된다 → 어느 쪽이든
# "아직 평가 없음"이 끝으로 간다.
#
# NULL 을 그대로 두지 않는 이유: 커서는 (정렬키, id) 튜플 비교로 다음 페이지를
# 찾는데, SQL 에서 NULL 과의 비교는 참도 거짓도 아닌 NULL 이라 조건이 통째로
# 걸러진다. 평가 없는 지원자가 커서 두 번째 페이지부터 통째로 사라진다.
UNRATED_SORT_VALUE = {"desc": -1.0, "asc": 100.0}


def _encode_cursor(sort: str, order: str, value: Any, row_id: int) -> str:
    """커서는 불투명 문자열이다. 클라이언트가 내용을 알 필요도, 만들 필요도 없다.

    sort·order 를 함께 담는 이유: 정렬을 바꾸면 이전 커서의 기준값이 의미를 잃는다.
    그대로 쓰면 조용히 엉뚱한 페이지가 나오므로, 담아 두고 어긋나면 거절한다.
    """
    payload = {"s": sort, "o": order, "v": value, "id": row_id}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def _decode_cursor(cursor: str, sort: str, order: str) -> tuple[Any, int]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor))
        value, row_id = payload["v"], int(payload["id"])
        cursor_sort, cursor_order = payload["s"], payload["o"]
    except (ValueError, KeyError, TypeError, binascii.Error):
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "커서를 해석할 수 없습니다")

    if (cursor_sort, cursor_order) != (sort, order):
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"커서는 정렬 {cursor_sort}/{cursor_order} 기준입니다. "
            f"정렬을 바꾸면 첫 페이지부터 다시 요청하세요",
        )

    # JSON 은 날짜를 모른다. 문자열 그대로 넘기면 Postgres 가
    # "timestamptz < varchar" 를 만나 비교를 거부한다 — 원래 타입으로 되돌린다.
    try:
        value = datetime.fromisoformat(value) if sort == "created_at" else float(value)
    except (TypeError, ValueError):
        raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, "커서를 해석할 수 없습니다")

    return value, row_id


def _seek(stmt: Select, key, cursor_value: Any, cursor_id: int, order: str, aggregated: bool):
    """(정렬키, id) 튜플 비교로 "마지막으로 본 행 다음부터"를 건다.

    id 를 함께 비교하는 이유: 같은 시각(또는 같은 점수)의 행이 여럿이면 정렬키만으로는
    순서가 흔들려 커서가 행을 건너뛰거나 중복시킨다. id 가 최종 tie-breaker 다.

    집계(score) 기준일 때는 WHERE 가 아니라 HAVING 에 걸어야 한다 — 집계 결과는
    그룹이 만들어진 뒤에야 존재한다.
    """
    pair = tuple_(key, Application.id)
    condition = pair < (cursor_value, cursor_id) if order == "desc" else pair > (cursor_value, cursor_id)
    return stmt.having(condition) if aggregated else stmt.where(condition)


@router.get("", response_model=SearchResult)
def search(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: str | None = None,
    stage: Annotated[list[str] | None, Query()] = None,
    posting_id: int | None = None,
    sort: str = Query("created_at"),
    order: str = Query("desc"),
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = None,
    # offset 은 남겨 둔다 — 화면이 아직 쓰고 있을 수 있다. 깊은 페이지에서는 커서를 권장한다.
    offset: int = Query(0, ge=0),
    with_total: bool = Query(
        True,
        description="전체 건수를 셀지. false 면 total 이 null 로 오고 검색이 크게 빨라진다",
    ),
):
    started = time.perf_counter()

    if sort not in SORTS:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY, f"알 수 없는 정렬: {sort} (가능: {', '.join(SORTS)})"
        )
    if order not in ORDERS:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY, f"알 수 없는 정렬 방향: {order} (가능: {', '.join(ORDERS)})"
        )
    if stage:
        bad = [s for s in stage if s not in STAGES]
        if bad:
            raise HTTPException(http.HTTP_422_UNPROCESSABLE_ENTITY, f"알 수 없는 단계: {bad}")

    def apply_filters(stmt: Select) -> Select:
        if q:
            # 이름 또는 이메일 부분 일치. 검색 범위는 02-api.md 에서 이 둘로 확정돼 있다
            like = f"%{q}%"
            stmt = stmt.where(or_(Application.name.ilike(like), Application.email.ilike(like)))
        if stage:
            stmt = stmt.where(Application.current_stage.in_(stage))
        if posting_id:
            stmt = stmt.where(Application.job_posting_id == posting_id)
        # 조회는 로그인한 사람 전체에게 열려 있다 (ADR-0017) — 좁히지 않는다.
        return stmt

    # total 은 커서·offset 을 걸기 전에 센다 — 전체 결과 수이지 이번 페이지 수가 아니다.
    #
    # **이 COUNT 가 검색 API 의 병목이다** (docs/perf-search.md "인덱스로 풀 수 없는 병목").
    # 10만 건 기준 검색 109 ms 중 104 ms 가 여기다. 페이지 조회는 limit 만큼 채우면
    # 멈출 수 있지만 COUNT 는 조건에 맞는 행을 끝까지 세야 해서 멈출 수가 없다.
    # 인덱스로는 못 줄인다 — 그래서 "셀지 말지"를 호출부가 정하게 열어 둔다.
    #
    # 커서로 넘기는 화면은 "총 몇 건"이 필요 없다(다음 페이지 유무는 next_cursor 가 답한다).
    # 그런 화면은 with_total=false 로 부르면 된다.
    total = None
    if with_total:
        total = db.scalar(
            select(func.count()).select_from(apply_filters(select(Application)).subquery())
        )

    aggregated = sort == "score"
    if aggregated:
        # 평가가 없는 지원자가 목록에서 사라지면 안 되므로 outerjoin 이다.
        # 표시용(NULL 유지)과 정렬용(NULL 을 끝으로 보내는 값)을 나눠 뽑는다.
        display_avg = func.avg(Evaluation.score)
        sort_key = func.coalesce(display_avg, UNRATED_SORT_VALUE[order])
        stmt = (
            apply_filters(
                select(Application, display_avg.label("avg_score"))
                .outerjoin(Evaluation, Evaluation.application_id == Application.id)
            )
            .group_by(Application.id)
        )
    else:
        display_avg = None
        sort_key = Application.created_at
        stmt = apply_filters(select(Application).join(JobPosting))

    if cursor:
        value, row_id = _decode_cursor(cursor, sort, order)
        stmt = _seek(stmt, sort_key, value, row_id, order, aggregated)
        offset = 0  # 커서와 offset 이 같이 오면 커서가 이긴다

    direction = (lambda c: c.desc()) if order == "desc" else (lambda c: c.asc())
    stmt = stmt.order_by(direction(sort_key), direction(Application.id))

    # 한 건 더 읽어 "다음 페이지가 있는지"를 판단한다. 따로 count 하지 않아도 된다.
    rows = db.execute(stmt.limit(limit + 1).offset(offset)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    items = []
    for row in rows:
        application = row[0]
        item = ApplicationListItem.model_validate(application)
        if aggregated:
            item.avg_score = float(row.avg_score) if row.avg_score is not None else None
        items.append(item)

    next_cursor = None
    if has_more and rows:
        last_application = rows[-1][0]
        if aggregated:
            raw = rows[-1].avg_score
            last_value = float(raw) if raw is not None else UNRATED_SORT_VALUE[order]
        else:
            last_value = last_application.created_at.isoformat()
        next_cursor = _encode_cursor(sort, order, last_value, last_application.id)

    # 화면이 "0.14초" 처럼 응답 시간을 보여준다. 튜닝 전/후 비교의 기준값이기도 하다
    took_ms = round((time.perf_counter() - started) * 1000, 1)
    return SearchResult(items=items, total=total, took_ms=took_ms, next_cursor=next_cursor)
