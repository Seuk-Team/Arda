"""읽기 도구 구현 (M3). 확인 없이 바로 실행.

기존 API 서비스 레이어를 재사용한다 — 별도 경로를 만들지 않는다 (agent.md §4).
도구는 DB 세션과 사용자 컨텍스트를 받아, 기존 API와 같은 권한 검사를 거친다.
"""

from __future__ import annotations

import logging
import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Application,
    Evaluation,
    InterviewerAvailability,
    JobPosting,
    ScheduleProposal,
    ScheduleSlot,
    User,
)


# ── 시맨틱 검색어에서 키워드를 뽑는 규칙 ─────────────────────────────
# 벡터 검색이 죽어 있어도 "Python 경험자" 는 찾아져야 한다. 자연어 질의에서
# 검색에 쓸 만한 낱말만 남기고 조사·상투어를 버린다. 형태소 분석기를 붙이지
# 않은 이유: 의존성 하나 더 늘리는 값에 비해, 역량 검색어의 신호는 대부분
# 영문 기술어(Python, AWS)와 두 글자 이상 한글 명사에 실려 있다.
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#.]*|[가-힣]{2,}")
_STOPWORDS = {
    "경험", "경험자", "경력", "사람", "지원자", "개발자", "이상", "이하", "미만",
    "있는", "있으신", "있고", "가진", "찾아줘", "찾아", "찾기", "보여줘", "알려줘",
    "누구", "관련", "가능", "필요", "정도", "해본", "다루는", "쓰는", "출신",
    "and", "or", "the", "with", "of", "in", "for",
}

logger = logging.getLogger(__name__)


def _keywords(text: str) -> list[str]:
    """자연어 질의에서 검색 키워드를 뽑는다. 순서 유지, 중복 제거."""
    out: list[str] = []
    for token in _TOKEN.findall(text or ""):
        if len(token) < 2 or token.lower() in _STOPWORDS:
            continue
        if token.lower() not in {t.lower() for t in out}:
            out.append(token)
    return out


def _keyword_filter(keywords: list[str]):
    """키워드 OR 조건. 이름·이메일뿐 아니라 스킬·자기소개서·학력까지 본다.

    ADR-0021 은 ILIKE 를 "이름·이메일" 로만 적었지만, 그 범위로는 역량 검색에
    아무것도 걸리지 않아 병합의 한쪽이 항상 빈다 (보고서의 ADR 차이 항목).
    """
    clauses = []
    for kw in keywords:
        like = f"%{kw}%"
        clauses.append(
            or_(
                Application.name.ilike(like),
                Application.email.ilike(like),
                Application.education.ilike(like),
                Application.self_intro.ilike(like),
                func.array_to_string(Application.skills, ",").ilike(like),
            )
        )
    return or_(*clauses)


def _keyword_hits(app: Application, keywords: list[str]) -> int:
    """이 지원자가 몇 개의 키워드에 걸렸는지 — 키워드 결과 정렬에 쓴다."""
    haystack = " ".join(
        filter(
            None,
            [
                app.name or "",
                app.email or "",
                app.education or "",
                app.self_intro or "",
                ", ".join(app.skills or []),
            ],
        )
    ).lower()
    return sum(1 for kw in keywords if kw.lower() in haystack)


def _skill_exact_hits(app: Application, keywords: list[str]) -> int:
    """스킬 배열에 키워드가 **exact 원소** 로 몇 개 들어있는지 (대소문자 무시).

    직무·기술 어휘(Python, Kubernetes, FastAPI…) 는 임베딩보다 exact match 가
    확실한 신호다. 더미 실측(2026-09-02): "Kubernetes 경험" 질의에 벡터가 React
    개발자를 상위에 올리는데, 정작 skills 에 "Kubernetes" 를 정확히 가진 지원자는
    임계값 밖으로 밀리거나 rank 3(keyword only) 으로 뒤에 붙었다. 이 함수는
    그런 사람을 rank 0 으로 끌어올려, 랭킹에서 semantic 만인 오답을 이긴다.

    `_keyword_hits` 는 self_intro·education 같은 자연어 필드까지 훑는 substring
    이라 신호가 흐리다("교육" 안의 "육" 은 아니지만 "python-교육생" 은 잡힘).
    여기서는 **skills 배열의 각 원소와 완전 일치** 만 세서 오탐을 낮춘다.
    """
    if not app.skills or not keywords:
        return 0
    skills_lower = {s.lower() for s in app.skills}
    return sum(1 for kw in keywords if kw.lower() in skills_lower)


def _semantic_search(db: Session, user: User, params: dict, limit: int) -> dict:
    """벡터 + 키워드 하이브리드 검색 (ADR-0021 결과 병합).

    벡터 검색이 불가능하거나(pgvector·모델·임베딩 없음) 임계값 안에 아무것도
    없으면 **키워드 검색으로 내려앉고 그 사실을 note 로 알린다.** 조용히 빈
    리스트를 반환하면 아르가 "지원자가 없습니다" 라고 단정한다.
    """
    from app.agent.embedder import MAX_DISTANCE, EmbeddingUnavailable, search_similar

    semantic = params["semantic"]
    keywords = _keywords(semantic)

    stage = params.get("stage")
    if isinstance(stage, str):
        stage = [stage]
    posting_id = params.get("posting_id")
    # 단계·공고 필터는 벡터 검색 뒤에 걸리므로 그만큼 넉넉히 뽑아둔다.
    fetch_limit = limit * 3 if (stage or posting_id) else limit

    distances: dict[int, float] = {}
    degraded: str | None = None
    try:
        distances = dict(search_similar(db, semantic, limit=fetch_limit))
    except EmbeddingUnavailable as exc:
        degraded = exc.reason
    except Exception:  # 벡터 검색이 터져도 검색 자체는 살아 있어야 한다
        logger.exception("벡터 검색 실패 — 키워드 검색으로 대체")
        degraded = "시맨틱 검색 중 오류가 발생했습니다"
        # **rollback 이 없으면 폴백이 통째로 500 이 된다.** PG 는 실패한 문장 하나로
        # 트랜잭션 전체를 abort 시키므로, 바로 아래 키워드 쿼리가
        # InFailedSqlTransaction 으로 터진다. "pgvector 파이썬 패키지는 있는데 DB
        # 확장은 없는" 상태(= 2026-08-31 운영)에서 실제로 재현된다:
        # application_embeddings 테이블이 없어 SELECT 가 죽고 → 폴백도 죽는다.
        db.rollback()

    stmt = select(Application)
    conditions = []
    if distances:
        conditions.append(Application.id.in_(list(distances)))
    if keywords:
        conditions.append(_keyword_filter(keywords))
    if not conditions:
        # 벡터도 못 쓰고 뽑을 키워드도 없다 — 검색어 자체가 조사·상투어뿐이다.
        return {
            "results": [],
            "count": 0,
            "search_mode": "keyword_fallback" if degraded else "semantic",
            "note": (
                f"검색어 '{semantic}' 에서 쓸 만한 키워드를 뽑지 못했습니다. "
                "기술명·직무명을 넣어 다시 시도해 주세요."
                + (f" (시맨틱 검색 불가: {degraded})" if degraded else "")
            ),
        }
    stmt = stmt.where(or_(*conditions))
    if stage:
        stmt = stmt.where(Application.current_stage.in_(stage))
    if posting_id:
        stmt = stmt.where(Application.job_posting_id == int(posting_id))

    apps = list(db.scalars(stmt.limit(fetch_limit)).all())

    rows = []
    for app in apps:
        distance = distances.get(app.id)
        hits = _keyword_hits(app, keywords) if keywords else 0
        skill_hits = _skill_exact_hits(app, keywords) if keywords else 0
        # skills exact match 는 최상위 신호 — 있으면 semantic 만인 결과보다 앞선다
        if skill_hits and distance is not None:
            matched_by, rank = "skill+semantic", 0
        elif skill_hits:
            matched_by, rank = "skill_exact", 0
        elif distance is not None and hits:
            matched_by, rank = "both", 1
        elif distance is not None:
            matched_by, rank = "semantic", 2
        elif hits:
            matched_by, rank = "keyword", 3
        else:
            continue
        row = _app_to_dict(app) | {"matched_by": matched_by}
        if distance is not None:
            row["similarity"] = round(1.0 - distance, 3)
        if hits:
            row["keyword_hits"] = hits
        if skill_hits:
            row["skill_hits"] = skill_hits
        rows.append(
            (rank, -skill_hits, distance if distance is not None else 1.0, -hits, row)
        )

    # 정렬: (rank 오름차순, skill_hits 많은 순, 벡터 거리 짧은 순, 키워드 적중 많은 순)
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    results = [r[4] for r in rows][:limit]

    if degraded:
        mode = "keyword_fallback"
        note = (
            f"시맨틱(벡터) 검색을 쓸 수 없어 키워드 검색으로 대체했습니다 — {degraded}. "
            "표현이 다르지만 의미가 비슷한 지원자는 빠질 수 있으니, 결과가 부족하면 "
            "다른 키워드로도 찾아보시라고 안내해 주세요."
        )
    elif not distances:
        mode = "keyword_fallback"
        note = (
            f"유사도 임계값(코사인 거리 {MAX_DISTANCE}) 안에 드는 지원자가 없어 "
            "키워드 검색 결과만 보여줍니다."
        )
    else:
        mode = "semantic+keyword"
        note = None

    if not results and note is None:
        note = "조건에 맞는 지원자를 찾지 못했습니다."

    payload = {"results": results, "count": len(results), "search_mode": mode}
    if note:
        payload["note"] = note
    return payload


def search_applications(db: Session, user: User, params: dict) -> dict:
    """지원자 통합 검색. 에이전트의 핵심 도구 — 16개 시나리오 중 14개에서 호출.

    반환 형태는 항상 dict 다: {"results": [...], "count": n, "search_mode": ...}
    (+ 알릴 것이 있으면 "note"). 검색이 온전히 돌았는지 아르가 알아야 하므로
    리스트만 돌려주지 않는다.
    """
    # 검색 결과는 도구 결과로 컨텍스트에 들어간 뒤 이후 모든 라운드에 재전송된다.
    # 기본 50건은 그것만으로 수천 토큰이라, 실제로 필요한 만큼만 가져온다.
    limit = min(int(params.get("limit", 10)), 50)

    # ── 시맨틱 검색: semantic 파라미터가 있으면 벡터 + 키워드 하이브리드 ──
    if params.get("semantic"):
        return _semantic_search(db, user, params, limit)

    # ── 기존 ILIKE 검색 (이름·이메일) ──
    stmt = select(Application)

    q = params.get("q")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(Application.name.ilike(like), Application.email.ilike(like))
        )

    stage = params.get("stage")
    if stage:
        if isinstance(stage, str):
            stage = [stage]
        stmt = stmt.where(Application.current_stage.in_(stage))

    posting_id = params.get("posting_id")
    if posting_id:
        stmt = stmt.where(Application.job_posting_id == int(posting_id))

    sort = params.get("sort", "created_at")
    order = params.get("order", "desc")

    if sort == "score":
        avg_score = func.avg(Evaluation.score).label("avg_score")
        stmt = (
            select(Application, avg_score)
            .outerjoin(Evaluation, Evaluation.application_id == Application.id)
            .group_by(Application.id)
        )
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(Application.name.ilike(like), Application.email.ilike(like))
            )
        if stage:
            stmt = stmt.where(Application.current_stage.in_(stage))
        if posting_id:
            stmt = stmt.where(Application.job_posting_id == int(posting_id))

        avg_expr = func.avg(Evaluation.score)
        order_expr = avg_expr.desc() if order == "desc" else avg_expr.asc()
        stmt = stmt.order_by(order_expr.nullslast(), Application.id.desc())
        rows = db.execute(stmt.limit(limit)).all()
        results = [
            _app_to_dict(row[0]) | {"avg_score": round(float(row.avg_score), 1) if row.avg_score else None}
            for row in rows
        ]
        return _lexical_payload(results, limit, q)

    direction = Application.created_at.desc if order == "desc" else Application.created_at.asc
    stmt = stmt.order_by(direction(), Application.id.desc())
    apps = db.scalars(stmt.limit(limit)).all()
    return _lexical_payload([_app_to_dict(a) for a in apps], limit, q)


def _lexical_payload(results: list[dict], limit: int, q: str | None) -> dict:
    """이름·이메일 검색 결과를 도구 반환 형태로 감싼다."""
    payload = {
        "results": results,
        "count": len(results),
        "search_mode": "lexical" if q else "all",
    }
    if not results:
        payload["note"] = (
            "이름·이메일에 일치하는 지원자가 없습니다. 역량으로 찾는 것이라면 "
            "semantic 파라미터를 쓰세요."
            if q
            else "지원자가 없습니다."
        )
    elif len(results) == limit:
        payload["note"] = f"결과가 {limit}건에서 잘렸습니다. 더 있을 수 있습니다."
    return payload


def get_application(db: Session, user: User, params: dict) -> dict | None:
    """지원자 상세 조회. 평가·메모·파일·이력을 한 번에 반환."""
    application_id = int(params["application_id"])

    row = db.scalar(
        select(Application)
        .options(
            selectinload(Application.stage_history),
            selectinload(Application.evaluations),
            selectinload(Application.notes),
            selectinload(Application.files),
        )
        .where(Application.id == application_id)
    )
    if row is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}

    scores = [e.score for e in row.evaluations]
    avg = round(sum(scores) / len(scores), 1) if scores else None

    return {
        "id": row.id,
        "name": row.name,
        "email": row.email,
        "phone": row.phone,
        "education": row.education,
        "career_years": row.career_years,
        "skills": row.skills,
        "self_intro": row.self_intro[:200] if row.self_intro else None,
        "ai_summary": row.ai_summary,
        "current_stage": row.current_stage,
        "source": row.source,
        "created_at": row.created_at.isoformat(),
        "avg_score": avg,
        "evaluations": [
            {"evaluator_id": e.evaluator_id, "score": e.score, "comment": e.comment}
            for e in row.evaluations
        ],
        "stage_history": [
            {"from": h.from_stage, "to": h.to_stage, "by": h.changed_by, "at": h.created_at.isoformat()}
            for h in row.stage_history
        ],
        "files": [{"filename": f.filename, "kind": f.kind} for f in row.files],
        "notes_count": len(row.notes),
        "schedule": _get_latest_schedule(db, application_id),
    }


def list_postings(db: Session, user: User, params: dict) -> list[dict]:
    """채용공고 목록 조회. 공고 이름 → posting_id 변환에 쓰인다."""
    rows = db.execute(
        select(JobPosting, func.count(Application.id))
        .outerjoin(Application, Application.job_posting_id == JobPosting.id)
        .group_by(JobPosting.id)
        .order_by(JobPosting.created_at.desc())
    ).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "status": p.status,
            "application_count": n,
            "created_at": p.created_at.isoformat(),
        }
        for p, n in rows
    ]


def _get_latest_schedule(db: Session, application_id: int) -> dict | None:
    """지원자의 최신 일정 제안 요약. get_application 결과에 포함."""
    proposal = db.scalar(
        select(ScheduleProposal)
        .where(ScheduleProposal.application_id == application_id)
        .order_by(ScheduleProposal.created_at.desc())
        .limit(1)
    )
    if proposal is None:
        return None

    result = {"status": proposal.status}
    if proposal.status == "confirmed" and proposal.confirmed_slot_id:
        slot = db.get(ScheduleSlot, proposal.confirmed_slot_id)
        if slot:
            interviewer = db.get(User, slot.interviewer_id)
            result["confirmed_slot"] = {
                "start_at": slot.start_at.isoformat(),
                "end_at": slot.end_at.isoformat(),
                "interviewer_name": interviewer.name if interviewer else None,
            }
    return result


def list_availability(db: Session, user: User, params: dict) -> list[dict]:
    """면접관 가용 시간 조회. 로그인한 사람이면 누구나 (ADR-0017)."""
    interviewer_id = int(params["interviewer_id"])

    target = db.get(User, interviewer_id)
    if target is None:
        return {"error": f"사용자 {interviewer_id}를 찾을 수 없습니다"}

    query = (
        select(InterviewerAvailability)
        .where(InterviewerAvailability.interviewer_id == interviewer_id)
        .order_by(InterviewerAvailability.start_at)
    )

    from_at = params.get("from")
    if from_at:
        from datetime import datetime as dt
        if isinstance(from_at, str):
            from_at = dt.fromisoformat(from_at)
        query = query.where(InterviewerAvailability.end_at > from_at)

    to_at = params.get("to")
    if to_at:
        from datetime import datetime as dt
        if isinstance(to_at, str):
            to_at = dt.fromisoformat(to_at)
        query = query.where(InterviewerAvailability.start_at < to_at)

    rows = db.scalars(query).all()
    return [
        {
            "id": r.id,
            "interviewer_id": r.interviewer_id,
            "start_at": r.start_at.isoformat(),
            "end_at": r.end_at.isoformat(),
        }
        for r in rows
    ]


def get_schedule_status(db: Session, user: User, params: dict) -> dict:
    """지원자의 최신 면접 일정 제안 상태 조회."""
    application_id = int(params["application_id"])

    app = db.get(Application, application_id)
    if app is None:
        return {"error": f"지원자 {application_id}를 찾을 수 없습니다"}

    proposal = db.scalar(
        select(ScheduleProposal)
        .where(ScheduleProposal.application_id == application_id)
        .order_by(ScheduleProposal.created_at.desc())
        .limit(1)
    )
    if proposal is None:
        return {"status": "none", "message": "일정 제안이 없습니다"}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if (
        proposal.status == "proposed"
        and proposal.expires_at is not None
        and proposal.expires_at <= now
    ):
        proposal.status = "expired"
        proposal.updated_at = now
        db.commit()

    result = {
        "status": proposal.status,
        "created_at": proposal.created_at.isoformat(),
    }
    if proposal.expires_at:
        result["expires_at"] = proposal.expires_at.isoformat()

    if proposal.status == "confirmed" and proposal.confirmed_slot_id:
        slot = db.get(ScheduleSlot, proposal.confirmed_slot_id)
        if slot:
            interviewer = db.get(User, slot.interviewer_id)
            result["confirmed_slot"] = {
                "start_at": slot.start_at.isoformat(),
                "end_at": slot.end_at.isoformat(),
                "interviewer_name": interviewer.name if interviewer else None,
            }

    return result


def list_interviews(db: Session, user: User, params: dict) -> list[dict]:
    """확정된 면접 목록 조회. 면접관은 본인 건만."""
    query = (
        select(ScheduleSlot, Application, JobPosting, User)
        .join(ScheduleProposal, ScheduleProposal.confirmed_slot_id == ScheduleSlot.id)
        .join(Application, Application.id == ScheduleProposal.application_id)
        .join(JobPosting, JobPosting.id == Application.job_posting_id)
        .join(User, User.id == ScheduleSlot.interviewer_id)
        .where(ScheduleProposal.status == "confirmed")
        .order_by(ScheduleSlot.start_at)
    )

    from_at = params.get("from")
    if from_at:
        from datetime import datetime as dt
        if isinstance(from_at, str):
            from_at = dt.fromisoformat(from_at)
        query = query.where(ScheduleSlot.start_at >= from_at)

    to_at = params.get("to")
    if to_at:
        from datetime import datetime as dt
        if isinstance(to_at, str):
            to_at = dt.fromisoformat(to_at)
        query = query.where(ScheduleSlot.start_at < to_at)

    # 역할 분기 없음 — mine 은 이제 권한이 아니라 필터다 (ADR-0017)
    if params.get("mine"):
        query = query.where(ScheduleSlot.interviewer_id == user.id)

    rows = db.execute(query).all()
    return [
        {
            "application_id": application.id,
            "applicant_name": application.name,
            "posting_title": posting.title,
            "interviewer_name": interviewer.name,
            "start_at": slot.start_at.isoformat(),
            "end_at": slot.end_at.isoformat(),
        }
        for slot, application, posting, interviewer in rows
    ]


def search_users(db: Session, user: User, params: dict) -> list[dict]:
    """내부 사용자(면접관 등) 검색. 이름·이메일 키워드로 찾는다."""
    limit = min(int(params.get("limit", 20)), 50)

    stmt = select(User)

    q = params.get("q")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(User.name.ilike(like), User.email.ilike(like))
        )

    role = params.get("role")
    if role:
        stmt = stmt.where(User.role == role)

    stmt = stmt.order_by(User.name).limit(limit)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
        }
        for u in rows
    ]


def _app_to_dict(app: Application) -> dict:
    return {
        "id": app.id,
        "name": app.name,
        "email": app.email,
        "current_stage": app.current_stage,
        "career_years": app.career_years,
        "skills": app.skills,
        "created_at": app.created_at.isoformat(),
    }
