"""지원자 AI 요약 생성 (M2).

접수 시 1회 자동 생성, 재생성은 명시적 버튼만.
더미 10만 건에는 절대 호출하지 않는다 (ADR-0011 비용 가드).

프롬프트: prompts/summarize.v1.md — JSON(gist·fit·concerns) 출력.
ai_summary 컬럼에 JSON 문자열로 저장, 프론트가 파싱해서 표시.
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
    """summarize 프롬프트에 필요한 변수를 만든다."""
    posting = db.get(JobPosting, app.job_posting_id)
    posting_title = posting.title if posting else "공고 정보 없음"
    posting_requirements = (posting.description or "요건 정보 없음") if posting else "요건 정보 없음"

    resume_text = _EMPTY
    cover_letter_text = app.self_intro or _EMPTY

    # 폼 데이터로 이력서 텍스트를 구성한다.
    # 첨부 파일(S3) 추출은 S3 배포 후 추가 예정.
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


def generate_summary(db: Session, application_id: int) -> str | None:
    """AI 요약을 생성하고 DB에 저장한다. 성공하면 JSON 문자열, 실패하면 None."""
    app = db.get(Application, application_id)
    if app is None:
        logger.warning("요약 대상 없음: application_id=%d", application_id)
        return None

    prompt_vars = _build_prompt_vars(db, app)

    from app.agent.prompts import render

    prompt_text, prompt_tag = render("summarize", **prompt_vars)

    try:
        import anthropic
    except ImportError:
        logger.error("anthropic 패키지 미설치 — uv add anthropic 필요")
        return None

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY 미설정")
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=SUMMARY_MODEL,
            max_tokens=SUMMARY_MAX_TOKENS,
            messages=[{"role": "user", "content": prompt_text}],
        )
        raw = response.content[0].text.strip()
    except Exception:
        logger.exception("Claude API 호출 실패: application_id=%d", application_id)
        return None

    # JSON 파싱 검증 — 프롬프트가 JSON을 요구하지만 모델이 깨뜨릴 수 있다
    try:
        parsed = json.loads(raw)
        summary_json = json.dumps(parsed, ensure_ascii=False)
    except json.JSONDecodeError:
        logger.warning("JSON 파싱 실패, 원본 저장: application_id=%d", application_id)
        summary_json = raw

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens

    app.ai_summary = summary_json
    app.ai_summary_at = datetime.now(UTC)
    app.ai_summary_model = f"{SUMMARY_MODEL}/{prompt_tag}"
    db.commit()

    logger.info(
        "요약 생성 완료: application_id=%d, tokens=%d+%d, model=%s",
        application_id,
        input_tokens,
        output_tokens,
        app.ai_summary_model,
    )
    return summary_json


def generate_summary_bg(application_id: int) -> None:
    """FastAPI BackgroundTasks 용. 자체 DB 세션을 만들어 실행한다."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        generate_summary(db, application_id)
    except Exception:
        logger.exception("백그라운드 요약 실패: application_id=%d", application_id)
    finally:
        db.close()
