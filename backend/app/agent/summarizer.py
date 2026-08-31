"""지원자 AI 요약 생성 (M2, ADR-0022 프롬프트 체이닝).

3단계 파이프라인: 요약 → 평가 → 추천.
접수 시 1회 자동 생성, 재생성은 명시적 버튼만.
더미 10만 건에는 절대 호출하지 않는다 (ADR-0011 비용 가드).
"""

import json
import logging
import os
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Application, JobPosting

logger = logging.getLogger(__name__)

SUMMARY_MODEL = os.getenv("AGENT_SUMMARY_MODEL", "claude-haiku-4-5-20251001")
SUMMARY_MAX_TOKENS = 500

_EMPTY = "제출된 내용 없음"


def _build_prompt_vars(db: Session, app: Application) -> dict[str, str]:
    """프롬프트에 필요한 공통 변수를 만든다."""
    posting = db.get(JobPosting, app.job_posting_id)
    posting_title = posting.title if posting else "공고 정보 없음"
    posting_requirements = (posting.description or "요건 정보 없음") if posting else "요건 정보 없음"

    resume_text = _EMPTY
    cover_letter_text = app.self_intro or _EMPTY

    profile_parts: list[str] = []
    if app.name:
        profile_parts.append(f"이름: {app.name}")
    if app.education:
        profile_parts.append(f"학력: {app.education}")
    if app.career_years is not None:
        profile_parts.append(f"경력: {app.career_years}년")
    if app.skills:
        profile_parts.append(f"기술 스택: {', '.join(app.skills)}")
    if profile_parts:
        resume_text = "\n".join(profile_parts)

    return {
        "posting_title": posting_title,
        "posting_requirements": posting_requirements,
        "resume_text": resume_text,
        "cover_letter_text": cover_letter_text,
    }


def _call_llm(client, prompt_text: str) -> tuple[str, int, int]:
    """LLM 1회 호출. (응답 텍스트, input_tokens, output_tokens) 반환."""
    response = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=SUMMARY_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt_text}],
    )
    raw = response.content[0].text.strip()
    return raw, response.usage.input_tokens, response.usage.output_tokens


def _parse_json(raw: str, step: str, application_id: int) -> dict | None:
    """JSON 파싱. 실패하면 None."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("JSON 파싱 실패 (step=%s): application_id=%d", step, application_id)
        return None


def generate_summary(db: Session, application_id: int) -> str | None:
    """3단계 파이프라인으로 AI 요약을 생성하고 DB에 저장한다."""
    app = db.get(Application, application_id)
    if app is None:
        logger.warning("요약 대상 없음: application_id=%d", application_id)
        return None

    prompt_vars = _build_prompt_vars(db, app)

    from app.agent.prompts import render

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic 패키지 미설치 — uv add anthropic 필요")
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY 미설정")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    total_input = 0
    total_output = 0
    prompt_tags: list[str] = []

    # ── Step 1: 요약 ──
    try:
        step1_text, step1_tag = render(
            "chain_summarize",
            resume_text=prompt_vars["resume_text"],
            cover_letter_text=prompt_vars["cover_letter_text"],
        )
        prompt_tags.append(step1_tag)
        raw1, in1, out1 = _call_llm(client, step1_text)
        total_input += in1
        total_output += out1
    except Exception:
        logger.exception("Step1 실패: application_id=%d", application_id)
        return None

    step1 = _parse_json(raw1, "step1", application_id)
    if step1 is None or step1.get("insufficient"):
        summary_json = json.dumps(
            {"insufficient": True, "gist": "", "fit": [], "concerns": []},
            ensure_ascii=False,
        )
        app.ai_summary = summary_json
        app.ai_summary_at = datetime.now(UTC)
        app.ai_summary_model = f"{SUMMARY_MODEL}/{'+'.join(prompt_tags)}"
        db.commit()
        return summary_json

    # ── Step 2: 평가 ──
    try:
        step2_text, step2_tag = render(
            "chain_evaluate",
            posting_title=prompt_vars["posting_title"],
            posting_requirements=prompt_vars["posting_requirements"],
            profile_summary=json.dumps(step1, ensure_ascii=False),
        )
        prompt_tags.append(step2_tag)
        raw2, in2, out2 = _call_llm(client, step2_text)
        total_input += in2
        total_output += out2
    except Exception:
        logger.exception("Step2 실패: application_id=%d", application_id)
        return None

    step2 = _parse_json(raw2, "step2", application_id)
    if step2 is None:
        step2 = {"fit_score": None, "fit": [], "concerns": []}

    # ── Step 3: 추천 ──
    try:
        step3_text, step3_tag = render(
            "chain_recommend",
            posting_title=prompt_vars["posting_title"],
            evaluation_result=json.dumps(step2, ensure_ascii=False),
        )
        prompt_tags.append(step3_tag)
        raw3, in3, out3 = _call_llm(client, step3_text)
        total_input += in3
        total_output += out3
    except Exception:
        logger.exception("Step3 실패: application_id=%d", application_id)
        return None

    step3 = _parse_json(raw3, "step3", application_id)
    if step3 is None:
        step3 = {"action": None, "reasons": [], "check_points": []}

    # ── 결과 합산 저장 ──
    combined = {
        "insufficient": False,
        "gist": step1.get("gist", ""),
        "key_skills": step1.get("key_skills", []),
        "key_experiences": step1.get("key_experiences", []),
        "fit_score": step2.get("fit_score"),
        "fit": step2.get("fit", []),
        "concerns": step2.get("concerns", []),
        "recommendation": {
            "action": step3.get("action"),
            "reasons": step3.get("reasons", []),
            "check_points": step3.get("check_points", []),
        },
    }
    summary_json = json.dumps(combined, ensure_ascii=False)

    from app.agent.runtime import _estimate_cost

    cost = _estimate_cost(SUMMARY_MODEL, total_input, total_output)

    app.ai_summary = summary_json
    app.ai_summary_at = datetime.now(UTC)
    app.ai_summary_model = f"{SUMMARY_MODEL}/{'+'.join(prompt_tags)}"
    db.commit()

    logger.info(
        "summary_generated",
        extra={
            "application_id": application_id,
            "input_tokens": total_input,
            "output_tokens": total_output,
            "model": app.ai_summary_model,
            "cost_usd": round(cost, 6),
            "pipeline": "chain_v1",
        },
    )
    return summary_json


def generate_summary_bg(application_id: int) -> None:
    """FastAPI BackgroundTasks 용. 자체 DB 세션을 만들어 실행한다."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        generate_summary(db, application_id)
        _generate_embedding(db, application_id)
    except Exception:
        logger.exception("백그라운드 요약 실패: application_id=%d", application_id)
    finally:
        db.close()


def _generate_embedding(db: Session, application_id: int) -> None:
    """임베딩 생성 (ADR-0021). 실패해도 요약에 영향 없음."""
    try:
        from app.agent.embedder import embed_application

        embed_application(db, application_id)
        logger.info("embedding_generated", extra={"application_id": application_id})
    except Exception:
        logger.warning("임베딩 생성 실패 (무시): application_id=%d", application_id)
