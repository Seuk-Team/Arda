"""Ollama (로컬 Qwen3) 백엔드 어댑터.

로컬 추론이라 클라우드와 다른 세 가지를 어댑터가 직접 떠안는다.

1. **thinking 누출** — Qwen3 는 응답 본문에 `<think>...</think>` 를 섞어 낸다.
   지우지 않으면 그대로 프론트로 샌다.
2. **직렬화** — GPU 가 하나(RTX 3050 8GB)라 동시 요청을 감당하지 못한다.
   `/agent/chat` 은 sync `def` 라 FastAPI 스레드풀에서 병렬로 들어온다. 모듈
   수준 락으로 추론 호출만 직렬화한다 (Anthropic 경로에는 락이 없다).
3. **조용한 잘림** — Ollama 의 `num_ctx` 기본값은 작다. 고정 프리픽스만
   약 17KB(시스템 프롬프트 12KB + 도구 스키마 5KB)라 기본값이면 프롬프트가
   말없이 잘린다. 항상 명시하고, 잘림이 의심되면 경고를 남긴다.

비용은 0.0 을 명시적으로 채운다. Anthropic 의 PRICING 표에 로컬 모델명이
흘러들어가면 haiku 단가로 폴백해 있지도 않은 요금이 찍힌다.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Any

from .base import (
    MAX_ROUNDS,
    AgentResult,
    CompletionResult,
    PendingAction,
    ToolRunner,
    trim_history,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_CHAT_MODEL = "qwen3:8b"
DEFAULT_SUMMARY_MODEL = "qwen3:8b"
DEFAULT_NUM_CTX = 16384
DEFAULT_TIMEOUT_SEC = 600.0

# 로컬 추론 직렬화 락. 모듈 수준이어야 스레드풀의 모든 요청이 같은 락을 본다.
_INFERENCE_LOCK = threading.Lock()

# 잘림 의심 임계값
_CTX_NEAR_FULL = 0.9      # prompt_eval_count 가 num_ctx 의 이 비율을 넘으면 경고
_ROUGH_CHARS_PER_TOKEN = 3.0   # 한글 섞인 프롬프트 기준 보수적 추정
_TRUNCATION_RATIO = 0.5   # 추정치 대비 이 비율보다 적게 먹었으면 경고

_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think\b[^>]*>.*\Z", re.DOTALL | re.IGNORECASE)
_THINK_CLOSE = re.compile(r"\A.*?</think\s*>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Qwen3 의 `<think>...</think>` 를 지운다.

    닫히지 않은 여는 태그(길이 제한으로 잘린 경우)와, 여는 태그 없이 닫는 태그만
    남은 경우(템플릿이 여는 태그를 먹은 경우)도 함께 처리한다. 이걸 놓치면
    사고 과정이 그대로 사용자에게 보인다.
    """
    if not text:
        return ""
    out = _THINK_BLOCK.sub("", text)
    if "</think" in out.lower():
        out = _THINK_CLOSE.sub("", out)
    if "<think" in out.lower():
        out = _THINK_OPEN.sub("", out)
    return out.strip()


def to_ollama_tools(definitions: list[dict]) -> list[dict]:
    """Anthropic 도구 정의(`input_schema`) → Ollama function 형식(`parameters`).

    원본 `TOOL_DEFINITIONS` 는 건드리지 않는다 — 여기서만 변환한다.
    """
    converted: list[dict] = []
    for d in definitions:
        schema = d.get("input_schema") or {"type": "object", "properties": {}}
        converted.append({
            "type": "function",
            "function": {
                "name": d["name"],
                "description": d.get("description", ""),
                "parameters": schema,
            },
        })
    return converted


def _coerce_arguments(raw: Any) -> dict:
    """Ollama 가 dict 로 줄 때도, JSON 문자열로 줄 때도 있다."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class OllamaBackend:
    """로컬 Ollama /api/chat 어댑터."""

    name = "ollama"
    # 문법 제약 디코딩(`format` 에 JSON 스키마) 지원. 요약 체인이 이걸 쓴다.
    supports_structured_output = True

    def __init__(
        self,
        model: str,
        host: str | None = None,
        num_ctx: int | None = None,
        timeout: float | None = None,
    ):
        self.model = model
        self.host = (host or os.getenv("OLLAMA_HOST", DEFAULT_HOST)).rstrip("/")
        self.num_ctx = num_ctx if num_ctx is not None else _env_int("OLLAMA_NUM_CTX", DEFAULT_NUM_CTX)
        self.timeout = timeout if timeout is not None else _env_float(
            "OLLAMA_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC
        )

    def model_tag(self) -> str:
        return f"{self.name}:{self.model}"

    def unavailable_reason(self) -> str | None:
        # 로컬은 API 키가 없다. 서버 기동 여부는 실제 호출에서 드러난다.
        return None

    # ── HTTP ───────────────────────────────────────────────────────

    def _post_chat(self, payload: dict) -> dict:
        import httpx

        url = f"{self.host}/api/chat"
        # 락은 HTTP 호출 구간만 감싼다. 도구 실행(DB 조회)까지 잡아두면
        # GPU 가 노는 동안 다른 요청이 막힌다.
        with _INFERENCE_LOCK:
            response = httpx.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _chat_once(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        json_schema: dict | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            # num_ctx 를 명시하지 않으면 기본값이 작아 프롬프트가 조용히 잘린다.
            "options": {"num_ctx": self.num_ctx},
        }
        if tools:
            payload["tools"] = tools
        if json_schema is not None:
            payload["format"] = json_schema

        data = self._post_chat(payload)
        self._warn_if_truncated(messages, data)
        return data

    def _warn_if_truncated(self, messages: list[dict], data: dict) -> None:
        """프롬프트가 조용히 잘렸는지 의심되면 경고를 남긴다.

        Ollama 는 앞부분이 캐시에 걸리면 `prompt_eval_count` 에 새로 평가한 몫만
        보고한다. 그래서 이건 확정이 아니라 '의심' 신호다 — 예외를 던지지 않는다.
        """
        prompt_tokens = data.get("prompt_eval_count")
        if not prompt_tokens:
            return

        if prompt_tokens >= self.num_ctx * _CTX_NEAR_FULL:
            logger.warning(
                "ollama_context_near_full",
                extra={
                    "model": self.model_tag(),
                    "prompt_eval_count": prompt_tokens,
                    "num_ctx": self.num_ctx,
                },
            )
            return

        chars = sum(len(str(m.get("content", ""))) for m in messages)
        estimated = chars / _ROUGH_CHARS_PER_TOKEN
        if estimated > 0 and prompt_tokens < estimated * _TRUNCATION_RATIO:
            logger.warning(
                "ollama_prompt_truncation_suspected",
                extra={
                    "model": self.model_tag(),
                    "prompt_eval_count": prompt_tokens,
                    "estimated_tokens": int(estimated),
                    "num_ctx": self.num_ctx,
                },
            )

    # ── 대화 (도구 루프 포함) ───────────────────────────────────────

    def run_chat(
        self,
        *,
        message: str,
        history: list[dict],
        system_prompt: str,
        tools: ToolRunner,
        request_id: str | None = None,
    ) -> AgentResult:
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        messages.extend(trim_history(history))
        messages.append({"role": "user", "content": message})

        ollama_tools = to_ollama_tools(tools.definitions)

        result = AgentResult(reply="", model=self.model_tag(), backend=self.name)

        for _ in range(MAX_ROUNDS):
            result.rounds += 1
            data = self._chat_once(messages, tools=ollama_tools)

            # 로컬에는 프롬프트 캐싱 개념이 없다. cache_* 는 0 으로 남고,
            # "미적중"과 "개념 없음"의 구분은 backend 태그가 한다.
            result.input_tokens += data.get("prompt_eval_count", 0) or 0
            result.output_tokens += data.get("eval_count", 0) or 0

            msg = data.get("message") or {}
            text = strip_think(msg.get("content") or "")
            tool_calls = msg.get("tool_calls") or []

            if not tool_calls:
                result.reply = text or "응답을 생성할 수 없습니다."
                break

            parsed_calls = [
                (
                    (tc.get("function") or {}).get("name", ""),
                    _coerce_arguments((tc.get("function") or {}).get("arguments")),
                )
                for tc in tool_calls
            ]

            # 쓰기 도구가 포함되어 있으면 실행하지 않고 확인 요청으로 반환
            write_tool = next(
                ((n, a) for n, a in parsed_calls if tools.is_deferred(n)), None
            )
            if write_tool:
                name, args = write_tool
                # 인자 값에는 지원자 이름·이메일이 들어올 수 있다. 키 이름만 남긴다 (J5)
                logger.info(
                    "pending_write_tool",
                    extra={"tool": name, "tool_args": sorted(args)},
                )
                result.tool_calls.append({"name": name, "input": args})
                result.reply = text
                result.pending_action = PendingAction(
                    tool_name=name,
                    arguments=args,
                    description=tools.describe(name, args),
                )
                break

            # thinking 을 지운 assistant 턴을 이력에 넣는다. 지우지 않으면 다음
            # 라운드 입력에 사고 과정이 그대로 쌓인다.
            messages.append({
                "role": "assistant",
                "content": text,
                "tool_calls": tool_calls,
            })

            for name, args in parsed_calls:
                logger.info("tool_call", extra={"tool": name, "tool_args": sorted(args)})
                result.tool_calls.append({"name": name, "input": args})

                output = tools.execute(name, args)
                messages.append({
                    "role": "tool",
                    "tool_name": name,
                    "content": output,
                })
        else:
            result.reply = "도구 호출 횟수 제한에 도달했습니다. 질문을 더 구체적으로 해주세요."

        # 로컬 추론은 과금이 없다 — 0.0 을 명시한다.
        result.cost_usd = 0.0
        return result

    # ── 단발 생성 (요약 체인) ──────────────────────────────────────

    def complete(
        self,
        *,
        prompt: str,
        max_tokens: int,
        json_schema: dict | None = None,
    ) -> CompletionResult:
        """`max_tokens` 는 상한으로 걸지 않는다.

        Anthropic 기준으로 잡은 값(500)을 그대로 `num_predict` 에 넣으면 Qwen3 의
        `<think>` 블록이 그 예산을 다 먹고 JSON 이 나오기 전에 끊긴다. 대신
        `format` 스키마가 문법으로 출력 길이를 닫는다 — 그게 능력 플래그를
        최소 공통 분모로 깎지 않은 이유다.
        """
        messages = [{"role": "user", "content": prompt}]
        data = self._chat_once(messages, json_schema=json_schema)
        msg = data.get("message") or {}
        return CompletionResult(
            text=strip_think(msg.get("content") or ""),
            input_tokens=data.get("prompt_eval_count", 0) or 0,
            output_tokens=data.get("eval_count", 0) or 0,
            cost_usd=0.0,
        )


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s 값이 정수가 아니다 — 기본값 %d 사용", key, default)
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("%s 값이 숫자가 아니다 — 기본값 %s 사용", key, default)
        return default
