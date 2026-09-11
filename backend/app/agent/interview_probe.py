"""자기소개서의 검증 가능한 주장 → 면접 꼬리 질문 (AI면접 설계 §5-5).

**주장이 참인지 판정하지 않는다.** 질문만 만들고 판단은 면접관이 한다
(ADR-0003). 해 본 사람은 세부를 알고 안 해 본 사람은 추상적으로 답하므로,
질문이 좋으면 대조는 사람이 할 수 있다 — 프롬프트에도 같은 규칙이 박혀 있다.

주장 하나도 못 찾는 것은 실패가 아니다. 감상과 다짐만 쓴 자기소개서가
있고, 그때 억지로 뽑은 질문은 면접관에게 해롭다.
"""

from __future__ import annotations

import json
import logging
import re
from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

logger = logging.getLogger(__name__)

_WS = re.compile(r"\s+")
_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})

PROBE_MAX_TOKENS = 1200

MAX_CLAIMS = 5
QUESTIONS_PER_CLAIM = 2
CLAIM_TYPES = ("수치", "기술", "역할", "규모")

_PROBE_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "type": {"type": "string", "enum": list(CLAIM_TYPES)},
                    "questions": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["claim", "type", "questions"],
            },
        }
    },
    "required": ["claims"],
}


def sources_of(app, db=None) -> dict[str, str]:
    """질문을 만드는 데 쓸 글들 — 자기소개서 · 이력서 · 공고 요건.

    **셋의 역할이 다르다.**

    - 자기소개서 · 이력서 — **지원자가 쓴 글.** 여기서만 주장을 인용한다
    - 공고 요건 — **회사가 쓴 글.** 인용하지 않고, 무엇을 물을지 고르는 데만 쓴다

    처음에는 자기소개서만 봤다. 확인할 주장이 지원자의 문장에서 나와야 원문을
    인용할 수 있어서였는데, **이력서도 지원자가 쓴 글이라 같은 보장이 선다.**
    경력·기술은 대부분 이력서에 있으므로 그쪽을 빼면 물을 거리의 절반을 버린다.
    """
    from app.agent.extractor import extract_text

    cover_file = resume_file = None
    for f in app.files:
        if f.kind == "cover_letter" and cover_file is None:
            cover_file = extract_text(f)
        elif f.kind == "resume" and resume_file is None:
            resume_file = extract_text(f)

    # 폼에 직접 쓴 경력·기술도 이력서와 같은 자리다.
    #
    # **`skills` 는 배열이라 그대로 넣으면 `['Python', 'FastAPI']` 가 프롬프트에
    # 들어간다.** 모델이 그 대괄호까지 옮겨 적으면 인용 대조(`_parse_claims`)가
    # 어긋나고, 면접관이 자소서에서 못 찾는 문장이 된다.
    resume_parts = [
        part
        for part in (
            f"[경력] {app.career_years}년" if app.career_years else None,
            f"[기술] {', '.join(app.skills)}" if app.skills else None,
            resume_file,
        )
        if part
    ]

    requirements = ""
    if db is not None and app.job_posting_id:
        from app.models import JobPosting

        posting = PgHiringRepository(db).get_posting(app.job_posting_id)
        if posting:
            requirements = posting.description or ""

    return {
        "cover_letter": "\n\n".join(p for p in (app.self_intro, cover_file) if p),
        "resume": "\n\n".join(resume_parts),
        "requirements": requirements,
    }


def cover_letter_of(app) -> str:
    """자기소개서만. `sources_of` 가 생기기 전 이름이라 남겨 둔다."""
    return sources_of(app)["cover_letter"]


def generate_probes(sources: dict[str, str] | str) -> list[dict] | None:
    """지원자가 쓴 글에서 주장과 꼬리 질문을 뽑는다.

    반환: `[{"claim", "type", "questions"}]` — 주장이 없으면 빈 리스트,
    백엔드 불가·파싱 실패면 `None`. **빈 리스트와 None 은 다르다** —
    전자는 "뽑을 게 없었다", 후자는 "못 돌렸다"다. 화면이 둘을 구분해야
    "자소서에 확인할 주장이 없습니다"와 "요약을 못 만들었습니다"가 갈린다.
    """
    if isinstance(sources, str):   # 옛 호출부 — 자기소개서만 넘기던 형태
        sources = {"cover_letter": sources, "resume": "", "requirements": ""}
    cover = (sources.get("cover_letter") or "").strip()
    resume = (sources.get("resume") or "").strip()
    requirements = (sources.get("requirements") or "").strip()

    # **인용은 지원자가 쓴 글에서만 나온다.** 공고 요건은 회사가 쓴 글이라
    # 여기 넣지 않는다 — 넣으면 회사 문장을 지원자 주장으로 인용하게 된다.
    quotable = "\n\n".join(p for p in (cover, resume) if p)
    if not quotable:
        return []

    from app.agent.backends import get_summary_backend
    from app.agent.prompts import render

    backend = get_summary_backend()
    reason = backend.unavailable_reason()
    if reason:
        logger.error("꼬리 질문 생성 불가: %s", reason)
        return None

    prompt_text, tag = render(
        "interview_probe",
        cover_letter_text=cover or "(없음)",
        resume_text=resume or "(없음)",
        requirements_text=requirements or "(없음)",
    )
    schema = _PROBE_SCHEMA if backend.supports_structured_output else None
    result = backend.complete(
        prompt=prompt_text, max_tokens=PROBE_MAX_TOKENS, json_schema=schema
    )

    claims = _parse_claims(result.text or "", cover=cover, resume=resume)
    if claims is None:
        logger.warning("꼬리 질문 파싱 실패 (stop=%s, prompt=%s)", result.stop_reason, tag)
        return None
    return claims


# ── 답변 기반 꼬리질문 (2026-09-10) ────────────────────────────
# `generate_probes` 는 **면접 시작 전** 자소서·이력서에서 미리 뽑는다. 이쪽은
# **답변 직후** 그 답변만 재료로 하나 만든다 — 지원자가 다음 질문 답하는 동안
# 백그라운드로 도는 자리라 지연에 여유가 있고, 그래서 실시간 흐름을 안 막는다.

FOLLOWUP_MAX_TOKENS = 200

# 짧은 답변에서는 억지로 꼬리를 뽑지 않는다 — "파이썬입니다" 에서 나오는 꼬리는
# 지원자에게 해롭다. 이 값 미만이면 즉시 None.
FOLLOWUP_MIN_ANSWER_CHARS = 20


def probe_from_answer(
    prev_question: str, prev_answer: str, applicant_summary: str = ""
) -> str | None:
    """직전 질문·답변 → 자연스러운 꼬리질문 하나. 못 뽑으면 None.

    `applicant_summary` 는 있으면 문맥에 넣지만 없어도 돈다 — 요약이 없거나
    실패한 지원자도 답변 자체로 꼬리를 만들 수 있어야 한다.

    **답변이 짧으면 즉시 포기한다** (억지 꼬리 방지, 위 상수). LLM 호출도 안 한다.
    반환 문자열은 그대로 다음 질문에 저장되므로 여기서 다듬는다 — 코드블록
    제거, 앞뒤 따옴표 제거, 250자 초과 컷.
    """
    answer = (prev_answer or "").strip()
    if len(answer) < FOLLOWUP_MIN_ANSWER_CHARS:
        return None

    from app.agent.backends import get_summary_backend

    backend = get_summary_backend()
    reason = backend.unavailable_reason()
    if reason:
        logger.warning("꼬리질문 생성 불가 (백엔드): %s", reason)
        return None

    context = f"[지원자 요약]\n{applicant_summary.strip()}\n\n" if applicant_summary.strip() else ""
    prompt = (
        "면접 진행자다. 방금 지원자가 답한 것을 재료로 **한 문장 짜리 꼬리 질문**을 만든다.\n\n"
        "규칙:\n"
        "- 답변에서 지원자가 실제로 한 말을 근거로 삼는다 — 지원자 요약은 참고만.\n"
        "- 추궁이 아니라 지원자가 세부를 펼칠 자리를 만든다. 실제로 해 본 사람은 세부가 있고 아닌 사람은 없다.\n"
        "- 한 문장. 물음표로 끝난다. 앞뒤 따옴표·번호·설명 붙이지 않는다.\n"
        "- 60자 이내. 넘으면 지원자가 못 따라온다.\n"
        "- 답변이 감상·다짐만 있어 물을 세부가 없으면 `SKIP` 한 단어만.\n\n"
        f"{context}"
        f"[직전 질문]\n{prev_question}\n\n"
        f"[지원자 답변]\n{answer}\n\n"
        "[꼬리 질문]"
    )
    result = backend.complete(prompt=prompt, max_tokens=FOLLOWUP_MAX_TOKENS)
    text = (result.text or "").strip()

    # 모델이 코드블록으로 감쌌으면 벗긴다
    if text.startswith("```"):
        first_nl = text.index("\n") if "\n" in text else len(text)
        text = text[first_nl + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    # 앞뒤 따옴표 제거
    if len(text) >= 2 and text[0] in "\"'“‘「『" and text[-1] in "\"'”’」』":
        text = text[1:-1].strip()

    if not text or text.upper().startswith("SKIP"):
        return None

    # 250자 초과는 다듬어도 못 살린다 — 프롬프트를 뚫고 큰 응답이 온 경우
    if len(text) > 250:
        logger.warning("꼬리질문이 너무 길어 버림 (%d자)", len(text))
        return None

    return text


def _fingerprint(text: str) -> str:
    """대조용 지문 — 공백을 지우고 따옴표를 통일한다.

    PDF 추출 텍스트는 문장 한가운데서 줄이 바뀐다("넘겼습니\\n다"). 그대로 비교하면
    멀쩡한 인용이 전부 어긋나므로 공백을 지우고 본다. 글자 자체가 달라진 경우는
    지문도 달라지므로 걸러진다.
    """
    return _WS.sub("", text.translate(_QUOTES))


def _parse_claims(raw: str, cover: str, resume: str) -> list[dict] | None:
    """`{"claims": [...]}` 를 꺼내 정제한다. 못 읽으면 None.

    상한(주장 5개·질문 2개)은 프롬프트에도 적혀 있지만 여기서 다시 자른다 —
    프롬프트는 부탁이고 이쪽이 보증이다.

    **자소서에 없는 인용은 버린다.** 모델이 원문을 옮기다 글자를 깨뜨리는 일이 있는데
    ("목록이" → "목lists이"), 그러면 면접관이 자소서에서 그 문장을 찾지 못해 대조가
    성립하지 않는다. 질문이 멀쩡해도 근거를 짚을 수 없으면 쓸 수 없다.
    """
    # 어느 글에서 온 인용인지 **우리가 판정한다.** 모델에게 물으면 틀리게 적을 수
    # 있고, 면접관은 그 표시를 보고 원문을 찾으러 간다.
    fps = {"자기소개서": _fingerprint(cover), "이력서": _fingerprint(resume)}
    s = raw.strip()
    if s.startswith("```"):
        first_nl = s.index("\n") if "\n" in s else len(s)
        s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()

    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
        return None

    out: list[dict] = []
    for item in data["claims"][:MAX_CLAIMS]:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim", "")).strip()
        questions = [
            str(q).strip()
            for q in (item.get("questions") or [])
            if isinstance(q, (str, int, float)) and str(q).strip()
        ][:QUESTIONS_PER_CLAIM]
        # 질문 없는 주장은 면접관에게 줄 것이 없다
        if not claim or not questions:
            continue
        # 끝에 붙인 마침표까지 원문과 같기를 요구하지는 않는다
        fp = _fingerprint(claim.rstrip(" .,·…"))
        origin = next((name for name, src in fps.items() if src and fp in src), None)
        if origin is None:
            logger.info("지원자가 쓴 글에 없는 인용이라 버린다: %r", claim[:40])
            continue
        claim_type = str(item.get("type", "")).strip()
        out.append(
            {
                "claim": claim,
                "type": claim_type if claim_type in CLAIM_TYPES else "기타",
                "questions": questions,
                "source": origin,
            }
        )
    return out
