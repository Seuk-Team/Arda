"""지원자 AI 요약 생성 (M2, ADR-0022 프롬프트 체이닝).

3단계 파이프라인: 요약 → 평가 → 추천.
접수 시 1회 자동 생성, 재생성은 명시적 버튼만.
더미 10만 건에는 절대 호출하지 않는다 (ADR-0011 비용 가드).
"""

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import Application
from app.adapter.outbound.pg.application_pg_repository import PgApplicationRepository
from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

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
            # v2 신설: 이력서·자소서 근무 기간에서 추출한 경력 연수. 폼 값이 비었을 때 채운다.
            # 정확한 규칙은 chain_summarize.v2.md 를 본다. 서류에서 못 세면 null.
            "career_years": {"type": ["integer", "null"], "minimum": 0, "maximum": 60},
        },
        "required": ["insufficient", "gist", "key_skills", "key_experiences"],
    },
    # chain_evaluate.v2 (ADR-0034) 의 출력 모양. **프롬프트와 같이 고친다** — 2026-09-15 까지
    # v1 모양(fit_score 1~5)으로 남아 있었고, 스키마를 강제하는 백엔드(Ollama `format`)에서는
    # 모델이 세 갈래 점수를 낼 수 없어 doc_score 가 fit_score×20 폴백(20점 단위)으로 떨어졌다.
    # Claude 는 스키마를 무시해(anthropic_backend.supports_structured_output=False) 드러나지 않았다.
    "chain_evaluate": {
        "type": "object",
        "properties": {
            "requirements_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "preferred_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "culture_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "fit": {
                "type": "array", "maxItems": 3,
                "items": {"type": "string", "maxLength": 40},
            },
            "concerns": {
                "type": "array", "maxItems": 3,
                "items": {"type": "string", "maxLength": 40},
            },
            "evidence": {
                "type": "array", "maxItems": 3,
                "items": {"type": "string", "maxLength": 200},
            },
        },
        "required": ["requirements_score", "preferred_score", "culture_score", "fit", "concerns"],
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

    posting = PgHiringRepository(db).get_posting(app.job_posting_id)
    posting_title = posting.title if posting else "공고 정보 없음"
    # 요건 = description + requirements(0013). 둘 다 비면 "정보 없음" 을 그대로 보여 준다 —
    # 프롬프트가 빈 문장을 요건으로 오해하지 않게. 우대·인재상도 같은 규칙 (ADR-0034).
    req_parts = [p.strip() for p in ((posting.description if posting else None),
                                     (getattr(posting, "requirements", None) if posting else None)) if p and p.strip()]
    posting_requirements = "\n".join(req_parts) if req_parts else "요건 정보 없음"
    posting_preferred = (getattr(posting, "preferred", None) or "").strip() if posting else ""
    posting_preferred = posting_preferred or "우대 정보 없음"
    talent_profile = _talent_profile(db)

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
        "posting_preferred": posting_preferred,
        "talent_profile": talent_profile,
        "resume_text": resume_text,
        "cover_letter_text": cover_letter_text,
    }


def _talent_profile(db: Session) -> str:
    """회사 인재상(company_profile.talent_profile). 없으면 "정보 없음" — 지어내지 않게."""
    try:
        from app.hiring.company import get_profile

        text = (get_profile(db).talent_profile or "").strip()
    except Exception:  # 가짜 DB(테스트)·프로파일 표 없음
        text = ""
    return text or "인재상 정보 없음"


def _clamp_score(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


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


def _fill_structured_fields(
    db: Session, app: Application, backend, resume_text: str
) -> None:
    """이력서 텍스트에서 학력·경력·기술스택을 추출해 비어 있는 DB 필드만 채운다."""
    needs_fill = not app.education or app.career_years is None or not app.skills
    if not needs_fill or not resume_text.strip():
        return

    prompt = (
        "다음은 지원자 이력서 내용이다. 아래 JSON 형식으로 정보를 추출하라.\n"
        "없는 정보는 null로 둔다. career_years는 총 경력 연수(정수, 신입/없으면 0).\n\n"
        f"이력서:\n{resume_text[:3000]}\n\n"
        "JSON만 출력:\n"
        '{"education": "최종학력 문자열 또는 null", "career_years": 0, "skills": ["스킬1"]}'
    )
    try:
        raw = backend.complete(prompt=prompt, max_tokens=300).text
        data = _parse_json(raw.strip(), "extract_fields", app.id)
        if data is None:
            return
        if not app.education and data.get("education"):
            app.education = str(data["education"])[:100]
        if app.career_years is None and data.get("career_years") is not None:
            try:
                app.career_years = max(0, int(data["career_years"]))
            except (TypeError, ValueError):
                pass
        if not app.skills and isinstance(data.get("skills"), list):
            app.skills = [str(s) for s in data["skills"] if s][:20]
        db.commit()
        logger.info("구조화 필드 채움: application_id=%d", app.id)
    except Exception:
        logger.warning("구조화 필드 추출 실패: application_id=%d", app.id)


def generate_summary(db: Session, application_id: int) -> str | None:
    """3단계 파이프라인으로 AI 요약을 생성하고 DB에 저장한다."""
    app = PgApplicationRepository(db).get(application_id)
    if app is None:
        logger.warning("요약 대상 없음: application_id=%d", application_id)
        return None

    from app.agent.prompts import render

    from app.agent.backends import get_summary_backend

    backend = get_summary_backend()
    reason = backend.unavailable_reason()
    if reason:
        logger.error(reason)
        return None

    # 폼에서 학력·경력·기술스택을 입력하지 않은 경우 이력서 파일에서 추출
    if not app.education or app.career_years is None or not app.skills:
        from app.agent.extractor import extract_text
        for f in app.files:
            if f.kind == "resume":
                resume_text = extract_text(f)
                if resume_text:
                    _fill_structured_fields(db, app, backend, resume_text)
                break

    prompt_vars = _build_prompt_vars(db, app)

    model_tag = backend.model_tag()
    total_input = 0
    total_output = 0
    total_cost = 0.0
    prompt_tags: list[str] = []

    # ── Step 1: 요약 ──
    try:
        # 백엔드가 로컬 어댑터(Ollama)면 v1 프롬프트를 명시적으로 로드한다.
        # 오늘 학습한 요약 어댑터는 chain_summarize.v1 gold 기반이라 v2 의 career_years
        # 필드를 낼 학습을 안 했다. Anthropic 은 최신(v2)로 그대로 · career_years 채워진다.
        # 어댑터 v2 gold 재학습 없이 서빙 스위치 가능하도록 (2026-09-17).
        summarize_version = 1 if getattr(backend, "name", None) == "ollama" else None
        step1_text, step1_tag = render(
            "chain_summarize",
            version=summarize_version,
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

    # v2 신설: 이력서에서 추출한 경력 연수를 폼 값이 비었을 때만 채운다.
    # 지원자가 폼에 명시적으로 입력한 값이 있으면 그것을 우선 (지원자 의사 존중).
    # AI 가 null 을 반환하면 폼 값도 건드리지 않는다.
    # 이전 재생성이 AI 로 채웠는지 (2026-09-17 우정 PR #294 재확인 지적).
    # 첫 재생성: career_years=None → AI 값 채움 → source="ai" 저장.
    # 두 번째 재생성: career_years 이미 채워짐 → filled_from_ai=False → detail 재작성 시
    #   source 필드가 빠져 신고값으로 보이게 됐다. 이전 표시를 이어받아 방지한다.
    prev_source = (app.doc_score_detail or {}).get("career_years_source")

    career_years_filled_from_ai = False
    if app.career_years is None:
        # 폼 값이 비었으면 AI 값을 처음 채운다.
        ai_years = step1.get("career_years")
        if isinstance(ai_years, int) and 0 <= ai_years <= 60:
            app.career_years = ai_years
            career_years_filled_from_ai = True
            logger.info(
                "career_years_filled_from_summary",
                extra={"application_id": application_id, "value": ai_years},
            )
    elif prev_source == "ai":
        # 이전에 AI 로 채운 값이 있으면 AI 가 다시 세는 값으로 갱신한다 (우정 제안).
        # 이력서·자소서가 갱신되면 새 AI 값이 더 정확할 수 있다. 폼 값이 신고값이면
        # source 표식이 없어 이 갈래에 안 들어온다 — 지원자 의사는 여전히 우선.
        ai_years = step1.get("career_years")
        if isinstance(ai_years, int) and 0 <= ai_years <= 60 and ai_years != app.career_years:
            logger.info(
                "career_years_updated_from_summary",
                extra={"application_id": application_id, "before": app.career_years, "after": ai_years},
            )
            app.career_years = ai_years
            career_years_filled_from_ai = True

    # ── Step 2: 평가 — 요건·우대·인재상 세 갈래 100점 (chain_evaluate v2, ADR-0034) ──
    try:
        step2_text, step2_tag = render(
            "chain_evaluate",
            posting_title=prompt_vars["posting_title"],
            posting_requirements=prompt_vars["posting_requirements"],
            posting_preferred=prompt_vars["posting_preferred"],
            talent_profile=prompt_vars["talent_profile"],
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
        step2 = {"fit": [], "concerns": []}

    # 세 갈래 → 서류 100점(회사 가중치) → 옛 화면용 1~5점은 100점에서 내려 만든다.
    # v1 응답(fit_score 만 있음)이 와도 죽지 않게 fit_score 를 먼저 살린다.
    from app.application import screening

    parts = {
        "requirements": _clamp_score(step2.get("requirements_score")),
        "preferred": _clamp_score(step2.get("preferred_score")),
        "culture": _clamp_score(step2.get("culture_score")),
    }
    doc_score = screening.doc_score_from(parts, screening.weights(db))
    legacy_fit = step2.get("fit_score")
    if doc_score is not None:
        fit_score = max(1, min(5, int(round(doc_score / 20)) or 1))
    elif isinstance(legacy_fit, (int, float)):
        fit_score = int(legacy_fit)
        doc_score = max(0, min(100, int(round(float(legacy_fit) * 20))))
    else:
        fit_score = None
    step2["fit_score"] = fit_score

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
        "career_years": step1.get("career_years"),  # v2 신설 · null 이면 폼 값도 없음
        "fit_score": step2.get("fit_score"),
        "doc_score": doc_score,
        "scores": parts,
        "fit": step2.get("fit", []),
        "concerns": step2.get("concerns", []),
        "evidence": step2.get("evidence", []),
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
    # 자동 심사 재료 (ADR-0034). 판정(단계 이동)은 generate_summary_bg 가 이어서 한다 —
    # 여기서 하면 요약 테스트가 가짜 DB 로 단계까지 옮기려 든다.
    app.doc_score = doc_score
    detail: dict = {
        **parts,
        "fit": step2.get("fit", []),
        "concerns": step2.get("concerns", []),
        "evidence": step2.get("evidence", []),
        "weights": {k: v for k, v in screening.weights(db).items() if k.startswith("doc_")},
    }
    # AI 가 채운 career_years 는 출처를 남긴다 (우정 리뷰 #294 제안).
    # 프론트가 "N년 (AI 추정)" 으로 표시하고 · 아르 검색 도구가 신고값과 구별하고 · 공정성
    # 질문 때 근거로 쓴다. 폼 값이 있었으면 이 필드는 안 붙어 "신고값" 이 기본 가정이다.
    # 이번 세션에 AI 로 채웠거나 · 이전에 AI 로 채운 표시가 있었다면 이어받는다.
    # 이래야 두 번째 재생성에서 detail 이 새로 쓰여도 "ai" 표식이 유지된다 (우정 지적).
    if career_years_filled_from_ai or prev_source == "ai":
        detail["career_years_source"] = "ai"
    app.doc_score_detail = detail
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
        summary = None
        try:
            summary = generate_summary(db, application_id)
        except Exception:
            logger.exception("백그라운드 요약 실패: application_id=%d", application_id)
        try:
            _generate_embedding(db, application_id)
        except Exception:
            logger.exception("백그라운드 임베딩 실패: application_id=%d", application_id)
        # 자동 심사 (ADR-0034) — 점수가 나왔을 때만. 요약이 없으면 사람이 본다.
        if summary is not None:
            try:
                from app.application import screening

                app = PgApplicationRepository(db).get(application_id)
                if app is not None:
                    screening.decide_document(db, app)
            except Exception:
                logger.exception("백그라운드 자동 심사 실패: application_id=%d", application_id)
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
