"""빈출 담당자 요청을 4B 안 거치고 잡는 규칙 라우터 (Phase 1 레버 ②).

로컬 sLLM(qwen3:4b) 실측에서 "김도현 찾아줘" 같은 뻔한 요청에도 4B 가 도구를
잘못 고르는 사례를 확인했다 (search_applications 대신 search_users 호출).
프롬프트로 잡기에는 4B 지시 준수 능력이 얕고 매번 확률적이라, 확신도 높은
패턴은 아예 LLM 을 우회한다.

**설계 원칙**:
- 확신도 높은 것만 잡는다. 애매하면 return None 으로 LLM 이 판단
- 쓰기 도구는 pending_action 만 만들고 실행하지 않는다 — 담당자 확인 카드
  흐름을 유지 (change_stage 같은 되돌리기 어려운 것)
- 어댑터 무관 (LLM 부르기 전 단계) — 클라우드도 같은 실수 가능성이라 이 규칙이
  로컬만의 것이 아니다
- resolve_entities 는 chat 엔드포인트가 이미 호출한 뒤라 여기 들어온 message
  는 정규화됨을 전제
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field

from app.labels import STAGE_LABEL_KR

logger = logging.getLogger(__name__)


# 한국어 라벨 → 시스템 stage 값. STAGE_LABEL_KR 을 뒤집되 축약형 표현
# ("면접", "합격", "탈락") 도 함께 잡는다.
STAGE_ALIASES: dict[str, str] = {
    # 정본 (STAGE_LABEL_KR 그대로)
    "지원 접수": "applied",
    "서류 검토": "screening",
    "면접": "interview",
    "최종 합격": "accepted",
    "불합격": "rejected",
    # 축약·구어체
    "접수": "applied",
    "지원접수": "applied",
    "서류": "screening",
    "서류심사": "screening",
    "심사": "screening",
    "합격": "accepted",
    "최종합격": "accepted",
    "탈락": "rejected",
}


# 정규식 alternation 용 (긴 것부터 매치되게 정렬 — "최종합격" 이 "합격" 보다 먼저)
_STAGE_PATTERN = "|".join(sorted(STAGE_ALIASES.keys(), key=len, reverse=True))


@dataclass
class DirectAction:
    """라우터가 잡은 요청 → 어떤 도구를 어떤 인자로 부를지."""

    tool_name: str
    args: dict = field(default_factory=dict)
    # True 면 pending_action 만 만들고 실행 안 함 (확인 카드 흐름)
    is_write: bool = False
    # 매치된 규칙 이름 (로깅·디버깅용)
    rule: str = ""


# ── 규칙들 (매치 순서대로 시도, 먼저 잡히는 걸 씀) ─────────────────


def _try_list_applicants(m: str) -> DirectAction | None:
    """지원자 목록 요청. 도구 오답이 잦은 대표 케이스."""
    # "지원자 목록/리스트/전체/다 보여줘" — 뒤 어미는 유연하게
    if re.match(r"^(전체\s*)?지원자\s*(목록|리스트|다\s*보여|전체|모두)", m):
        return DirectAction(
            "search_applications", {"limit": 20},
            rule="list_applicants",
        )
    # "지원자 몇 명 (있어)?" — 개수 질문도 목록 조회로 대체
    if re.match(r"^지원자\s*(몇\s*명|얼마나)", m):
        return DirectAction(
            "search_applications", {"limit": 50},
            rule="count_applicants",
        )
    return None


def _try_stage_applicants(m: str) -> DirectAction | None:
    """특정 stage 지원자 — '면접 지원자', '서류검토 단계 지원자' 등."""
    match = re.match(
        rf"^({_STAGE_PATTERN})\s*(?:단계)?\s*지원자",
        m,
    )
    if match:
        stage = STAGE_ALIASES[match.group(1)]
        return DirectAction(
            "search_applications", {"stage": [stage], "limit": 20},
            rule=f"stage_applicants:{stage}",
        )
    return None


def _try_name_search(m: str) -> DirectAction | None:
    """이름 검색 — 'X 찾아줘 / 검색해줘 / 알려줘 / 조회해줘'.

    이름은 한글 2~4자 non-greedy 로 좁힌다. greedy 로 하면 "백지안을" 처럼
    조사까지 이름에 먹혀 검색어가 어긋난다.
    """
    match = re.match(
        r"^([가-힣]{2,4}?)\s*(?:을|를|이|가)?\s*(?:지원자)?\s*(?:을|를|이|가)?\s*"
        r"(?:찾아|검색해?|알려|조회해?|보여)\s*줘\s*[.!?]?$",
        m,
    )
    if match:
        return DirectAction(
            "search_applications", {"q": match.group(1), "limit": 10},
            rule="name_search",
        )
    return None


def _try_change_stage(m: str) -> DirectAction | None:
    """단계 변경 — 'X를 면접 단계로 옮겨줘 / 바꿔줘 / 변경해줘 / 보내줘'.

    쓰기 도구라 pending_action 으로 반환. 이름 → id 조회는 라우터 실행 단계
    (agent.py 의 handler) 에서 처리.

    stage 접미사는 "단계로 / 으로 / 로" 세 가지 다 잡는다 — "면접 단계로",
    "면접으로", "면접로" (부자연이지만).
    verb 는 "변경해줘"처럼 -해- 삽입도 허용.
    """
    match = re.match(
        rf"^(.+?)\s*(?:을|를|이|가)?\s*"
        rf"({_STAGE_PATTERN})\s*(?:단계로|으로|로)\s*"
        r"(?:옮겨|바꿔|변경\s*해?|보내)\s*(?:줘|주세요)?\s*[.!?]?$",
        m,
    )
    if not match:
        return None
    raw_name = match.group(1).strip()
    stage = STAGE_ALIASES[match.group(2)]
    # 이름이 지나치게 길거나 조사 붙었으면 라우터 스킵 (LLM 이 처리)
    if not re.match(r"^[가-힣]{2,4}$", raw_name):
        return None
    return DirectAction(
        "change_stage",
        {"_name_lookup": raw_name, "to_stage": stage},
        is_write=True,
        rule=f"change_stage:{stage}",
    )


_RULES = [
    _try_list_applicants,
    _try_stage_applicants,
    _try_name_search,
    _try_change_stage,
]


def classify_rules(message: str) -> DirectAction | None:
    """regex 규칙 라우터. 아무 규칙도 안 잡으면 None."""
    stripped = message.strip()
    if not stripped:
        return None
    for rule_fn in _RULES:
        action = rule_fn(stripped)
        if action is not None:
            return action
    return None


# ── LLM 라우터 — 판단은 LLM, 실행은 코드 ────────────────────────
#
# regex 라우터의 성과는 regex 가 똑똑해서가 아니라 **실행이 코드**여서 나왔다
# (id 창작·도구 결과 창작이 구조적으로 불가능). 그 구조는 그대로 두고 "판단" 만
# LLM 에 넘긴다: 의도 하나 고르기 + 메시지 안의 이름 베껴 쓰기. 그게 전부다.
#
# LLM 이 못 하는 것 (코드가 전담):
#   - id 생성 → 코드가 이름으로 DB 조회 (_lookup_applicants_by_name)
#   - 도구 결과 열람·요약 → 템플릿 렌더 (_format_reply)
#   - DB 호출 구성 → DirectAction 으로 코드가 만듦
# 그래서 분류가 틀려도 결과는 "엉뚱한 목록" / "되묻기" / "폴백" 이지 데이터 훼손이 아니다.
#
# 스위치: AGENT_INTENT_ROUTER = rules (기본) | llm | 0

INTENTS = ("list_applicants", "stage_applicants", "name_search", "change_stage", "other")
STAGE_CODES = ("applied", "screening", "interview", "accepted", "rejected")

# "오늘 면접 몇 건이야?" 는 면접 *일정* 질문인데 4B 가 "면접" 을 단계로 읽어
# stage_applicants 로 보냈다 (2026-09-02 변형 O2). 일정·건수·날짜 힌트가 있으면
# stage 라우팅을 막고 풀 에이전트(get_schedule_status·list_interviews 보유)로 넘긴다.
# 과하게 잡혀도 결과는 폴백(=기존 동작)이지 오답이 아니다.
_SCHEDULE_HINT = re.compile(r"(몇\s*건|일정|오늘|내일|이번\s*주|다음\s*주|날짜|시간|스케줄)")

# grammar 강제 스키마. enum 으로 출력 공간을 닫는다 — 의도·stage 를 지어낼 수 없다.
# name 은 자유 문자열이지만 _to_action 이 "메시지 안에 실제로 있는 문자열" 만 통과시킨다.
INTENT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": list(INTENTS)},
        "name": {"type": "string", "maxLength": 12},
        "stage": {"type": "string", "enum": [*STAGE_CODES, ""]},
    },
    "required": ["intent", "name", "stage"],
}

_CLASSIFY_PROMPT = """담당자 메시지를 아래 의도 하나로 분류하고 JSON 하나만 출력한다.

의도:
- list_applicants: 지원자 전체 목록·리스트·전부 보여달라
- stage_applicants: 특정 단계(접수/서류검토/면접/합격/불합격)의 지원자 목록
- name_search: 특정 지원자 한 명을 이름으로 찾기·조회·프로필
- change_stage: 특정 지원자의 단계를 바꾸기·옮기기·합격/불합격 처리
- other: 위에 없음 (인사, 자유 질문, 이메일 작성, 일정 잡기, 통계 등)

규칙:
- name 은 메시지에 적힌 이름을 그대로 복사한다 (씨·님 같은 호칭 제외). 이름이 없으면 "".
- stage 는 코드로: 접수→applied, 서류검토/서류심사→screening, 면접→interview, 합격/최종합격→accepted, 불합격/탈락→rejected. 해당 없으면 "".
- 면접 *일정·건수·날짜·시간* 을 묻는 것은 단계가 아니다 → other.
- 확신이 없으면 other.

예시:
"지원자들 다 보여줘요" → {"intent":"list_applicants","name":"","stage":""}
"면접 단계 지원자 누구야" → {"intent":"stage_applicants","name":"","stage":"interview"}
"김도현씨 찾아줘" → {"intent":"name_search","name":"김도현","stage":""}
"곽민재 프로필 좀" → {"intent":"name_search","name":"곽민재","stage":""}
"문해린 합격 단계로 옴겨줘" → {"intent":"change_stage","name":"문해린","stage":"accepted"}
"서지호 불합격 처리해줘" → {"intent":"change_stage","name":"서지호","stage":"rejected"}
"김도현에게 합격 메일 써줘" → {"intent":"other","name":"","stage":""}
"오늘 면접 몇 건이야?" → {"intent":"other","name":"","stage":""}
"안녕" → {"intent":"other","name":"","stage":""}

메시지: {message}
JSON:"""


def _parse_json(text: str) -> dict | None:
    """코드펜스·잡음을 걷어내고 dict 만 돌려준다. 실패하면 None (→ 폴백)."""
    if not text:
        return None
    body = text.strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body, flags=re.DOTALL).strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(body[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _valid_name(name: str, message: str) -> bool:
    """이름은 반드시 메시지 안에 있는 한글 2~4자여야 한다 — 창작 차단."""
    return bool(name) and name in message and re.fullmatch(r"[가-힣]{2,4}", name) is not None


def _to_action(data: dict | None, message: str) -> DirectAction | None:
    """LLM 분류 결과 → DirectAction. 검증 실패는 전부 None (풀 에이전트로 폴백)."""
    if not isinstance(data, dict):
        return None
    intent = data.get("intent")
    name = re.sub(r"(씨|님)$", "", (data.get("name") or "").strip())
    stage = (data.get("stage") or "").strip()

    if intent == "list_applicants":
        # 의도는 list 인데 유효한 stage 가 같이 왔으면 그쪽이 더 강한 신호다 —
        # "합격한 지원자 보여줘" 에서 모델이 stage=accepted 는 뽑고 의도만 list 로
        # 골랐다 (2026-09-02 변형 S3). stage 는 grammar enum 이라 지어낸 값일 수 없고,
        # list 요청 6건 실측에서 모델은 전부 stage="" 를 냈으므로 이 승격은 모델이
        # 명시적으로 stage 를 뽑았을 때만 발동한다.
        if stage in STAGE_CODES:
            intent = "stage_applicants"
        else:
            return DirectAction("search_applications", {"limit": 20}, rule="llm:list_applicants")
    if intent == "stage_applicants":
        if stage not in STAGE_CODES:
            return None
        if _SCHEDULE_HINT.search(message):
            return None  # 일정 질문 — stage 로 보내지 않고 폴백
        return DirectAction(
            "search_applications", {"stage": [stage], "limit": 20},
            rule=f"llm:stage_applicants:{stage}",
        )
    if intent == "name_search":
        if not _valid_name(name, message):
            return None
        return DirectAction("search_applications", {"q": name, "limit": 10}, rule="llm:name_search")
    if intent == "change_stage":
        if not _valid_name(name, message) or stage not in STAGE_CODES:
            return None
        return DirectAction(
            "change_stage", {"_name_lookup": name, "to_stage": stage},
            is_write=True, rule=f"llm:change_stage:{stage}",
        )
    return None


def classify_llm(message: str, backend=None) -> DirectAction | None:
    """LLM 에게 의도·이름만 묻는다. 실패·불확실은 None → 풀 에이전트로.

    `backend` 는 테스트 주입용. 기본은 AGENT_CHAT_BACKEND 가 고른 어댑터.
    이름 값은 로그에 남기지 않는다 (개인정보). 의도·유무·시간·토큰만 남긴다.
    """
    stripped = message.strip()
    if not stripped:
        return None
    if backend is None:
        from .backends import get_chat_backend  # 지연 import — 순환 방지
        backend = get_chat_backend()

    prompt = _CLASSIFY_PROMPT.replace("{message}", stripped)
    started = time.time()
    try:
        result = backend.complete(prompt=prompt, max_tokens=64, json_schema=INTENT_SCHEMA)
    except Exception:
        logger.exception("intent_router_llm_error")
        return None
    elapsed_ms = round((time.time() - started) * 1000)

    data = _parse_json(result.text)
    action = _to_action(data, stripped)
    logger.info(
        "intent_router_llm",
        extra={
            "intent": (data or {}).get("intent"),
            "routed": action is not None,
            "has_name": bool((data or {}).get("name")),
            "has_stage": bool((data or {}).get("stage")),
            "elapsed_ms": elapsed_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "stop_reason": result.stop_reason,
        },
    )
    return action


def classify(message: str) -> DirectAction | None:
    """라우터 진입점. `AGENT_INTENT_ROUTER` 로 방식을 고른다.

    - `rules` (기본, `1` 도 같음): regex 규칙 라우터
    - `llm`: LLM 분류 라우터 (판단만 LLM, 실행은 코드)
    - `0` / `off`: 라우터 끔, 전부 풀 에이전트 (순수 비교 실측용)

    message 는 chat 엔드포인트가 `resolve_entities` 로 정규화한 후 넘긴 것을
    전제한다. 여기서는 다시 정규화하지 않는다 (중복 방지).
    """
    mode = os.getenv("AGENT_INTENT_ROUTER", "rules").strip().lower()
    if mode in ("0", "off", "none"):
        return None
    if mode == "llm":
        return classify_llm(message)
    return classify_rules(message)
