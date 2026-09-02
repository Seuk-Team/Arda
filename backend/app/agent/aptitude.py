"""사전 성향 설문 — 통계 계산 + AI 관찰 요약 (ADR-0027).

통계는 코드가 계산하고 LLM 은 재서술 한 문단만 쓴다. **LLM 이 죽어도 통계
표는 뜬다** — 요약은 부가물이지 관문이 아니다. 유형 판정·점수는 만들지
않는다 (ADR-0027 결정 3, 프롬프트에도 같은 규칙이 박혀 있다).
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.aptitude_questions import CATEGORY_LABELS, LIKERT_LABELS, QUESTIONS_BY_KEY
from app.models import AptitudeAnswer, AptitudeSession

logger = logging.getLogger(__name__)

SUMMARY_MAX_TOKENS = 500

_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {"observation": {"type": "string"}},
    "required": ["observation"],
}


def compute_stats(answers: list[AptitudeAnswer]) -> list[dict]:
    """카테고리별 평균. 문항 상수에서 빠진 key(옛 응답)는 '기타'로 모은다."""
    by_cat: dict[str, list[int]] = {}
    for a in answers:
        q = QUESTIONS_BY_KEY.get(a.question_key)
        cat = q["category"] if q else "etc"
        by_cat.setdefault(cat, []).append(a.value)

    out = []
    for cat, values in by_cat.items():
        out.append(
            {
                "category": cat,
                "label": CATEGORY_LABELS.get(cat, "기타"),
                "mean": round(sum(values) / len(values), 2),
                "count": len(values),
            }
        )
    # 문항 상수의 카테고리 순서대로 — 실행마다 순서가 흔들리면 화면이 흔들린다
    order = list(CATEGORY_LABELS)
    out.sort(key=lambda s: order.index(s["category"]) if s["category"] in order else 99)
    return out


def generate_aptitude_summary(db: Session, session_id: int) -> str | None:
    """관찰 요약 생성 → 세션에 저장. 실패하면 None (통계만으로 화면이 선다)."""
    session = db.get(AptitudeSession, session_id)
    if session is None or not session.answers:
        logger.warning("요약 대상 없음: aptitude_session_id=%s", session_id)
        return None

    from app.agent.backends import get_summary_backend
    from app.agent.prompts import render

    backend = get_summary_backend()
    reason = backend.unavailable_reason()
    if reason:
        logger.error("성향 설문 요약 불가: %s", reason)
        return None

    stats = compute_stats(list(session.answers))
    stats_text = "\n".join(
        f"- {s['label']}: {s['mean']} ({s['count']}문항)" for s in stats
    )
    answers_text = "\n".join(
        f"- {a.question_text} → {a.value} ({LIKERT_LABELS.get(a.value, a.value)})"
        for a in session.answers
    )

    prompt_text, tag = render(
        "aptitude_summary", category_stats=stats_text, answers=answers_text
    )
    schema = _SUMMARY_SCHEMA if backend.supports_structured_output else None
    result = backend.complete(
        prompt=prompt_text, max_tokens=SUMMARY_MAX_TOKENS, json_schema=schema
    )

    observation = _parse_observation(result.text or "")
    if not observation:
        logger.warning(
            "성향 설문 요약 파싱 실패 (stop=%s): aptitude_session_id=%s",
            result.stop_reason,
            session_id,
        )
        return None

    session.ai_summary = observation
    session.ai_summary_model = f"{backend.model_tag()} {tag}"
    db.commit()
    return observation


def _parse_observation(raw: str) -> str | None:
    """JSON {"observation": ...} 우선, 아니면 원문을 그대로 쓴다.

    로컬은 grammar 로 형식이 강제되지만 클라우드는 아니다 — 형식이 어긋났다고
    멀쩡한 문단을 버리지 않는다 (summarizer `_strip_fences` 와 같은 감각).
    """
    s = raw.strip()
    if s.startswith("```"):
        first_nl = s.index("\n") if "\n" in s else len(s)
        s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    try:
        data = json.loads(s)
        if isinstance(data, dict) and isinstance(data.get("observation"), str):
            return data["observation"].strip() or None
    except json.JSONDecodeError:
        pass
    return s or None


def generate_aptitude_summary_bg(session_id: int) -> None:
    """FastAPI BackgroundTasks 용 — 자체 DB 세션 (generate_summary_bg 와 같은 방식)."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        generate_aptitude_summary(db, session_id)
    except Exception:
        logger.exception("성향 설문 요약 실패: aptitude_session_id=%s", session_id)
    finally:
        db.close()
