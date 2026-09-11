"""LLM 어댑터 · Ports & Adapters 정식 자리 (ADR-0035).

**실체는 `app/agent/backends/` 에 있고** (`anthropic_backend.py`, `ollama_backend.py`)
여기서 re-export 한다. 새 코드는 이 이름을 쓴다:

    from app.adapter.outbound.llm import AnthropicBackend, OllamaBackend

옛 코드 (`app.agent.backends.AnthropicBackend`) 는 그대로 동작. 실체 이동은 Phase
3 이후.
"""

from __future__ import annotations

from app.agent.backends import AnthropicBackend, OllamaBackend

__all__ = ["AnthropicBackend", "OllamaBackend"]
