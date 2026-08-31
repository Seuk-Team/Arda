"""읽기 도구 구현 (M3). 확인 없이 바로 실행.

기존 API 서비스 레이어를 재사용한다 — 별도 경로를 만들지 않는다 (agent.md §4).
도구는 DB 세션과 사용자 컨텍스트를 받아, 기존 API와 같은 권한 검사를 거친다.
"""

from __future__ import annotations

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


def search_applications(
    db: Session, user: User, params: dict
) -> list[dict]:
    """지원자 통합 검색. 에이전트의 핵심 도구 — 16개 시나리오 중 14개에서 호출."""
    # 검색 결과는 도구 결과로 컨텍스트에 들어간 뒤 이후 모든 라운드에 재전송된다.
    # 기본 50건은 그것만으로 수천 토큰이라, 실제로 필요한 만큼만 가져온다.
    limit = min(int(params.get("limit", 10)), 50)

    # ── 시맨틱 검색: semantic 파라미터가 있으면 벡터 유사도 검색 ──
    semantic = params.get("semantic")
    if semantic:
        from app.agent.embedder import search_similar

        similar_ids = search_similar(db, semantic, limit=limit)
        if not similar_ids:
            return []
        stmt = (
            select(Application)
            .where(Application.id.in_(similar_ids))
        )
        stage = params.get("stage")
        if stage:
            if isinstance(stage, str):
                stage = [stage]
            stmt = stmt.where(Application.current_stage.in_(stage))
        posting_id = params.get("posting_id")
        if posting_id:
            stmt = stmt.where(Application.job_posting_id == int(posting_id))
        apps = db.scalars(stmt).all()
        id_order = {aid: i for i, aid in enumerate(similar_ids)}
        apps.sort(key=lambda a: id_order.get(a.id, len(similar_ids)))
        return [_app_to_dict(a) | {"search_type": "semantic"} for a in apps]

    # ── 기존 ILIKE 검색 ──
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
