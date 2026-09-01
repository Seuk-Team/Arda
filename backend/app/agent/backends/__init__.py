"""LLM 백엔드 선택.

전역 스위치를 두지 않는다. 전환이 역할별 순차(임베딩→STT→요약→채팅)로 진행되므로
env 를 역할별로 가른다 — "요약만 로컬" 같은 중간 상태가 가능해야 한다.

    AGENT_CHAT_BACKEND     (기본 anthropic)  — run_agent 경로
    AGENT_SUMMARY_BACKEND  (기본 anthropic)  — summarizer 경로

둘 다 미설정이면 기존 Anthropic 경로와 완전히 동일하게 동작한다.
"""

from __future__ import annotations

import logging
import os

from . import anthropic_backend as _anthropic
from . import ollama_backend as _ollama
from .anthropic_backend import AnthropicBackend
from .base import (
    MAX_HISTORY_MESSAGES,
    MAX_ROUNDS,
    AgentResult,
    ChatBackend,
    CompletionResult,
    PendingAction,
    ToolRunner,
    trim_history,
)
from .ollama_backend import OllamaBackend

logger = logging.getLogger(__name__)

DEFAULT_BACKEND = "anthropic"

# 역할 → (백엔드 선택 env, 백엔드별 모델 env 와 기본값)
_ROLE_MODEL_ENV = {
    "chat": {
        "anthropic": ("AGENT_CHAT_MODEL", _anthropic.DEFAULT_CHAT_MODEL),
        "ollama": ("OLLAMA_CHAT_MODEL", _ollama.DEFAULT_CHAT_MODEL),
    },
    "summary": {
        "anthropic": ("AGENT_SUMMARY_MODEL", _anthropic.DEFAULT_SUMMARY_MODEL),
        "ollama": ("OLLAMA_SUMMARY_MODEL", _ollama.DEFAULT_SUMMARY_MODEL),
    },
}

_FACTORIES = {
    "anthropic": AnthropicBackend,
    "ollama": OllamaBackend,
}


def build_backend(name: str, role: str) -> ChatBackend:
    """이름·역할로 어댑터 인스턴스를 만든다.

    모르는 이름이면 조용히 Anthropic 으로 돌아가지 않고 터뜨린다 — 오타 하나로
    로컬인 줄 알고 클라우드에 과금하는 쪽이 더 나쁘다.
    """
    key = (name or "").strip().lower() or DEFAULT_BACKEND
    factory = _FACTORIES.get(key)
    if factory is None:
        raise ValueError(
            f"알 수 없는 LLM 백엔드: {name!r} (가능한 값: {', '.join(sorted(_FACTORIES))})"
        )
    model_env, model_default = _ROLE_MODEL_ENV[role][key]
    return factory(os.getenv(model_env, model_default))


def _select(role: str, switch_env: str) -> ChatBackend:
    return build_backend(os.getenv(switch_env, DEFAULT_BACKEND), role)


def get_chat_backend() -> ChatBackend:
    """`run_agent` 가 쓸 백엔드."""
    return _select("chat", "AGENT_CHAT_BACKEND")


def get_summary_backend() -> ChatBackend:
    """`summarizer` 가 쓸 백엔드."""
    return _select("summary", "AGENT_SUMMARY_BACKEND")


__all__ = [
    "MAX_HISTORY_MESSAGES",
    "MAX_ROUNDS",
    "AgentResult",
    "AnthropicBackend",
    "ChatBackend",
    "CompletionResult",
    "OllamaBackend",
    "PendingAction",
    "ToolRunner",
    "build_backend",
    "get_chat_backend",
    "get_summary_backend",
    "trim_history",
]
