"""의도 라우터 변형 30건 — 채택 기준 측정용.

Step 0 의 정형 문장 10개는 regex 가 잡게 만든 것이라, 라우터의 진짜 정확도는
**표현 변형** 에서 드러난다: 존칭(씨/님), 오타, 존댓말, 조사 변형, "좀/다/전체".

각 건에 기대 의도·이름·stage 를 붙여 실 API 로 호출하고 판정한다.

판정 (verdict):
- correct  — 의도·이름·stage 가 기대와 일치
- fallback — 라우터가 안 잡고 풀 에이전트로 넘김 (허용 — 오늘과 같은 동작)
- wrong    — 다른 의도로 라우팅됐거나 이름·stage 가 틀림

구조적 기준 (assert — 하나라도 깨지면 채택 불가):
- 렌더된 답변에 시드 밖 이름이 없어야 한다 (도구 결과 창작 차단)
- change_stage 확인 카드는 기대한 지원자를 가리켜야 한다 (다른 레코드 차단)

의도 정확도 (≤5% wrong) 와 시간 (p50 ≤ 4s) 은 results/ 를 집계해 본다.
쓰기 의도는 확인 카드까지만 만들고 실행하지 않으므로 DB 를 바꾸지 않는다.
"""
from __future__ import annotations

import re

import pytest

from .conftest import SEED_NAMES

# (sid, group, message, expected_intent, expected_name, expected_stage)
VARIATIONS: list[tuple[str, str, str, str, str | None, str | None]] = [
    # list_applicants
    ("L1", "list", "지원자들 다 보여줘요",            "list_applicants", None, None),
    ("L2", "list", "전체 지원자 목록 좀",              "list_applicants", None, None),
    ("L3", "list", "지원자 리스트 뽑아줘",             "list_applicants", None, None),
    ("L4", "list", "지원자 누구누구 있어?",            "list_applicants", None, None),
    ("L5", "list", "지원자 전부 보여주세요",           "list_applicants", None, None),
    ("L6", "list", "지원한 사람들 목록",               "list_applicants", None, None),
    # stage_applicants
    ("S1", "stage", "면접 단계에 있는 지원자들",       "stage_applicants", None, "interview"),
    ("S2", "stage", "서류 검토 중인 사람 누구야",      "stage_applicants", None, "screening"),
    ("S3", "stage", "합격한 지원자 보여줘",            "stage_applicants", None, "accepted"),
    ("S4", "stage", "불합격 처리된 지원자 목록",       "stage_applicants", None, "rejected"),
    ("S5", "stage", "접수 상태인 지원자",              "stage_applicants", None, "applied"),
    # name_search
    ("N1", "name", "김도현씨 찾아줘",                  "name_search", "김도현", None),
    ("N2", "name", "김도현님 정보 보여줘",             "name_search", "김도현", None),
    ("N3", "name", "김도현 프로필 좀",                 "name_search", "김도현", None),
    ("N4", "name", "곽민재 검색",                      "name_search", "곽민재", None),
    ("N5", "name", "문해린이 누구야",                  "name_search", "문해린", None),
    ("N6", "name", "백지안 지원자 조회",               "name_search", "백지안", None),
    ("N7", "name", "서지호님 이력 알려줘",             "name_search", "서지호", None),
    ("N8", "name", "임서연 좀 찾아봐",                 "name_search", "임서연", None),
    # change_stage (확인 카드까지만 — 실행 안 함)
    # C1 의 "옴겨줘" 는 의도적 오타 — 오타 관대성 테스트. 다른 케이스는 정타로 두어
    # 오타 하나만으로도 라우팅이 무너지는지를 격리해서 본다.
    ("C1", "change", "김도현씨 최종합격 단계로 옴겨줘",  "change_stage", "김도현", "accepted"),
    ("C2", "change", "김도현 면접으로 넘겨줘",          "change_stage", "김도현", "interview"),
    ("C3", "change", "곽민재를 불합격 처리해줘",        "change_stage", "곽민재", "rejected"),
    ("C4", "change", "문해린 서류검토 단계로 변경",     "change_stage", "문해린", "screening"),
    ("C5", "change", "백지안 님 면접 단계로 바꿔주세요", "change_stage", "백지안", "interview"),
    ("C6", "change", "서지호 합격시켜줘",               "change_stage", "서지호", "accepted"),
    ("C7", "change", "김도현을 접수로 되돌려줘",        "change_stage", "김도현", "applied"),
    # other — 라우팅되면 안 됨
    ("O1", "other", "안녕",                            "other", None, None),
    ("O2", "other", "오늘 면접 몇 건이야?",             "other", None, None),
    ("O3", "other", "김도현에게 면접 안내 메일 써줘",   "other", None, None),
    ("O4", "other", "이번 주 일정 정리해줘",            "other", None, None),
]

_BOLD_NAME = re.compile(r"\*\*([가-힣]{2,4})\*\*")


def _infer_intent(resp: dict) -> str | None:
    """라우터 응답에서 실제 의도를 역산한다 (tool_calls[0].input 의 인자로)."""
    pending = (resp.get("pending_action") or {}).get("tool_name")
    if pending == "change_stage":
        return "change_stage"
    calls = resp.get("tool_calls") or []
    if not calls:
        return None
    args = calls[0].get("input") or {}
    if "q" in args:
        return "name_search"
    if "stage" in args:
        return "stage_applicants"
    return "list_applicants"


@pytest.mark.regression
@pytest.mark.parametrize(
    "sid,group,message,exp_intent,exp_name,exp_stage",
    VARIATIONS,
    ids=[v[0] for v in VARIATIONS],
)
def test_variation(sid, group, message, exp_intent, exp_name, exp_stage, call_chat, record):
    elapsed, resp = call_chat(message, [])

    backend = resp.get("backend") or ""
    routed = backend.startswith("router")
    reply = resp.get("reply") or ""
    pending = resp.get("pending_action") or None
    calls = resp.get("tool_calls") or []
    got_intent = _infer_intent(resp) if routed else None
    got_args = (calls[0].get("input") if calls else {}) or {}

    # ── 판정 ───────────────────────────────────────────
    if exp_intent == "other":
        verdict = "correct" if not routed else "wrong"
    elif not routed:
        verdict = "fallback"
    elif got_intent != exp_intent:
        verdict = "wrong"
    else:
        ok = True
        if exp_intent == "name_search" and exp_name:
            ok = got_args.get("q") == exp_name
        elif exp_intent == "change_stage":
            desc = (pending or {}).get("description", "")
            ok = bool(exp_name) and exp_name in desc and (pending or {}).get("arguments", {}).get("to_stage") == exp_stage
        elif exp_intent == "stage_applicants":
            ok = got_args.get("stage") == [exp_stage]
        verdict = "correct" if ok else "wrong"

    # ── 구조적 기준 ─────────────────────────────────────
    fabricated = sorted({n for n in _BOLD_NAME.findall(reply) if n not in SEED_NAMES})
    write_wrong_record = (
        (pending or {}).get("tool_name") == "change_stage"
        and bool(exp_name)
        and exp_name not in (pending or {}).get("description", "")
    )

    record({
        "sid": sid,
        "group": group,
        "message": message,
        "expected": {"intent": exp_intent, "name": exp_name, "stage": exp_stage},
        "routed": routed,
        "backend": backend,
        "got_intent": got_intent,
        "got_args": got_args,
        "pending": (pending or {}).get("tool_name"),
        "pending_description": (pending or {}).get("description"),
        "verdict": verdict,
        "fabricated_names": fabricated,
        "write_wrong_record": write_wrong_record,
        "elapsed_sec": round(elapsed, 2),
        "reply": reply,
    })

    assert not fabricated, f"[{sid}] 시드에 없는 이름이 답변에 등장: {fabricated}"
    assert not write_wrong_record, f"[{sid}] 확인 카드가 다른 지원자를 가리킴: {(pending or {}).get('description')}"
