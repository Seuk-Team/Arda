"""서류의 주장 ↔ 면접 발언 대조 (AI면접 설계 §5-6 · ADR-0026 결정 3).

**"거짓말 탐지" 를 목소리가 아니라 대조로 한다.** 이력서·자기소개서에 쓴 주장과
면접에서 한 말을 맞춰 보고, 어긋나면 **양쪽 원문을 인용해** 보여 준다. 판단은
면접관이 한다 (ADR-0003).

**점수를 만들지 않는다.** 갈래는 `consistent` · `inconsistent` · `unverified`
셋뿐이다. 합불에 곱해지는 수치가 생기는 순간 "AI 는 추천까지만" 이 무너진다.

## 인용을 코드로 보증한다

프롬프트에 "원문 그대로 옮겨라" 라고 적어도 모델은 글자를 흘린다. 그러면 면접관이
서류에서 그 문장을 못 찾고, 지원자는 하지도 않은 말로 대조당한다. **양쪽 다
원문에 있는지 확인하고, 없으면 버린다** — 프롬프트는 부탁이고 이쪽이 보증이다
(`interview_probe` 와 같은 방식).
"""

from __future__ import annotations

import json
import logging
import re

from app.agent.interview_probe import _fingerprint

logger = logging.getLogger(__name__)

# 인용 앞에 모델이 붙이는 표지 — `[면접 전사에서의 답변] 처음엔…`, `[답변 2] …`.
# 전사를 `[질문 N]` · `[답변 N]` 으로 넘겨 주니 그 형식을 따라 적는다(exaone 3.5
# 실측). 표지를 뗀 나머지는 여전히 원문과 글자까지 같아야 하므로 보증은 그대로다.
_LABEL = re.compile(r"^\s*(?:\[[^\]]{0,40}\]\s*)+")

FINDINGS_MAX_TOKENS = 2000

MAX_FINDINGS = 8
VERDICTS = ("consistent", "inconsistent", "unverified")
SOURCES = ("self_intro", "resume")

_FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim_source": {"type": "string", "enum": list(SOURCES)},
                    "claim_text": {"type": "string"},
                    "answer_text": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                },
                "required": ["claim_source", "claim_text", "answer_text", "verdict"],
            },
        }
    },
    "required": ["findings"],
}


def transcript_of(turns) -> str:
    """면접 전사 — 질문과 답변을 번갈아. 답 안 한 회차는 빼고 센다.

    **`transcript` 를 그대로 쓴다.** 엔티티 해석("파이썬 이년" → "Python 2년")을
    거친 문장을 넣으면, 모델이 그 문장을 인용했을 때 지원자가 하지 않은 말을
    인용하게 된다 (02-api.md 의 같은 이유).
    """
    parts = []
    for t in turns:
        if not (t.transcript or "").strip():
            continue
        parts.append(f"[질문 {t.seq}] {t.question}\n[답변 {t.seq}] {t.transcript}")
    return "\n\n".join(parts)


def generate_findings(sources: dict[str, str], transcript: str) -> list[dict] | None:
    """서류와 전사를 맞춰 본다.

    반환: `[{"claim_source", "claim_text", "answer_text", "verdict"}]` —
    맞춰 볼 것이 없으면 빈 리스트, 백엔드 불가·파싱 실패면 `None`.
    **빈 리스트와 None 은 다르다** — 전자는 "맞춰 볼 게 없었다", 후자는 "못 돌렸다".
    """
    cover = (sources.get("cover_letter") or "").strip()
    resume = (sources.get("resume") or "").strip()
    transcript = (transcript or "").strip()

    # 서류가 없거나 아무 답도 없으면 부를 것이 없다 — 토큰을 쓰지 않는다
    if not (cover or resume) or not transcript:
        return []

    from app.agent.backends import get_summary_backend
    from app.agent.prompts import render

    backend = get_summary_backend()
    reason = backend.unavailable_reason()
    if reason:
        logger.error("대조 생성 불가: %s", reason)
        return None

    prompt_text, tag = render(
        "interview_findings",
        cover_letter_text=cover or "(없음)",
        resume_text=resume or "(없음)",
        transcript_text=transcript,
    )
    schema = _FINDINGS_SCHEMA if backend.supports_structured_output else None
    result = backend.complete(
        prompt=prompt_text, max_tokens=FINDINGS_MAX_TOKENS, json_schema=schema
    )

    findings = _parse_findings(
        result.text or "", cover=cover, resume=resume, transcript=transcript
    )
    if findings is None:
        logger.warning("대조 파싱 실패 (stop=%s, prompt=%s)", result.stop_reason, tag)
        return None
    return findings


def _parse_findings(
    raw: str, cover: str, resume: str, transcript: str
) -> list[dict] | None:
    """`{"findings": [...]}` 를 꺼내 정제한다. 못 읽으면 None.

    **양쪽 인용을 다 확인한다.** 주장은 서류에, 답변은 전사에 있어야 한다.
    한쪽이라도 원문에서 못 찾으면 버린다 — 반쪽짜리 대조는 면접관에게 해롭다.
    """
    fps = {"self_intro": _fingerprint(cover), "resume": _fingerprint(resume)}
    said = _fingerprint(transcript)

    def quoted(text: str) -> str:
        """대조용 지문. 끝의 마침표와 앞의 표지를 뗀다."""
        return _fingerprint(_LABEL.sub("", text).rstrip(" .,·…"))

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
    if not isinstance(data, dict) or not isinstance(data.get("findings"), list):
        return None

    out: list[dict] = []
    seen: set[str] = set()
    for item in data["findings"][:MAX_FINDINGS]:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim_text", "")).strip()
        answer = str(item.get("answer_text", "")).strip()
        verdict = str(item.get("verdict", "")).strip()
        if not claim or verdict not in VERDICTS:
            continue

        # 주장이 어느 서류에서 왔는지는 **모델 말이 아니라 원문으로** 정한다.
        # 자소서 문장을 이력서라고 적어 보내면 면접관이 엉뚱한 쪽을 뒤진다.
        claim_fp = quoted(claim)
        source = next((name for name, src in fps.items() if src and claim_fp in src), None)
        if source is None:
            logger.info("서류에 없는 인용이라 버린다: %r", claim[:40])
            continue
        if claim_fp in seen:
            continue
        seen.add(claim_fp)

        if verdict == "unverified":
            # 면접에서 안 다뤄진 주장. **답변을 지어내지 않는다** — 빈 칸이 곧
            # "이건 못 물어봤다" 는 정보다.
            answer = ""
        elif not answer or quoted(answer) not in said:
            logger.info("전사에 없는 답변이라 버린다: %r", answer[:40])
            continue

        out.append(
            {
                "claim_source": source,
                # 담당자 화면에 `[답변 2]` 같은 표지가 보일 이유가 없다
                "claim_text": _LABEL.sub("", claim).strip(),
                "answer_text": _LABEL.sub("", answer).strip(),
                "verdict": verdict,
            }
        )
    return out


def generate_findings_bg(session_id: int) -> None:
    """FastAPI BackgroundTasks 용. 자체 DB 세션을 만들어 실행한다.

    **지원자를 기다리게 하지 않는다.** 면접을 끝내는 요청이 sLLM 을 기다리면
    "끝내기" 버튼이 몇십 초 멈춘다 — 전사를 비동기로 돌린 것과 같은 이유다.

    **다시 부르면 지운 뒤 새로 만든다.** 대조를 두 번 돌려 같은 주장이 두 줄로
    쌓이면 담당자가 어느 쪽이 최신인지 모른다.
    """
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Application, InterviewFinding, InterviewSession, InterviewTurn

    db = SessionLocal()
    try:
        session = db.get(InterviewSession, session_id)
        if session is None:
            return
        app_row = db.get(Application, session.application_id)
        if app_row is None:
            return

        from app.agent.interview_probe import sources_of

        turns = db.scalars(
            select(InterviewTurn)
            .where(InterviewTurn.session_id == session_id)
            .order_by(InterviewTurn.seq)
        ).all()

        findings = generate_findings(sources_of(app_row, db), transcript_of(turns))
        if findings is None:
            logger.error("대조를 못 만들었다: session_id=%d", session_id)
            return

        for row in db.scalars(
            select(InterviewFinding).where(InterviewFinding.session_id == session_id)
        ).all():
            db.delete(row)
        for f in findings:
            db.add(InterviewFinding(session_id=session_id, **f))
        db.commit()
        logger.info("대조 %d건 저장: session_id=%d", len(findings), session_id)
    except Exception:
        logger.exception("백그라운드 대조 실패: session_id=%d", session_id)
    finally:
        db.close()
