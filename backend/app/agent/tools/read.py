"""읽기 도구 구현 (M3). 확인 없이 바로 실행.

기존 API 서비스 레이어를 재사용한다 — 별도 경로를 만들지 않는다 (agent.md §4).
도구는 DB 세션과 사용자 컨텍스트를 받아, 기존 API와 같은 권한 검사를 거친다.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.deps import scope_to_viewer
from app.models import Application, Evaluation, JobPosting, User


def search_applications(
    db: Session, user: User, params: dict
) -> list[dict]:
    """지원자 통합 검색. 에이전트의 핵심 도구 — 16개 시나리오 중 14개에서 호출."""
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

    stmt = scope_to_viewer(stmt, user)

    sort = params.get("sort", "created_at")
    order = params.get("order", "desc")
    limit = min(int(params.get("limit", 50)), 200)

    if sort == "score":
        avg_score = func.avg(Evaluation.score).label("avg_score")
        stmt = (
            select(Application, avg_score)
            .outerjoin(Evaluation, Evaluation.application_id == Application.id)
            .group_by(Application.id)
        )
        # 필터 재적용 (select를 다시 만들었으므로)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(
                or_(Application.name.ilike(like), Application.email.ilike(like))
            )
        if stage:
            stmt = stmt.where(Application.current_stage.in_(stage))
        if posting_id:
            stmt = stmt.where(Application.job_posting_id == int(posting_id))
        stmt = scope_to_viewer(stmt, user)

        # 평가 없는 지원자(avg NULL)는 항상 뒤로 — Postgres DESC 기본이 NULLS FIRST 라
        # 그대로 두면 "점수 높은 순"에서 미평가자가 맨 위에 온다
        avg_expr = func.avg(Evaluation.score)
        order_expr = avg_expr.desc() if order == "desc" else avg_expr.asc()
        stmt = stmt.order_by(order_expr.nullslast(), Application.id.desc())
        rows = db.execute(stmt.limit(limit)).all()
        return [
            _app_to_dict(row[0]) | {"avg_score": round(float(row.avg_score), 1) if row.avg_score else None}
            for row in rows
        ]

    direction = Application.created_at.desc if order == "desc" else Application.created_at.asc
    stmt = stmt.order_by(direction(), Application.id.desc())
    apps = db.scalars(stmt.limit(limit)).all()
    return [_app_to_dict(a) for a in apps]


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
