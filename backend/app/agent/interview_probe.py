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


def generate_probes(cover_letter_text: str) -> list[dict] | None:
    """자기소개서에서 주장과 꼬리 질문을 뽑는다.

    반환: `[{"claim", "type", "questions"}]` — 주장이 없으면 빈 리스트,
    백엔드 불가·파싱 실패면 `None`. **빈 리스트와 None 은 다르다** —
    전자는 "뽑을 게 없었다", 후자는 "못 돌렸다"다. 화면이 둘을 구분해야
    "자소서에 확인할 주장이 없습니다"와 "요약을 못 만들었습니다"가 갈린다.
    """
    text = (cover_letter_text or "").strip()
    if not text:
        return []

    from app.agent.backends import get_summary_backend
    from app.agent.prompts import render

    backend = get_summary_backend()
    reason = backend.unavailable_reason()
    if reason:
        logger.error("꼬리 질문 생성 불가: %s", reason)
        return None

    prompt_text, tag = render("interview_probe", cover_letter_text=text)
    schema = _PROBE_SCHEMA if backend.supports_structured_output else None
    result = backend.complete(
        prompt=prompt_text, max_tokens=PROBE_MAX_TOKENS, json_schema=schema
    )

    claims = _parse_claims(result.text or "", source=text)
    if claims is None:
        logger.warning("꼬리 질문 파싱 실패 (stop=%s, prompt=%s)", result.stop_reason, tag)
        return None
    return claims


def _fingerprint(text: str) -> str:
    """대조용 지문 — 공백을 지우고 따옴표를 통일한다.

    PDF 추출 텍스트는 문장 한가운데서 줄이 바뀐다("넘겼습니\\n다"). 그대로 비교하면
    멀쩡한 인용이 전부 어긋나므로 공백을 지우고 본다. 글자 자체가 달라진 경우는
    지문도 달라지므로 걸러진다.
    """
    return _WS.sub("", text.translate(_QUOTES))


def _parse_claims(raw: str, source: str) -> list[dict] | None:
    """`{"claims": [...]}` 를 꺼내 정제한다. 못 읽으면 None.

    상한(주장 5개·질문 2개)은 프롬프트에도 적혀 있지만 여기서 다시 자른다 —
    프롬프트는 부탁이고 이쪽이 보증이다.

    **자소서에 없는 인용은 버린다.** 모델이 원문을 옮기다 글자를 깨뜨리는 일이 있는데
    ("목록이" → "목lists이"), 그러면 면접관이 자소서에서 그 문장을 찾지 못해 대조가
    성립하지 않는다. 질문이 멀쩡해도 근거를 짚을 수 없으면 쓸 수 없다.
    """
    src = _fingerprint(source)
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
        if _fingerprint(claim.rstrip(" .,·…")) not in src:
            logger.info("자소서에 없는 인용이라 버린다: %r", claim[:40])
            continue
        claim_type = str(item.get("type", "")).strip()
        out.append(
            {
                "claim": claim,
                "type": claim_type if claim_type in CLAIM_TYPES else "기타",
                "questions": questions,
            }
        )
    return out
