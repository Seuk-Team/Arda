"""이력서 변동 감지 · 두 지원자의 이력서 텍스트를 대조해 변동 요약을 낸다.

두 시나리오에서 쓴다:
  A. 무결성 앵커에서 mismatch 로 잡힌 경우 (사후 변조 감지) — 현재 파일 텍스트와
     앵커 당시 저장돼 있던 텍스트 (재생성 요약의 이력서 원문 or 이전 s3_key) 를 비교.
  B. 새 접수 시 동일 인물 감지 (이메일 or 이름+연락처 일치) — 이전 application 의
     이력서와 이번 이력서를 비교.

Claude API 호출 · chain_resume_diff.v1 프롬프트 · JSON 반환. 실패 시 changed=False 로
안전한 기본값을 낸다 (담당자 화면이 통째로 죽지 않게).

(2026-09-17 신설)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models import Application

logger = logging.getLogger(__name__)

_MAX_TOKENS = 1200

_FALLBACK_UNREADABLE = {
    "changed": False,
    "summary": "이력서를 읽지 못해 변동을 확인할 수 없습니다.",
    "changes": [],
}


def _resume_text_of(db: Session, application: Application) -> str | None:
    """지원자 이력서 파일 하나 (kind=resume 첫 번째) 를 텍스트로 뽑는다.

    지원자마다 이력서는 종류당 1개가 정상 (backend/app/agent/extractor.py 관례).
    실패 시 None.
    """
    from app.agent.extractor import extract_text

    for f in application.files:
        if f.kind == "resume":
            try:
                text = extract_text(f)
                if text:
                    return text.strip()
            except Exception:
                logger.exception("이력서 추출 실패: file_id=%d", f.id)
                return None
            return None
    return None


def is_same_person(a: Application, b: Application) -> bool:
    """두 지원자가 같은 사람인가.

    판정 기준 (2026-09-17):
    - 이메일 완전 일치 = 동일인 (거의 확실).
    - 이메일 다르면 이름+연락처 완전 일치도 동일인 (연락처 유일 전제).
    - 이름만 같으면 동명이인으로 본다 (다른 사람 취급).
    """
    if a is None or b is None:
        return False
    if (a.email or "").strip().lower() == (b.email or "").strip().lower() and a.email:
        return True
    if (a.name or "").strip() == (b.name or "").strip() and a.name:
        phone_a = (a.phone or "").strip().replace("-", "").replace(" ", "")
        phone_b = (b.phone or "").strip().replace("-", "").replace(" ", "")
        if phone_a and phone_a == phone_b:
            return True
    return False


def find_prior_applications(db: Session, application: Application) -> list[Application]:
    """이 지원자 이전에 동일 인물이 낸 지원 이력을 찾는다.

    이 지원자 자신 (application_id 같은 것) 은 제외. 시간 오래된 순으로 정렬.
    """
    from sqlalchemy import select

    q = select(Application).where(Application.id != application.id).order_by(Application.created_at)
    out: list[Application] = []
    for row in db.scalars(q):
        if is_same_person(application, row):
            out.append(row)
    return out


def compute_resume_diff(
    db: Session, curr: Application, prev: Application
) -> dict[str, Any]:
    """이전·현재 이력서를 대조해 변동 요약을 낸다.

    두 지원자가 같은 사람이 아니면 호출자가 걸러야 한다 (`is_same_person`).
    성공 시 JSON: {"changed": bool, "summary": str, "changes": [...]}.
    실패 시 안전한 기본값.
    """
    prev_text = _resume_text_of(db, prev)
    curr_text = _resume_text_of(db, curr)

    if not prev_text or not curr_text:
        reason = []
        if not prev_text:
            reason.append("이전 이력서")
        if not curr_text:
            reason.append("현재 이력서")
        return {
            "changed": False,
            "summary": f"{'·'.join(reason)}를 읽지 못해 변동을 확인할 수 없습니다.",
            "changes": [],
        }

    # 두 텍스트가 실질적으로 같으면 LLM 을 부르지 않는다 (비용 절약).
    if prev_text.strip() == curr_text.strip():
        return {
            "changed": False,
            "summary": "두 이력서 사이 실질적인 변화가 없습니다.",
            "changes": [],
        }

    from app.agent.backends import get_summary_backend
    from app.agent.prompts import render

    backend = get_summary_backend()
    if backend.unavailable_reason():
        logger.warning("resume_diff backend 사용 불가: %s", backend.unavailable_reason())
        return _FALLBACK_UNREADABLE

    prompt_text, _tag = render(
        "chain_resume_diff",
        prev_resume_text=prev_text[:12000],   # 너무 길면 자름 (프롬프트 예산 보호)
        curr_resume_text=curr_text[:12000],
    )

    try:
        result = backend.complete(prompt=prompt_text, max_tokens=_MAX_TOKENS)
        raw = result.text.strip()
    except Exception:
        logger.exception("resume_diff LLM 호출 실패")
        return _FALLBACK_UNREADABLE

    # 코드펜스 벗기기
    if raw.startswith("```"):
        first_nl = raw.index("\n") if "\n" in raw else len(raw)
        raw = raw[first_nl + 1 :]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("resume_diff JSON 파싱 실패: %s", raw[:200])
        return _FALLBACK_UNREADABLE

    # 기본 구조 방어
    parsed.setdefault("changed", False)
    parsed.setdefault("summary", "")
    parsed.setdefault("changes", [])
    if not isinstance(parsed.get("changes"), list):
        parsed["changes"] = []
    return parsed


def latest_prior_diff(db: Session, application: Application) -> dict[str, Any] | None:
    """지금 지원자의 가장 최근 이전 지원과의 이력서 변동 요약.

    이전 지원이 없으면 None. 있으면 `compute_resume_diff` 결과 + `prev_application_id`
    를 함께 반환한다.
    """
    priors = find_prior_applications(db, application)
    if not priors:
        return None
    prev = priors[-1]  # 시간 오래된 순 정렬이라 마지막이 가장 최근
    diff = compute_resume_diff(db, application, prev)
    diff["prev_application_id"] = prev.id
    diff["prev_created_at"] = prev.created_at.isoformat() if prev.created_at else None
    return diff
