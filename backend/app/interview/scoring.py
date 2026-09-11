"""면접 AI 채점 (ADR-0034) — 답변 대조 + 진위 일관성 → interview_sessions.ai_score.

면접이 `done` 이 되면 백그라운드에서 한 번 돈다. 두 재료:
- 답변 대조: 전사(Q/A)를 공고 요건·우대·인재상과 대조해 LLM 이 0~100 (prompts/interview_score).
- 진위 일관성: 실시간 판정이 세션에 쌓아 둔 집계({"n","truth_sum"})의 평균 truth_pct.
  표본이 없으면 답변 점수만으로 100 환산(screening.interview_score_from).

면접관 점수는 여기 들어가지 않는다 — 팀장 결정(면접관은 코멘트만).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app import screening
from app.company import get_profile
from app.models import Application, InterviewSession, JobPosting
from app.ports.output.interview_repository import InterviewRepository
from app.adapter.outbound.pg.application_pg_repository import PgApplicationRepository
from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository
from app.adapter.outbound.pg.interview_pg_repository import PgInterviewRepository

logger = logging.getLogger(__name__)


def record_truth_sample(db: Session, session: InterviewSession, truth_pct: float) -> None:
    """실시간 판정 한 건을 집계에 더한다. **개별 값은 남기지 않는다.**"""
    current = dict(session.truth_samples or {})
    current["n"] = int(current.get("n") or 0) + 1
    current["truth_sum"] = float(current.get("truth_sum") or 0.0) + float(truth_pct)
    session.truth_samples = current  # JSON 컬럼은 재대입해야 변경이 잡힌다
    db.commit()


def _transcript_text(session: InterviewSession) -> str:
    lines: list[str] = []
    for t in session.turns:
        answer = (t.transcript or "").strip() or "(답변 없음 — 전사 없음)"
        lines.append(f"Q{t.seq}. {t.question}\nA: {answer}")
    return "\n\n".join(lines) if lines else "(질문·답변 없음)"


def score_interview(db: Session, session_id: int) -> int | None:
    """세션 하나를 채점해 저장한다. 커밋한다. 점수를 못 내면 None(재시도 대상)."""
    session = PgInterviewRepository(db).get_session(session_id)
    if session is None or session.status != "done":
        return None
    application = PgApplicationRepository(db).get(session.application_id)
    posting = PgHiringRepository(db).get_posting(application.job_posting_id) if application else None
    if application is None or posting is None:
        return None

    from app.agent.backends import get_summary_backend
    from app.agent.prompts import render
    from app.agent.summarizer import _call_llm, _parse_json

    profile = get_profile(db)
    talent = (profile.talent_profile or "").strip() or "인재상 정보 없음"
    requirements = "\n".join(p for p in (posting.description, posting.requirements) if p) or "요건 정보 없음"
    preferred = (posting.preferred or "").strip() or "우대 정보 없음"

    answers_score: int | None = None
    parsed: dict = {}
    prompt_tag = None
    backend = get_summary_backend()
    reason = backend.unavailable_reason()
    if reason:
        logger.error("면접 채점 백엔드 사용 불가: %s", reason)
    else:
        try:
            text, prompt_tag = render(
                "interview_score",
                posting_title=posting.title,
                posting_requirements=requirements,
                posting_preferred=preferred,
                talent_profile=talent,
                profile_summary=application.ai_summary or "요약 없음",
                transcript=_transcript_text(session),
            )
            raw, _, _, cost, stop = _call_llm(backend, text, "interview_score")
            parsed = _parse_json(raw, "interview_score", application.id, stop) or {}
            value = parsed.get("answers_score")
            if isinstance(value, (int, float)):
                answers_score = max(0, min(100, int(round(value))))
        except Exception:
            logger.exception("면접 답변 채점 실패: session_id=%s", session_id)

    truth = screening.truth_consistency(session.truth_samples)
    w = screening.weights(db)
    ai = screening.interview_score_from(answers_score, truth, w)

    session.ai_score = ai
    session.ai_score_detail = {
        "answers": answers_score,
        "truth": truth,
        "truth_n": (session.truth_samples or {}).get("n", 0),
        "per_question": parsed.get("per_question", []),
        "strengths": parsed.get("strengths", []),
        "concerns": parsed.get("concerns", []),
        "weights": {"itv_answers": w["itv_answers"], "itv_truth": w["itv_truth"]},
        "prompt": prompt_tag,
        "model": backend.model_tag() if not reason else None,
    }
    session.scored_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(
        "interview_scored",
        extra={"session_id": session_id, "ai_score": ai, "answers": answers_score, "truth": truth},
    )
    return ai


def score_interview_bg(session_id: int) -> None:
    """FastAPI BackgroundTasks 용 — 자체 세션. 실패는 로그만(면접 종료는 이미 성공)."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        score_interview(db, session_id)
    except Exception:
        logger.exception("백그라운드 면접 채점 실패: session_id=%s", session_id)
    finally:
        db.close()


def latest_interview_score(
    db: Session,
    application_id: int,
    *,
    interview_repo: InterviewRepository | None = None,
) -> int | None:
    """지원자의 가장 최근 끝난 면접의 AI 점수. 없으면 None.

    조회는 `InterviewRepository` 로 위임한다 (ADR-0035 Phase 3a). `interview_repo`
    를 넣으면 그것을 쓰고, 없으면 Postgres 구현으로 기본값. 프로덕션 호출자는 그대로.
    """
    if interview_repo is None:
        from app.adapter.outbound.pg.interview_pg_repository import (
            PgInterviewRepository,
        )

        interview_repo = PgInterviewRepository(db)

    return interview_repo.latest_ai_score_for_application(application_id)


def _json_safe(value) -> str:
    return json.dumps(value, ensure_ascii=False)
