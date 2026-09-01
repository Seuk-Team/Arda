"""LLM 백엔드 공통 계약.

경계는 "발화 + 이력 + 도구 → AgentResult" 수준에 있다. `messages.create` 한 줄을
감싸는 얇은 래퍼가 아니다 — 도구 루프, 도구 스키마 변환, thinking 제거, 로컬 추론
직렬화가 전부 어댑터 안에 있다. 그래야 `run_agent` 에 `if backend == ...` 분기가
박히지 않는다.

토크나이저가 백엔드마다 달라 토큰 수를 가로로 비교할 수 없다. 그래서 모델명만으로는
부족하고 `backend:model` 로 태깅한다 (`embedder.model_tag()` 와 같은 방식).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# 스트리밍 중 확정된 본문 조각을 받는 콜백. 조각은 이어 붙이면 되는 평문이며
# `<think>` 는 이미 걷힌 상태다. 예외를 던지지 않아야 한다 — 추론 루프가 멈춘다.
TextChunkHandler = Callable[[str], None]

MAX_ROUNDS = 10

# 대화 이력 상한 (메시지 개수 = user/assistant 쌍 × 2).
# 이력은 라운드마다 통째로 재전송되므로 상한이 없으면 대화가 길어질수록
# 호출당 입력이 선형으로, 대화 전체 비용은 제곱으로 늘어난다.
MAX_HISTORY_MESSAGES = 20


@dataclass
class PendingAction:
    tool_name: str
    arguments: dict
    description: str


@dataclass
class AgentResult:
    reply: str
    tool_calls: list[dict] = field(default_factory=list)
    pending_action: PendingAction | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    # `backend:model` 태그. 토큰 수는 백엔드 간 비교가 불가능하므로 어느 백엔드가
    # 낸 숫자인지 함께 남긴다.
    model: str = ""
    backend: str = ""
    # 비용 계산 책임은 백엔드에 있다. 로컬 추론은 0.0 을 "명시적으로" 채운다 —
    # 중앙에서 PRICING 표를 조회하면 모르는 모델이 haiku 단가로 폴백해 버린다.
    cost_usd: float = 0.0
    rounds: int = 0


@dataclass
class CompletionResult:
    """단발 텍스트 생성 1회 결과 (요약 체인 등)."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@runtime_checkable
class ToolRunner(Protocol):
    """도구 목록·실행을 어댑터에 넘기는 통로.

    DB 세션·사용자 같은 앱 개념이 어댑터로 새지 않게 한다.
    `definitions` 는 Anthropic 형식(`input_schema` 키)이 원본이고, 다른 백엔드용
    변환은 각 어댑터가 자기 안에서 한다.
    """

    definitions: list[dict]

    def is_deferred(self, name: str) -> bool:
        """실행하지 않고 사용자 확인으로 돌려보낼 도구인가 (쓰기 도구)."""
        ...

    def describe(self, name: str, arguments: dict) -> str:
        """확인 카드에 보여줄 설명 문구."""
        ...

    def execute(self, name: str, arguments: dict) -> str:
        """도구를 실행하고 결과를 JSON 문자열로 반환한다."""
        ...


@runtime_checkable
class ChatBackend(Protocol):
    """LLM 백엔드 어댑터."""

    name: str
    model: str
    # 문법 제약 디코딩(JSON 스키마 강제) 지원 여부. 로컬(Ollama `format`)에만 있다.
    # 최소 공통 분모로 깎지 않고, 있는 쪽은 쓰고 없는 쪽은 파싱 폴백을 쓴다.
    supports_structured_output: bool
    # 도구 결과를 축소해서 넣을지. 능력이 아니라 **프로필**이다 — 작은 로컬 모델은
    # 목록을 통째로 옮겨 적느라 출력 토큰을 태우므로, 애초에 옮겨 적을 것을 줄인다.
    # 도구는 로컬·API 양쪽이 같이 쓰므로 축소는 전역이 아니라 이 플래그로 가른다.
    compact_tool_results: bool

    def model_tag(self) -> str:
        """`backend:model`. 로그·저장 태그는 전부 이 값을 쓴다."""
        ...

    def unavailable_reason(self) -> str | None:
        """지금 호출할 수 없는 이유. 호출 가능하면 None."""
        ...

    def run_chat(
        self,
        *,
        message: str,
        history: list[dict],
        system_prompt: str,
        tools: ToolRunner,
        request_id: str | None = None,
    ) -> AgentResult:
        """도구 루프를 포함한 한 번의 대화 턴."""
        ...

    def complete(
        self,
        *,
        prompt: str,
        max_tokens: int,
        json_schema: dict | None = None,
    ) -> CompletionResult:
        """도구 없는 단발 생성. `json_schema` 는 능력 플래그가 참일 때만 쓰인다."""
        ...


@runtime_checkable
class StreamingChatBackend(Protocol):
    """본문을 조각으로 흘려보낼 수 있는 백엔드.

    `ChatBackend` 를 넓히지 않고 **별도 프로토콜**로 둔다. 그래야 스트리밍이 없는
    어댑터(Anthropic)는 아무것도 구현하지 않아도 되고, 호출자는
    `isinstance(backend, StreamingChatBackend)` 로만 갈라진다 — 메서드만 있는
    프로토콜이라 런타임 검사가 성립한다.

    계약:
    - 반환은 `run_chat` 과 똑같은 `AgentResult` 다. `reply` 가 **정본**이고
      `on_text` 로 흘린 조각은 미리보기다. 둘이 어긋나면 `reply` 가 맞다.
    - 도구 호출이 있는 라운드는 흘리지 않는다. 그 라운드의 본문은 최종 답이 아니다.
    - 쓰기 도구는 여전히 실행하지 않고 `pending_action` 으로 돌려보낸다(ADR-0003).
    """

    def run_chat_streaming(
        self,
        *,
        message: str,
        history: list[dict],
        system_prompt: str,
        tools: ToolRunner,
        on_text: TextChunkHandler,
        request_id: str | None = None,
    ) -> AgentResult:
        ...


def trim_history(history: list[dict], limit: int = MAX_HISTORY_MESSAGES) -> list[dict]:
    """대화 이력을 최근 limit 개로 자른다.

    Anthropic 규칙상 messages 는 user 로 시작해야 하므로, 자른 뒤 맨 앞이
    assistant 면 짝이 맞을 때까지 더 버린다. (Ollama 도 같은 순서를 기대한다.)
    """
    trimmed = history[-limit:]
    while trimmed and trimmed[0].get("role") != "user":
        trimmed = trimmed[1:]
    return trimmed
