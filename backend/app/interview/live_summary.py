"""면접 중 실시간 분석 수치 → 집계 → AI 요약 문장 (2026-09-17).

실시간 면접 서버(`ai/lie-detection`)는 판정마다 진위 %, 표정 상위 3개, 눈 깜빡임·
고개·입 표시, 목소리 지표를 담당자 화면으로 보낸다(`POST /internal/interview/{token}/verdict`).
전에는 진위 합계만 세션에 남기고 나머지는 버려서, 면접이 끝나면 **무엇을 봤는지가
종합 평가에 남지 않았다.**

## 세 단계

1. **센다** (`record_live_sample`) — 판정이 올 때마다 세션 전체와 **그 순간의 질문별로**
   더한다. 개별 판정은 여전히 남기지 않는다(ADR-0034·ADR-0029 취지). 저장 자리는 기존
   `interview_sessions.truth_samples` JSON — 옛 키(`n`·`truth_sum`)는 그대로라
   `screening.truth_consistency` 가 바뀌지 않는다.
2. **줄인다** (`live_stats`) — 사람이 읽을 숫자(평균·비율)로.
3. **쓴다** (`summarize`) — AI 가 2~3문장으로 요약한다. **문장 속 숫자는 전부 2 의 값이어야
   한다.** 하나라도 없는 숫자가 있거나, 진위·성격을 단정하는 말이 있으면 문장을 버리고
   정해진 틀의 문장으로 대신한다 — 서류↔발언 대조가 원문에 없는 인용을 버리는 것과 같은 규칙.

**점수에는 넣지 않는다.** 면접 점수의 재료는 지금처럼 진위 평균뿐이다. 표정 모델은
「긴장」(옛 disgust) 정밀도가 낮다는 기록이 있고(`feature_extractor.py`), 판정 모델도
아직 표정을 입력으로 쓰지 않는다. 이 요약은 **관찰한 수치를 보여 주는 자리**다.
"""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy.orm import Session

from app.models import InterviewSession

logger = logging.getLogger(__name__)

# 얼굴 관찰(`face_signals`) 중 「눈 깜빡임」 말고 표시만 세는 것들
_FLAG_KEYS = ("고개 움직임", "입", "얼굴 비대칭")
_BLINK_RE = re.compile(r"(\d+(?:\.\d+)?)\s*회/초")
# 목소리 지표 — 평균을 낸다 (`voice_signals`)
_VOICE_KEYS = ("pitch_hz", "pitch_var_st", "loud_var_db", "voiced_pct")

# 요약 문장에 나오면 버리는 말. 수치를 **해석**해 사람을 단정하는 표현이다.
_FORBIDDEN = ("거짓말", "속이", "속임", "정직", "솔직하지", "자신감", "성격", "불안해", "초조", "합격", "불합격", "탈락")

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


# ── 1. 센다 ───────────────────────────────────────────────────────


def _add(bucket: dict, verdict: dict) -> None:
    bucket["n"] = int(bucket.get("n") or 0) + 1
    truth = verdict.get("truth_pct")
    if isinstance(truth, (int, float)):
        bucket["truth_sum"] = float(bucket.get("truth_sum") or 0.0) + float(truth)

    expressions = verdict.get("expressions") or []
    if expressions and isinstance(expressions[0], dict):
        top = expressions[0].get("label_ko") or expressions[0].get("label")
        if top:
            expr = dict(bucket.get("expr") or {})
            expr[str(top)] = int(expr.get(str(top)) or 0) + 1
            bucket["expr"] = expr
            bucket["expr_n"] = int(bucket.get("expr_n") or 0) + 1

    signals = verdict.get("signals") or []
    if signals:
        bucket["face_n"] = int(bucket.get("face_n") or 0) + 1
        flags = dict(bucket.get("flags") or {})
        for s in signals:
            if not isinstance(s, dict):
                continue
            key = s.get("key")
            if key == "눈 깜빡임":
                m = _BLINK_RE.search(str(s.get("value") or ""))
                if m:
                    bucket["blink_sum"] = float(bucket.get("blink_sum") or 0.0) + float(m.group(1))
                    bucket["blink_n"] = int(bucket.get("blink_n") or 0) + 1
            elif key in _FLAG_KEYS and s.get("flag") == "high":
                flags[key] = int(flags.get(key) or 0) + 1
        bucket["flags"] = flags

    voice = verdict.get("voice") or {}
    if isinstance(voice, dict):
        for k in _VOICE_KEYS:
            v = voice.get(k)
            if isinstance(v, (int, float)):
                bucket[f"{k}_sum"] = float(bucket.get(f"{k}_sum") or 0.0) + float(v)
                bucket[f"{k}_n"] = int(bucket.get(f"{k}_n") or 0) + 1


def record_live_sample(
    db: Session, session: InterviewSession, verdict: dict, seq: int | None
) -> None:
    """판정 한 건을 세션 전체와 질문 `seq` 에 더한다. 커밋한다.

    세션 전체 칸은 JSON 맨 위 — 옛 `{"n","truth_sum"}` 와 같은 자리라 진위 평균 계산이
    그대로다. 질문별은 `by_q["<seq>"]` 에 같은 모양으로.
    """
    current = json.loads(json.dumps(session.truth_samples or {}))  # 깊은 복사
    _add(current, verdict)
    if seq is not None:
        by_q = current.setdefault("by_q", {})
        bucket = by_q.setdefault(str(seq), {})
        _add(bucket, verdict)
    session.truth_samples = current  # JSON 컬럼은 재대입해야 변경이 잡힌다
    db.commit()


# ── 2. 줄인다 ─────────────────────────────────────────────────────


def _avg(bucket: dict, key: str, digits: int) -> float | int | None:
    n = int(bucket.get(f"{key}_n") or 0)
    if n <= 0:
        return None
    value = round(float(bucket.get(f"{key}_sum") or 0.0) / n, digits)
    return int(value) if digits == 0 else value


def _bucket_stats(bucket: dict) -> dict:
    n = int(bucket.get("n") or 0)
    out: dict = {"n": n}
    if n > 0 and "truth_sum" in bucket:
        out["truth"] = int(round(float(bucket["truth_sum"]) / n))

    expr = bucket.get("expr") or {}
    expr_n = int(bucket.get("expr_n") or 0)
    if expr_n > 0:
        ranked = sorted(expr.items(), key=lambda kv: (-kv[1], kv[0]))
        out["expressions"] = [
            {"label": label, "pct": int(round(100 * count / expr_n))} for label, count in ranked[:3]
        ]

    blink = _avg(bucket, "blink", 1)
    if blink is not None:
        out["blink_per_sec"] = blink

    face_n = int(bucket.get("face_n") or 0)
    if face_n > 0:
        flags = bucket.get("flags") or {}
        shown = {k: int(round(100 * v / face_n)) for k, v in flags.items() if v}
        if shown:
            out["flags_pct"] = shown

    voice = {
        "pitch_hz": _avg(bucket, "pitch_hz", 0),
        "pitch_var_st": _avg(bucket, "pitch_var_st", 1),
        "loud_var_db": _avg(bucket, "loud_var_db", 1),
        "voiced_pct": _avg(bucket, "voiced_pct", 0),
    }
    voice = {k: v for k, v in voice.items() if v is not None}
    if voice:
        out["voice"] = voice
    return out


def live_stats(samples: dict | None) -> dict | None:
    """집계 → 사람이 읽을 숫자. 판정이 한 번도 없었으면 None."""
    if not samples or int(samples.get("n") or 0) <= 0:
        return None
    per_question = [
        {"seq": int(seq), **_bucket_stats(bucket)}
        for seq, bucket in sorted((samples.get("by_q") or {}).items(), key=lambda kv: int(kv[0]))
        if int(bucket.get("n") or 0) > 0
    ]
    return {"overall": _bucket_stats(samples), "per_question": per_question}


# ── 3. 쓴다 ───────────────────────────────────────────────────────


def _numbers_in(value) -> set[float]:
    found: set[float] = set()
    if isinstance(value, bool):
        return found
    if isinstance(value, (int, float)):
        found.add(round(float(value), 1))
    elif isinstance(value, dict):
        for v in value.values():
            found |= _numbers_in(v)
    elif isinstance(value, list):
        for v in value:
            found |= _numbers_in(v)
    return found


def check_summary(text: str, stats: dict) -> str | None:
    """문장을 쓸 수 있으면 None, 못 쓰면 이유."""
    if not text.strip():
        return "빈 문장"
    for word in _FORBIDDEN:
        if word in text:
            return f"금지어: {word}"
    allowed = _numbers_in(stats)
    for raw in _NUMBER_RE.findall(text):
        if round(float(raw), 1) not in allowed:
            return f"수치에 없는 숫자: {raw}"
    return None


def template_summary(stats: dict) -> str:
    """AI 문장을 못 쓸 때의 고정 틀. 수치만 옮긴다."""
    o = stats["overall"]
    parts = [f"면접 중 실시간 분석 {o['n']}회"]
    if "truth" in o:
        parts.append(f"진위 평균 {o['truth']}%")
    if o.get("expressions"):
        parts.append("표정 " + " · ".join(f"{e['label']} {e['pct']}%" for e in o["expressions"]))
    if "blink_per_sec" in o:
        parts.append(f"눈 깜빡임 평균 {o['blink_per_sec']}회/초")
    return ", ".join(parts) + "."


def summarize(backend, stats: dict) -> dict:
    """AI 요약. 돌려주는 것: `{"summary", "summary_source": "ai"|"template", "prompt"?, "rejected"?}`."""
    from app.agent.prompts import render
    from app.agent.summarizer import _call_llm, _parse_json

    result: dict = {}
    try:
        text, tag = render(
            "interview_live_summary",
            stats_json=json.dumps(stats, ensure_ascii=False, indent=1),
        )
        result["prompt"] = tag
        raw, _, _, _, stop = _call_llm(backend, text, "interview_live_summary")
        parsed = _parse_json(raw, "interview_live_summary", 0, stop) or {}
        summary = str(parsed.get("summary") or "").strip()
        problem = check_summary(summary, stats)
        if problem is None:
            result.update(summary=summary, summary_source="ai")
            return result
        result["rejected"] = problem
        logger.warning("실시간 분석 요약 버림: %s", problem)
    except Exception:
        logger.exception("실시간 분석 요약 실패 — 틀 문장으로 대신한다")
    result.update(summary=template_summary(stats), summary_source="template")
    return result
