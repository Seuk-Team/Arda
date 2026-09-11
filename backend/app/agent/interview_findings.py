"""서류의 주장 ↔ 면접 발언 대조 (AI면접 설계 §5-6 · ADR-0026 결정 3).

**"거짓말 탐지" 를 목소리가 아니라 대조로 한다.** 이력서·자기소개서에 쓴 주장과
면접에서 한 말을 맞춰 보고, 어긋나면 **양쪽 원문을 인용해** 보여 준다. 판단은
면접관이 한다 (ADR-0003).

**점수를 만들지 않는다.** 갈래는 `consistent` · `inconsistent` · `unverified`
셋뿐이다. 합불에 곱해지는 수치가 생기는 순간 "AI 는 추천까지만" 이 무너진다.

## 두 번 만든다 (2026-09-11)

- **답변마다** — 답변이 저장되면 그 답변 하나를 서류와 맞춰 `turn_id` 를 붙여
  남긴다. 담당자 화상 방이 **그 답변 밑에** 띄운다. 답변 하나로는 "안 다뤄졌다" 를
  말할 수 없으므로 일치·불일치만 낸다
- **끝날 때** — 전체 전사로 한 번 더 본다. 답변마다 만든 대조가 이미 다룬 주장은
  다시 내지 않고, 면접에서 다루지 않은 주장(확인필요)을 보탠다

## 기본은 꺼짐

LLM 을 답변마다 한 번, 끝날 때 한 번 부르므로 **머지만으로 과금이 시작되면 안
된다.** `AGENT_FINDINGS_BACKEND` 를 넣어야 켜진다 (`FINDINGS_BACKEND_ENV` 주석 참고).

## 인용을 코드로 보증한다

프롬프트에 "원문 그대로 옮겨라" 라고 적어도 모델은 글자를 흘린다. 그러면 면접관이
서류에서 그 문장을 못 찾고, 지원자는 하지도 않은 말로 대조당한다. **양쪽 다
원문에 있는지 확인하고, 없으면 버린다** — 프롬프트는 부탁이고 이쪽이 보증이다
(`interview_probe` 와 같은 방식).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

from app.agent.interview_probe import _fingerprint
from app.adapter.outbound.pg.application_pg_repository import PgApplicationRepository
from app.adapter.outbound.pg.interview_pg_repository import PgInterviewRepository

logger = logging.getLogger(__name__)

# **비어 있으면 꺼진 채로 돈다.** 답변마다 LLM 을 한 번 부르는 기능이라,
# 머지만으로 과금이 시작되면 안 된다 — 켜는 것은 돈을 낼 사람이 정한다
# (`STT_MODEL` · `VIT_MODEL` · `LIE_SERVICE_URL` 과 같은 방식).
#
#   끄기(기본): 아무것도 안 넣는다
#   로컬로:     AGENT_FINDINGS_BACKEND=ollama
#   클라우드로: AGENT_FINDINGS_BACKEND=anthropic   ← 과금된다
#
# 전역 `AGENT_SUMMARY_BACKEND` 를 그대로 쓰지 않는 이유: 요약은 이미 켜져 있고,
# 그 스위치를 따라가면 **요약을 켜 두는 것만으로 대조까지 같이 켜진다.**
FINDINGS_BACKEND_ENV = "AGENT_FINDINGS_BACKEND"

# 인용 앞에 모델이 붙이는 표지 — `[면접 전사에서의 답변] 처음엔…`, `[답변 2] …`.
# 전사를 `[질문 N]` · `[답변 N]` 으로 넘겨 주니 그 형식을 따라 적는다(exaone 3.5
# 실측). 표지를 뗀 나머지는 여전히 원문과 글자까지 같아야 하므로 보증은 그대로다.
_LABEL = re.compile(r"^\s*(?:\[[^\]]{0,40}\]\s*)+")

# 워커가 전사를 못 했을 때 넣는 자리표시자 — `[전사 지연 · 발화 8.9초]`.
# 지원자가 한 말이 아니므로 서류와 맞춰 볼 재료가 아니다.
_PLACEHOLDER = re.compile(r"^\s*\[전사")

FINDINGS_MAX_TOKENS = 2000
TURN_MAX_TOKENS = 800

MAX_FINDINGS = 8
# 답변 하나에서 낼 수 있는 대조. 답변 하나가 닿는 주장은 많아야 두셋이다.
TURN_MAX_FINDINGS = 3
VERDICTS = ("consistent", "inconsistent", "unverified")
SOURCES = ("self_intro", "resume")

# 담당자 화면에 나갈 말. **여기서 한 번만 정한다** — 화면과 프롬프트와 문서가
# 저마다 다른 낱말을 쓰면 같은 값이 세 이름으로 불린다.
#
# `unverified` 를 "확인 안 됨" 이 아니라 **"확인필요"** 로 부른다. 앞의 말은
# 지원자가 뭘 못 했다는 소리로 읽히는데, 실제로는 **우리가 안 물어본 것**이다.
KOREAN = {
    "consistent": "일치",
    "inconsistent": "불일치",
    "unverified": "확인필요",
}

# 답변마다 서류를 다시 읽지 않는다. `sources_of` 는 부를 때마다 S3 에서 PDF 를 받아
# 글자를 뽑는데, 한 면접에 답변이 10~19개라 그대로면 같은 이력서를 스무 번 받는다.
# 면접 하나가 끝날 만큼만 기억한다. 프로세스 메모리라 재시작하면 비고, 그러면 다시 읽는다.
_SOURCES_TTL_SEC = 1800
_SOURCES_MAX = 32
_sources_cache: dict[int, tuple[float, dict[str, str]]] = {}

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


def findings_on() -> bool:
    """스위치가 켜져 있는가. 백엔드를 만들지 않고 이름만 본다 — 상세 조회마다 부른다."""
    return bool(os.getenv(FINDINGS_BACKEND_ENV, "").strip())


def enabled_backend():
    """켜져 있으면 쓸 백엔드, 꺼져 있으면 None.

    **꺼진 것은 실패가 아니다.** 아무 일도 안 일어나고 대조가 안 생길 뿐이다.
    """
    from app.agent.backends import build_backend

    name = os.getenv(FINDINGS_BACKEND_ENV, "").strip()
    return build_backend(name, "summary") if name else None


def _generate(
    prompt_name: str, sources: dict[str, str], transcript: str, max_tokens: int
) -> list[dict] | None:
    """프롬프트 하나로 서류와 전사를 맞춰 본다. 반환 규칙은 `generate_findings` 와 같다."""
    cover = (sources.get("cover_letter") or "").strip()
    resume = (sources.get("resume") or "").strip()
    transcript = (transcript or "").strip()

    # 서류가 없거나 아무 답도 없으면 부를 것이 없다 — 토큰을 쓰지 않는다
    if not (cover or resume) or not transcript:
        return []

    from app.agent.prompts import render

    backend = enabled_backend()
    if backend is None:
        return []
    reason = backend.unavailable_reason()
    if reason:
        logger.error("대조 생성 불가: %s", reason)
        return None

    prompt_text, tag = render(
        prompt_name,
        cover_letter_text=cover or "(없음)",
        resume_text=resume or "(없음)",
        transcript_text=transcript,
    )
    schema = _FINDINGS_SCHEMA if backend.supports_structured_output else None
    result = backend.complete(prompt=prompt_text, max_tokens=max_tokens, json_schema=schema)

    findings = _parse_findings(
        result.text or "", cover=cover, resume=resume, transcript=transcript
    )
    if findings is None:
        logger.warning("대조 파싱 실패 (stop=%s, prompt=%s)", result.stop_reason, tag)
        return None
    return findings


def generate_findings(sources: dict[str, str], transcript: str) -> list[dict] | None:
    """서류와 전사를 맞춰 본다.

    반환: `[{"claim_source", "claim_text", "answer_text", "verdict"}]` —
    맞춰 볼 것이 없으면 빈 리스트, 백엔드 불가·파싱 실패면 `None`.
    **빈 리스트와 None 은 다르다** — 전자는 "맞춰 볼 게 없었다", 후자는 "못 돌렸다".
    """
    return _generate("interview_findings", sources, transcript, FINDINGS_MAX_TOKENS)


def generate_turn_findings(sources: dict[str, str], transcript: str) -> list[dict] | None:
    """답변 하나를 서류와 맞춰 본다. 반환 규칙은 `generate_findings` 와 같다.

    **확인필요를 내지 않는다.** 답변 하나만 보고 "이 주장은 면접에서 안 다뤄졌다"
    고 말하면 거짓이다 — 다음 답변에서 다룰 수 있다. 그건 끝날 때 전체로 본다.
    """
    found = _generate(
        "interview_findings_turn", sources, transcript, TURN_MAX_TOKENS
    )
    if found is None:
        return None
    return [f for f in found if f["verdict"] != "unverified"][:TURN_MAX_FINDINGS]


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


def _claim_key(text: str) -> str:
    """같은 주장인지 가르는 지문 — 끝날 때 대조와 답변 대조가 겹치는지 볼 때."""
    return _fingerprint(_LABEL.sub("", text).rstrip(" .,·…"))


def _cached_sources(app_row, db) -> dict[str, str]:
    """지원서 하나의 서류 글. 30분 동안은 다시 읽지 않는다 (`_sources_cache` 주석)."""
    from app.agent.interview_probe import sources_of

    now = time.monotonic()
    hit = _sources_cache.get(app_row.id)
    if hit is not None and now - hit[0] < _SOURCES_TTL_SEC:
        return hit[1]
    sources = sources_of(app_row, db)
    if len(_sources_cache) >= _SOURCES_MAX:
        _sources_cache.pop(next(iter(_sources_cache)))
    _sources_cache[app_row.id] = (now, sources)
    return sources


def save_turn_findings(db, turn_id: int) -> int | None:
    """답변 하나의 대조를 만들어 그 답변에 붙인다. 저장한 개수, 못 돌렸으면 None.

    **다시 부르면 그 답변 것만 갈아 끼운다.** 전사가 늦게 다시 와도 같은 주장이
    두 줄로 쌓이지 않는다. 끝날 때 만든 대조(turn_id 없음)에 같은 주장이 있으면
    그것은 지운다 — 어느 답변에서 나왔는지 아는 쪽이 면접관에게 더 쓸모 있다.
    """
    from sqlalchemy import delete, select

    from app.models import Application, InterviewFinding, InterviewSession, InterviewTurn

    turn = db.get(InterviewTurn, turn_id)
    if turn is None:
        return None
    said = (turn.transcript or "").strip()
    if not said or _PLACEHOLDER.match(said):
        # 말이 안 담겼거나 전사를 못 한 칸. 맞춰 볼 말이 없다 — 토큰을 쓰지 않는다
        return 0

    session = PgInterviewRepository(db).get_session(turn.session_id)
    app_row = PgApplicationRepository(db).get(session.application_id) if session else None
    if app_row is None:
        return None

    findings = generate_turn_findings(_cached_sources(app_row, db), transcript_of([turn]))
    if findings is None:
        return None

    db.execute(delete(InterviewFinding).where(InterviewFinding.turn_id == turn.id))
    keys = {_claim_key(f["claim_text"]) for f in findings}
    if keys:
        for row in db.scalars(
            select(InterviewFinding).where(
                InterviewFinding.session_id == turn.session_id,
                InterviewFinding.turn_id.is_(None),
            )
        ).all():
            if _claim_key(row.claim_text) in keys:
                db.delete(row)
    for f in findings:
        db.add(InterviewFinding(session_id=turn.session_id, turn_id=turn.id, **f))
    db.commit()
    return len(findings)


def generate_turn_findings_bg(session_id: int, turn_id: int) -> None:
    """FastAPI BackgroundTasks 용 — 답변이 저장된 뒤 돈다.

    **지원자를 기다리게 하지 않는다.** 답변 저장 응답이 sLLM 을 기다리면 앱의
    저장 확인이 몇 초씩 밀린다. 담당자 화상 방은 3초마다 다시 읽어 붙인다.
    """
    if not findings_on():
        # 꺼져 있다. **DB 도 건드리지 않는다.**
        return

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        saved = save_turn_findings(db, turn_id)
        if saved is None:
            logger.error("답변 대조를 못 만들었다: session_id=%d turn_id=%d", session_id, turn_id)
        else:
            logger.info(
                "답변 대조 %d건 저장: session_id=%d turn_id=%d", saved, session_id, turn_id
            )
    except Exception:
        logger.exception("답변 대조 실패: session_id=%d turn_id=%d", session_id, turn_id)
    finally:
        db.close()


def save_session_findings(db, session_id: int) -> int | None:
    """면접 전체를 한 번 더 본다. 보탠 개수, 못 돌렸으면 None.

    **다시 부르면 끝날 때 만든 것만 지우고 새로 만든다.** 답변마다 만든 대조는
    그대로 두고, 그 주장은 다시 내지 않는다 — 같은 주장이 "답변 3 · 불일치" 와
    "전체 · 일치" 두 줄로 뜨면 면접관이 어느 쪽을 믿어야 할지 모른다.
    """
    from sqlalchemy import select

    from app.models import Application, InterviewFinding, InterviewSession, InterviewTurn

    session = PgInterviewRepository(db).get_session(session_id)
    if session is None:
        return None
    app_row = PgApplicationRepository(db).get(session.application_id)
    if app_row is None:
        return None

    turns = db.scalars(
        select(InterviewTurn)
        .where(InterviewTurn.session_id == session_id)
        .order_by(InterviewTurn.seq)
    ).all()

    findings = generate_findings(_cached_sources(app_row, db), transcript_of(turns))
    if findings is None:
        return None

    rows = db.scalars(
        select(InterviewFinding).where(InterviewFinding.session_id == session_id)
    ).all()
    covered = {_claim_key(r.claim_text) for r in rows if r.turn_id is not None}
    for row in rows:
        if row.turn_id is None:
            db.delete(row)
    added = 0
    for f in findings:
        if _claim_key(f["claim_text"]) in covered:
            continue
        db.add(InterviewFinding(session_id=session_id, **f))
        added += 1
    db.commit()
    return added


def generate_findings_bg(session_id: int) -> None:
    """FastAPI BackgroundTasks 용. 자체 DB 세션을 만들어 실행한다.

    **지원자를 기다리게 하지 않는다.** 면접을 끝내는 요청이 sLLM 을 기다리면
    "끝내기" 버튼이 몇십 초 멈춘다 — 전사를 비동기로 돌린 것과 같은 이유다.
    """
    if enabled_backend() is None:
        # 꺼져 있다. **DB 도 건드리지 않는다** — 앞서 만들어 둔 대조가 있다면 그대로.
        return

    from app.db import SessionLocal

    db = SessionLocal()
    try:
        added = save_session_findings(db, session_id)
        if added is None:
            logger.error("대조를 못 만들었다: session_id=%d", session_id)
            return
        logger.info("대조 %d건 저장: session_id=%d", added, session_id)
    except Exception:
        logger.exception("백그라운드 대조 실패: session_id=%d", session_id)
    finally:
        db.close()
