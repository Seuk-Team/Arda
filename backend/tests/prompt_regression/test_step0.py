"""Step 0 회귀 하네스 — 로컬 sLLM 채팅 시나리오 10개.

2026-09-02 실측(Step 0 지도 3벌: 원본·C0·C0+Guard) 을 자동화한 것.
Guard 도입 후 성공률 10/10 · 평균 15초 상태가 회귀 기준선.

**호출 규칙**:
- test 자체는 최소만 assert (fallback 아니면 통과) — 회귀 하네스는 "이거 되냐"
  아니라 "얼마나 잘 되냐" 도구다. 숫자는 `results/` 파일로 남는다.
- history 가 필요한 시나리오 (예: "응 변경해줘") 는 앞선 시나리오 결과를
  이어받는 `chain` 세션 스코프로 처리 — pytest 실행 순서에 의존하되 파라미터
  라이즈로 순서를 명시.
"""
from __future__ import annotations

import re

import pytest


# 프론트 확인 응답 라우터(레버 ①) 시뮬 — ArChat.tsx 의 classifyConfirmReply 와 같다.
# 하네스는 실 백엔드에 직접 호출해서 프론트 편집이 반영 안 되므로 여기서 재현한다.
_CONFIRM_HEAD = re.compile(
    r"^\s*(응|네|넵|예|좋아요?|해줘|해|맞아요?|진행(?:해줘|할게요?|해)?|ㅇㅇ|ㅇㅋ|ok|okay|yes|yep|y|어)(?:\s|[.,!~?]|$)",
    re.IGNORECASE,
)
_CANCEL_ANYWHERE = re.compile(
    r"(아니(?:야|요|에요)?|취소|안\s?할래|안\s?해|안\s?됨|nope|\bno\b)",
    re.IGNORECASE,
)


def _classify_confirm(message: str) -> str | None:
    if _CANCEL_ANYWHERE.search(message):
        return "cancel"
    if _CONFIRM_HEAD.search(message):
        return "confirm"
    return None


# (sid, description, message, prev_sid_for_history)
SCENARIOS: list[tuple[str, str, str, str | None]] = [
    ("1a", "인사",           "안녕",                                None),
    ("1b", "자기소개",       "너는 누구야",                          None),
    ("1c", "능력 질문",      "너 뭐 할 수 있어?",                    None),
    ("2a", "지원자 목록",    "지원자 목록 보여줘",                    None),
    ("2b", "이름 검색",      "김도현 찾아줘",                         None),
    ("2c", "역량 검색",      "백엔드 개발 지원자 알려줘",             None),
    ("3a", "단계 변경 요청", "김도현을 면접 단계로 옮겨줘",           None),
    ("4a", "확인 응답",      "응 변경해줘",                           "3a"),
    ("5a", "이메일 초안",    "김도현에게 합격 이메일 초안 써줘",       None),
    ("5b", "일정 제안",      "김도현 면접 다음 주 화요일로 잡아줘",   None),
]


@pytest.fixture(scope="module")
def chain() -> dict:
    """이전 시나리오 응답을 뒤에서 참조하려는 저장소. sid → response."""
    return {}


@pytest.fixture(scope="module", autouse=True)
def _kim_dohyun_baseline(reset_stage):
    """3a→4a 가 실제로 김도현(id=1) 을 screening→interview 로 바꾸므로 전후 리셋."""
    reset_stage(1, "screening")
    yield
    reset_stage(1, "screening")


@pytest.mark.regression
@pytest.mark.parametrize(
    "sid,desc,message,prev",
    SCENARIOS,
    ids=[s[0] for s in SCENARIOS],
)
def test_scenario(sid, desc, message, prev, call_chat, call_confirm, chain, record):
    history: list[dict] = []
    prev_pending: dict | None = None
    if prev:
        prev_resp = chain.get(prev)
        prev_msg = next((s[2] for s in SCENARIOS if s[0] == prev), "")
        if prev_resp:
            history = [
                {"role": "user", "content": prev_msg},
                {"role": "assistant", "content": prev_resp.get("reply", "")},
            ]
            prev_pending = prev_resp.get("pending_action")

    # 레버 ① 확인 응답 규칙 라우터 (프론트 시뮬).
    # pending 살아있고 확인 패턴이면 /agent/chat 대신 /agent/confirm 직행 → LLM 안 거침.
    if prev_pending and _classify_confirm(message) == "confirm":
        tool_name = prev_pending["tool_name"]
        arguments = prev_pending.get("arguments", {})
        elapsed, confirm_data = call_confirm(tool_name, arguments)
        # 응답을 채팅 응답 shape 로 감싼다 (record 재사용)
        resp = {
            "reply": f"(confirm 성공: {confirm_data.get('ok', False)})",
            "tool_calls": [{"name": tool_name, "input": arguments}],
            "pending_action": None,
            "backend": "router:confirm-frontend",
            "model": "router:confirm-frontend",
            "input_tokens": 0,
            "output_tokens": 0,
        }
    else:
        elapsed, resp = call_chat(message, history)

    chain[sid] = resp

    reply = resp.get("reply", "")
    tool_calls = [t.get("name") for t in (resp.get("tool_calls") or [])]
    pending = (resp.get("pending_action") or {}).get("tool_name")
    fallback = reply.strip() == "응답을 생성할 수 없습니다."
    router_hit = (resp.get("backend") or "").startswith("router")

    record({
        "sid": sid,
        "desc": desc,
        "message": message,
        "elapsed_sec": round(elapsed, 2),
        "input_tokens": resp.get("input_tokens", 0),
        "output_tokens": resp.get("output_tokens", 0),
        "tool_calls": tool_calls,
        "pending": pending,
        "pending_arguments": (resp.get("pending_action") or {}).get("arguments"),
        "fallback": fallback,
        "router_hit": router_hit,
        "reply": reply,  # 원문 저장 — 라우터 후 실제 답변 확인용
        "reply_len": len(reply),
        "backend": resp.get("backend"),
        "model": resp.get("model"),
    })

    # 최소한만 강제. 자세한 판정은 record 로.
    assert not fallback, f"[{sid}] fallback 발생 — {reply}"
