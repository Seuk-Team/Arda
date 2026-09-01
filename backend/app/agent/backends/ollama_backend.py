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
    TextChunkHandler,
    ToolRunner,
    trim_history,
)

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_CHAT_MODEL = "qwen3:8b"
DEFAULT_SUMMARY_MODEL = "qwen3:8b"
DEFAULT_NUM_CTX = 16384
DEFAULT_TIMEOUT_SEC = 600.0
# 출력 토큰 상한. **속도의 지배 요인이 출력 길이다** — 2026-09-01 실측에서
# qwen3:4b 는 같은 질의에 3,248 토큰을 썼고(haiku 1,450) 45 tok/s 라 그 자체로 70초였다.
# 프리픽스가 아니라 여기가 병목이다. 0 이면 무제한.
DEFAULT_NUM_PREDICT = 700

# 로컬 모델 전용 출력 규율. 공용 프롬프트(agent.v1.md)는 Claude 기준으로 쓰여 있어
# 길이 제약이 없다 — 그것을 고치면 Anthropic 경로까지 바뀌므로 여기서만 덧붙인다.
_BREVITY_SUFFIX = """

## 출력 길이 (이 실행에만 적용 — 반드시 지킨다)

- 도구 결과를 그대로 옮겨 적지 마라. 요약해서 말한다.
- 목록은 **최대 5줄**, 한 줄에 `이름 (경력) — 기술 2개까지`. 넘으면 "외 n명"으로 닫는다.
- **이메일·ID·날짜·표는 쓰지 않는다.** 담당자가 명시적으로 물을 때만 쓴다.
- 전체 답변은 **8줄 이내**. 길어질 것 같으면 먼저 요약하고 더 볼지 되묻는다."""

# 로컬 추론 직렬화 락. 모듈 수준이어야 스레드풀의 모든 요청이 같은 락을 본다.
_INFERENCE_LOCK = threading.Lock()

# 잘림 의심 임계값
_CTX_NEAR_FULL = 0.9      # prompt_eval_count 가 num_ctx 의 이 비율을 넘으면 경고
_ROUGH_CHARS_PER_TOKEN = 3.0   # 한글 섞인 프롬프트 기준 보수적 추정
_TRUNCATION_RATIO = 0.5   # 추정치 대비 이 비율보다 적게 먹었으면 경고

_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_THINK_OPEN = re.compile(r"<think\b[^>]*>.*\Z", re.DOTALL | re.IGNORECASE)
_THINK_CLOSE = re.compile(r"\A.*?</think\s*>", re.DOTALL | re.IGNORECASE)


# 사고 모드를 가진 모델 계열. 여기 없으면 think 키를 보내지 않는다
_THINKING_MODEL_PREFIXES = ("qwen3", "deepseek-r1", "magistral")


def _is_thinking_model(model: str) -> bool:
    name = model.lower()
    return any(name.startswith(p) for p in _THINKING_MODEL_PREFIXES)


def _drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


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


# 로컬 모델용 짧은 도구 설명. 공용 `TOOL_DEFINITIONS` 의 설명은 Claude 기준이라
# 사용 힌트·폴백 해석법까지 들어 있는데(search_applications 는 300자가 넘는다),
# 4B 는 그걸 다 읽지 못하고 오히려 지시를 그대로 되뇌며 출력을 태운다.
# **여기서만 갈아끼운다** — 원본을 줄이면 Anthropic 경로의 동작까지 바뀐다.
_LOCAL_TOOL_DESCRIPTIONS = {
    "search_applications": (
        "지원자 검색. q=이름/이메일, semantic=역량·경력 의미 검색, "
        "stage=단계, posting_id=공고, limit=결과 수(기본 10). "
        "반환에 note 가 있으면 그 내용을 담당자에게 그대로 전한다."
    ),
}


def to_ollama_tools(definitions: list[dict]) -> list[dict]:
    """Anthropic 도구 정의(`input_schema`) → Ollama function 형식(`parameters`).

    원본 `TOOL_DEFINITIONS` 는 건드리지 않는다 — 여기서만 변환한다.
    설명도 로컬용 축약본이 있으면 여기서 갈아끼운다.
    """
    converted: list[dict] = []
    for d in definitions:
        schema = d.get("input_schema") or {"type": "object", "properties": {}}
        name = d["name"]
        converted.append({
            "type": "function",
            "function": {
                "name": name,
                "description": _LOCAL_TOOL_DESCRIPTIONS.get(
                    name, d.get("description", "")
                ),
                "parameters": schema,
            },
        })
    return converted


def streamable_prefix(raw: str) -> str:
    """누적 버퍼에서 **지금 내보내도 안전한** 본문 앞부분만 돌려준다.

    청크 단위로 `strip_think` 를 부르면 안 된다 — `<think>` 는 청크 경계를
    가로지르므로 태그가 쪼개져 사고 과정이 그대로 샌다. 그래서 누적 버퍼에서
    판단하고, 아직 확정되지 않은 꼬리는 붙들어 둔다.

    붙들어 두는 것은 둘이다.
    1. **닫히지 않은 여는 태그부터 끝까지** — 아직 사고 블록 안이다.
    2. **끝에 걸친 미완성 태그** (`<`, `<thi`, `</thin` …) — 다음 청크에서
       `<think>` 가 될 수 있다. 그대로 내보내면 태그 앞부분이 본문에 섞인다.

    반환값은 버퍼가 자랄수록 단조 증가한다(붙들어 둔 지점 뒤로만 늘어난다).
    그래서 호출자는 '이미 내보낸 길이' 만 기억하면 델타를 뽑을 수 있다.
    """
    if not raw:
        return ""
    visible = _THINK_BLOCK.sub("", raw)
    lower = visible.lower()

    # 1. 완결되지 않은 여는 태그 — 여기부터는 사고 블록일 수 있다.
    #    완결된 블록은 위에서 이미 빠졌으므로 남은 것은 전부 열린 채다.
    #    첫 번째 것부터 붙들어야 한다 (`<think>a<think>b` 같은 중첩 대비).
    open_at = lower.find("<think")
    if open_at != -1:
        return visible[:open_at]

    # 2. 꼬리에 걸친 미완성 태그
    lt = visible.rfind("<")
    if lt != -1:
        tail = lower[lt:]
        if ">" not in tail and any(
            p.startswith(tail) or tail.startswith(p) for p in ("<think", "</think")
        ):
            return visible[:lt]
    return visible


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
    # 도구 결과를 축소해서 넣는다. 병목은 출력 길이인데, 작은 모델은 도구 결과에
    # 있는 필드를 그대로 옮겨 적는다 — 넣지 않은 것은 옮겨 적을 수 없다.
    compact_tool_results = True

    def __init__(
        self,
        model: str,
        host: str | None = None,
        num_ctx: int | None = None,
        timeout: float | None = None,
        think: bool | None = None,
        num_predict: int | None = None,
    ):
        self.model = model
        self.host = (host or os.getenv("OLLAMA_HOST", DEFAULT_HOST)).rstrip("/")
        self.num_ctx = num_ctx if num_ctx is not None else _env_int("OLLAMA_NUM_CTX", DEFAULT_NUM_CTX)
        self.timeout = timeout if timeout is not None else _env_float(
            "OLLAMA_TIMEOUT_SEC", DEFAULT_TIMEOUT_SEC
        )
        # Qwen3 는 사고 모드가 기본으로 켜져 있다. `<think>` 를 지우기만 하면
        # **생성은 다 하고 버리는** 것이라 시간과 토큰 예산을 그대로 쓴다.
        # 실측(qwen3:4b, "면접 단계 지원자 보여줘"): 켜짐 출력 3444토큰·83초
        # → 꺼짐 쪽이 비교 대상이다. 도구 인자를 채우는 일에 사고 과정은 필요 없다.
        # 되살리려면 OLLAMA_THINK=1.
        # 3-상태다: True/False 는 payload 에 싣고, None 이면 키를 아예 안 보낸다.
        # **사고 모드가 없는 모델(qwen2.5 등)에 think 키를 보내면 Ollama 가 400 을 낸다.**
        # 그리고 think=False 는 사고를 없애는 게 아니라 <think> 태그만 떼는 것이라
        # 사고 과정이 본문으로 샌다(2026-09-01 실측, qwen3:4b 가 영어로 냈다) —
        # strip_think 가 태그 없는 것은 못 잡는다. 그래서 사고 모델은 켜 두고 지운다.
        env_think = os.getenv("OLLAMA_THINK")
        if think is not None:
            self.think = think
        elif env_think is not None:
            self.think = env_think == "1"
        else:
            self.think = True if _is_thinking_model(model) else None
        self.num_predict = (
            num_predict if num_predict is not None
            else _env_int("OLLAMA_NUM_PREDICT", DEFAULT_NUM_PREDICT)
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
            "options": _drop_none({
                "num_ctx": self.num_ctx,
                # 0 이하는 상한 없음 — Ollama 에 키를 아예 넣지 않는다
                "num_predict": self.num_predict if self.num_predict > 0 else None,
            }),
        }
        # 사고 모드. None 이면 키를 안 보낸다 — 지원하지 않는 모델이 400 을 낸다
        if self.think is not None:
            payload["think"] = self.think
        if tools:
            payload["tools"] = tools
        if json_schema is not None:
            payload["format"] = json_schema

        data = self._post_chat(payload)
        self._warn_if_truncated(messages, data)
        return data

    def _stream_payload(self, messages: list[dict], tools: list[dict] | None) -> dict:
        """스트리밍용 payload.

        `_chat_once` 의 payload 구성과 겹치지만 일부러 합치지 않았다 — 그 함수는
        지금 다른 작업에서도 손대는 중이라, 공용 헬퍼로 끌어내면 머지 충돌이
        커진다. 합치는 것은 두 갈래가 다 자리 잡은 뒤에 한다.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": _drop_none({
                "num_ctx": self.num_ctx,
                "num_predict": self.num_predict if self.num_predict > 0 else None,
            }),
        }
        if self.think is not None:
            payload["think"] = self.think
        if tools:
            payload["tools"] = tools
        return payload

    def _chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        on_text: TextChunkHandler | None = None,
    ) -> dict:
        """NDJSON 스트리밍 호출. 반환 형태는 `_chat_once` 와 같은 집계 dict 다.

        그래서 도구 루프 본문은 스트리밍 여부를 몰라도 된다 — 루프는 완성된
        `message.content` / `message.tool_calls` 만 본다.

        `on_text` 는 **도구 호출이 없는 동안에만** 불린다. 도구 호출 청크를 본
        순간부터 그 라운드는 흘려보내기를 멈춘다: 도구 라운드의 본문은 최종
        답이 아니라 다음 라운드의 재료라서, 담당자에게 보이면 안 된다.
        """
        import httpx

        url = f"{self.host}/api/chat"
        payload = self._stream_payload(messages, tools)

        content_parts: list[str] = []
        tool_calls: list[dict] = []
        final: dict = {}
        emitted = 0
        lead: int | None = None   # 앞쪽 공백 길이 (첫 emit 때 확정)
        suppressed = False        # 도구 호출을 본 뒤로는 흘리지 않는다

        # 락은 스트림 전 구간을 감싼다. 청크가 도는 동안 GPU 는 계속 물려 있으므로
        # 여기서 놓으면 다른 요청이 같은 GPU 에 겹쳐 들어온다.
        with _INFERENCE_LOCK:
            with httpx.stream(
                "POST", url, json=payload, timeout=self.timeout
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        # 조각난 줄 하나로 대화 전체를 버리지 않는다
                        logger.warning("ollama_stream_bad_chunk")
                        continue

                    msg = chunk.get("message") or {}
                    calls = msg.get("tool_calls") or []
                    if calls:
                        tool_calls.extend(calls)
                        suppressed = True

                    piece = msg.get("content") or ""
                    if piece:
                        content_parts.append(piece)

                    if on_text is not None and not suppressed and piece:
                        visible = streamable_prefix("".join(content_parts))
                        if lead is None:
                            if not visible.strip():
                                # 아직 공백뿐 — 앞 공백 길이를 확정할 수 없다
                                continue
                            lead = len(visible) - len(visible.lstrip())
                        delta = visible[lead + emitted:]
                        if delta:
                            on_text(delta)
                            emitted += len(delta)

                    if chunk.get("done"):
                        final = chunk

        data = dict(final)
        data["message"] = {
            "content": "".join(content_parts),
            "tool_calls": tool_calls,
        }
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
        """기존 계약 그대로. 스트리밍을 쓰지 않는 호출자는 여기로 온다."""
        return self._run_chat(
            message=message,
            history=history,
            system_prompt=system_prompt,
            tools=tools,
            request_id=request_id,
            on_text=None,
        )

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
        """`run_chat` 과 같은 일을 하되 마지막 라운드 본문을 조각으로 흘린다.

        반환값은 `run_chat` 과 동일한 `AgentResult` 이고 `reply` 가 정본이다 —
        `reply` 는 스트림과 무관하게 누적 버퍼에 `strip_think` 를 한 번 걸어
        만든다. 그래서 스트리밍을 켜도 최종 결과는 비스트리밍과 같다.
        """
        return self._run_chat(
            message=message,
            history=history,
            system_prompt=system_prompt,
            tools=tools,
            request_id=request_id,
            on_text=on_text,
        )

    def _run_chat(
        self,
        *,
        message: str,
        history: list[dict],
        system_prompt: str,
        tools: ToolRunner,
        request_id: str | None = None,
        on_text: TextChunkHandler | None = None,
    ) -> AgentResult:
        messages: list[dict] = [{"role": "system", "content": system_prompt + _BREVITY_SUFFIX}]
        messages.extend(trim_history(history))
        messages.append({"role": "user", "content": message})

        ollama_tools = to_ollama_tools(tools.definitions)

        result = AgentResult(reply="", model=self.model_tag(), backend=self.name)

        for _ in range(MAX_ROUNDS):
            result.rounds += 1
            if on_text is None:
                data = self._chat_once(messages, tools=ollama_tools)
            else:
                data = self._chat_stream(
                    messages, tools=ollama_tools, on_text=on_text
                )

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
