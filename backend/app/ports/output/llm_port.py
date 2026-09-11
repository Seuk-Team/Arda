"""LLM Port · Ports & Adapters 정식 이름.

**실제 구현은 `app/agent/backends/base.py`** 에 있고 (Protocol · DI 포함) 여기서
그대로 re-export 한다. ADR-0035 §3 규약에 따라 파일 이동 없이 새 이름을 열어 준다:

- 새 코드는 `from app.ports.output.llm_port import ChatBackend, get_chat_backend` 로 쓴다.
- 옛 코드는 `from app.agent.backends import ChatBackend, get_chat_backend` 그대로 동작.

이 위치는 "어디서 이 계약을 봐야 하는가" 를 문서화하는 자리다. 실체 이동은 Phase
3 이후 각 컨텍스트 오너가 필요할 때 진행한다 (§4).
"""

from __future__ import annotations

from app.agent.backends import (
    MAX_HISTORY_MESSAGES,
    MAX_ROUNDS,
    AgentResult,
    AnthropicBackend,
    ChatBackend,
    CompletionResult,
    OllamaBackend,
    PendingAction,
    StreamingChatBackend,
    TextChunkHandler,
    ToolRunner,
    build_backend,
    get_chat_backend,
    get_summary_backend,
    trim_history,
)

__all__ = [
    "MAX_HISTORY_MESSAGES",
    "MAX_ROUNDS",
    "AgentResult",
    "AnthropicBackend",
    "ChatBackend",
    "CompletionResult",
    "OllamaBackend",
    "PendingAction",
    "StreamingChatBackend",
    "TextChunkHandler",
    "ToolRunner",
    "build_backend",
    "get_chat_backend",
    "get_summary_backend",
    "trim_history",
]
