"""지원자 AI 요약 생성 (M2, ADR-0022 프롬프트 체이닝).

3단계 파이프라인: 요약 → 평가 → 추천.
접수 시 1회 자동 생성, 재생성은 명시적 버튼만.
더미 10만 건에는 절대 호출하지 않는다 (ADR-0011 비용 가드).
"""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Application, JobPosting

logger = logging.getLogger(__name__)

# 모델·백엔드 선택은 app.agent.backends 가 한다 (AGENT_SUMMARY_BACKEND /
# AGENT_SUMMARY_MODEL / OLLAMA_SUMMARY_MODEL). 여기서 또 읽으면 둘이 갈라진다.
#
# 한국어 출력은 500 으로는 모자란다 — step1(요지 3~5문장 + 핵심 역량 5 + 경험 3)이
# **매번 정확히 500 에서 잘려** JSON 이 깨졌고, 그 파싱 실패가 "제출물이 부족하다"로
# 저장됐다. 지원자 서류는 멀쩡한데 우리 한도가 작았던 것이다 (2026-09-01).
# 출력 토큰은 실제 생성분만 과금되므로 한도를 넉넉히 잡는 비용은 없다.
SUMMARY_MAX_TOKENS = 1500

_EMPTY = "제출된 내용 없음"

# 3단 체인의 출력 스키마. 문법 제약 디코딩을 지원하는 백엔드(로컬 Ollama `format`)
# 에서만 쓴다. 지원하지 않는 백엔드는 프롬프트로만 JSON 을 요청하고
# _strip_fences + _parse_json 폴백에 기댄다 — 최소 공통 분모로 깎지 않는다.
#
# `maxItems`/`maxLength` 는 팀장의 프롬프트 짧게 다듬기(6905c37) 규격과 같다.
# 프롬프트 규칙만 있으면 로컬 sLLM 이 넘길 여지가 있어 스키마에 겹장으로 강제한다.
_STEP_SCHEMAS: dict[str, dict] = {
    "chain_summarize": {
        "type": "object",
        "properties": {
            "insufficient": {"type": "boolean"},
            "gist": {"type": "string", "maxLength": 160},  # 2문장 이내
            "key_skills": {
                "type": "array", "maxItems": 3,
                "items": {"type": "string", "maxLength": 40},
            },
            "key_experiences": {
                "type": "array", "maxItems": 2,
                "items": {"type": "string", "maxLength": 40},
            },
        },
        "required": ["insufficient", "gist", "key_skills", "key_experiences"],
    },
    "chain_evaluate": {
        "type": "object",
        "properties": {
            "fit_score": {"type": "integer", "minimum": 1, "maximum": 5},
            "fit": {
                "type": "array", "maxItems": 2,
                "items": {"type": "string", "maxLength": 40},
            },
            "concerns": {
                "type": "array", "maxItems": 2,
                "items": {"type": "string", "maxLength": 40},
            },
        },
        "required": ["fit_score", "fit", "concerns"],
    },
    "chain_recommend": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "maxLength": 20},
            "reasons": {
                "type": "array", "maxItems": 2,
                "items": {"type": "string", "maxLength": 40},
            },
            "check_points": {
                "type": "array", "maxItems": 2,
                "items": {"type": "string", "maxLength": 40},
            },
        },
        "required": ["action", "reasons", "check_points"],
    },
}


def _build_prompt_vars(db: Session, app: Application) -> dict[str, str]:
    """프롬프트에 필요한 공통 변수를 만든다.

    이력서·자기소개서 **파일**의 텍스트도 여기서 합친다 (extractor.py).
    추출이 실패하면 기존처럼 폼 필드만으로 돈다 — 파일 하나 때문에
    요약이 통째로 빠지는 것보다 낫다.
    """
    from app.agent.extractor import extract_text

    posting = db.get(JobPosting, app.job_posting_id)
    posting_title = posting.title if posting else "공고 정보 없음"
    posting_requirements = (posting.description or "요건 정보 없음") if posting else "요건 정보 없음"

    profile_parts: list[str] = []
    if app.name:
        profile_parts.append(f"이름: {app.name}")
    if app.education:
        profile_parts.append(f"학력: {app.education}")
    if app.career_years is not None:
        profile_parts.append(f"경력: {app.career_years}년")
    if app.skills:
        profile_parts.append(f"기술 스택: {', '.join(app.skills)}")

    # 종류별 첫 파일만 쓴다 — 접수 흐름(C2)상 종류별 1개가 정상이다
    resume_file_text: str | None = None
    cover_file_text: str | None = None
    for f in app.files:
        if f.kind == "resume" and resume_file_text is None:
            resume_file_text = extract_text(f)
        elif f.kind == "cover_letter" and cover_file_text is None:
            cover_file_text = extract_text(f)

    if resume_file_text:
        profile_parts.append(f"\n[이력서 파일 내용]\n{resume_file_text}")
    resume_text = "\n".join(profile_parts) if profile_parts else _EMPTY

    cover_parts = [p for p in (app.self_intro, cover_file_text) if p]
    cover_letter_text = "\n\n".join(cover_parts) if cover_parts else _EMPTY

    return {
        "posting_title": posting_title,
        "posting_requirements": posting_requirements,
        "resume_text": resume_text,
        "cover_letter_text": cover_letter_text,
    }


def _call_llm(
    backend, prompt_text: str, step_name: str
) -> tuple[str, int, int, float, str | None]:
    """LLM 1회 호출. (응답 텍스트, input_tokens, output_tokens, cost_usd, stop_reason) 반환.

    문법 제약 디코딩을 지원하는 백엔드면 스키마를 강제하고, 아니면 스키마 없이
    부른 뒤 기존 파싱 폴백을 그대로 쓴다.

    `stop_reason` 을 함께 돌려주는 이유: 한도에서 잘린 응답은 JSON 이 깨져 파싱에
    실패하는데, 그것을 그냥 "파싱 실패"로만 보면 **원인이 안 보인다.** 잘림은
    프롬프트 문제가 아니라 우리 예산 문제라 대응이 다르다.
    """
    schema = _STEP_SCHEMAS.get(step_name) if backend.supports_structured_output else None
    result = backend.complete(
        prompt=prompt_text,
        max_tokens=SUMMARY_MAX_TOKENS,
        json_schema=schema,
    )
    return (
        result.text.strip(),
        result.input_tokens,
        result.output_tokens,
        result.cost_usd,
        result.stop_reason,
    )


def _strip_fences(raw: str) -> str:
    """LLM이 코드펜스로 감싼 경우 벗긴다."""
    s = raw.strip()
    if s.startswith("```"):
        first_nl = s.index("\n") if "\n" in s else len(s)
        s = s[first_nl + 1 :]
    if s.endswith("```"):
        s = s[: -3]
    return s.strip()


def _parse_json(
    raw: str, step: str, application_id: int, stop_reason: str | None = None
) -> dict | None:
    """JSON 파싱. 코드펜스가 있으면 벗기고 시도한다. 실패하면 None."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        if stop_reason == "max_tokens":
            # 프롬프트가 아니라 한도 문제다. 둘을 같은 로그로 뭉개면 다음 사람이
            # 프롬프트를 고치며 시간을 버린다.
            logger.error(
                "응답이 max_tokens 에서 잘려 JSON 이 깨졌다 (step=%s): "
                "application_id=%d — SUMMARY_MAX_TOKENS 를 올려야 한다",
                step,
                application_id,
            )
        else:
            logger.warning(
                "JSON 파싱 실패 (step=%s): application_id=%d", step, application_id
            )
        return None


def generate_summary(db: Session, application_id: int) -> str | None:
    """3단계 파이프라인으로 AI 요약을 생성하고 DB에 저장한다."""
    app = db.get(Application, application_id)
    if app is None:
        logger.warning("요약 대상 없음: application_id=%d", application_id)
        return None

    prompt_vars = _build_prompt_vars(db, app)

    from app.agent.prompts import render

    from app.agent.backends import get_summary_backend

    backend = get_summary_backend()
    reason = backend.unavailable_reason()
    if reason:
        logger.error(reason)
        return None

    model_tag = backend.model_tag()
    total_input = 0
    total_output = 0
    total_cost = 0.0
    prompt_tags: list[str] = []

    # ── Step 1: 요약 ──
    try:
        step1_text, step1_tag = render(
            "chain_summarize",
            resume_text=prompt_vars["resume_text"],
            cover_letter_text=prompt_vars["cover_letter_text"],
        )
        prompt_tags.append(step1_tag)
        raw1, in1, out1, cost1, stop1 = _call_llm(backend, step1_text, "chain_summarize")
        total_input += in1
        total_output += out1
        total_cost += cost1
    except Exception:
        logger.exception("Step1 실패: application_id=%d", application_id)
        return None

    step1 = _parse_json(raw1, "step1", application_id, stop1)

    # **우리가 못 읽은 것과 지원자 서류가 부족한 것은 다르다.** 파싱 실패를
    # insufficient 로 저장하면 화면에 "제출물이 부족하다"는 **거짓 진술**이 남고,
    # 값이 채워졌으니 재생성 대상에서도 빠진다. 실패는 미생성(NULL)으로 둔다.
    if step1 is None:
        logger.error("요약 1단계 파싱 실패로 저장하지 않는다: application_id=%d", application_id)
        return None

    if step1.get("insufficient"):
        summary_json = json.dumps(
            {"insufficient": True, "gist": "", "fit": [], "concerns": []},
            ensure_ascii=False,
        )
        app.ai_summary = summary_json
        app.ai_summary_at = datetime.now(UTC)
        app.ai_summary_model = f"{model_tag}/{'+'.join(prompt_tags)}"
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
        raw2, in2, out2, cost2, stop2 = _call_llm(backend, step2_text, "chain_evaluate")
        total_input += in2
        total_output += out2
        total_cost += cost2
    except Exception:
        logger.exception("Step2 실패: application_id=%d", application_id)
        return None

    step2 = _parse_json(raw2, "step2", application_id, stop2)
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
        raw3, in3, out3, cost3, stop3 = _call_llm(backend, step3_text, "chain_recommend")
        total_input += in3
        total_output += out3
        total_cost += cost3
    except Exception:
        logger.exception("Step3 실패: application_id=%d", application_id)
        return None

    step3 = _parse_json(raw3, "step3", application_id, stop3)
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

    # 비용은 각 호출에서 백엔드가 계산해 온 것을 합산한다. 여기서 PRICING 표를
    # 다시 조회하면 로컬 모델명이 haiku 단가로 폴백해 없는 요금이 찍힌다.
    cost = total_cost

    app.ai_summary = summary_json
    app.ai_summary_at = datetime.now(UTC)
    app.ai_summary_model = f"{model_tag}/{'+'.join(prompt_tags)}"
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
    """FastAPI BackgroundTasks 용. 자체 DB 세션을 만들어 실행한다.

    요약과 임베딩은 **서로 독립**이다 — 요약이 실패해도 시맨틱 검색을 위한
    임베딩은 만들어져야 하고, 반대도 같다. 두 호출을 각자 try 로 감싸서
    한쪽 실패가 다른 쪽을 삼키지 않게 한다.
    """
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        try:
            generate_summary(db, application_id)
        except Exception:
            logger.exception("백그라운드 요약 실패: application_id=%d", application_id)
        try:
            _generate_embedding(db, application_id)
        except Exception:
            logger.exception("백그라운드 임베딩 실패: application_id=%d", application_id)
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
