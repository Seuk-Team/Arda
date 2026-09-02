"""Anthropic (Claude) 백엔드 어댑터.

기존 `run_agent` / `summarizer._call_llm` 본문을 그대로 옮긴 것이다. 프롬프트
캐싱, 캐시 토큰 집계, PRICING 기반 비용 추정 전부 동작이 같아야 한다.
"""

from __future__ import annotations

import logging
import os

from ..tools.guard import StopToolLoop

from .base import (
    MAX_ROUNDS,
    AgentResult,
    CompletionResult,
    PendingAction,
    ToolRunner,
    trim_history,
)

logger = logging.getLogger(__name__)

DEFAULT_CHAT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_SUMMARY_MODEL = "claude-haiku-4-5-20251001"

AGENT_MODEL = os.getenv("AGENT_CHAT_MODEL", DEFAULT_CHAT_MODEL)

# 프롬프트 캐시 요율 (입력 단가 기준) — 쓰기 1.25배, 읽기 0.1배
CACHE_WRITE_RATE = 1.25
CACHE_READ_RATE = 0.10

PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-5": (5.00, 25.00),
}

_NO_PACKAGE_REPLY = "anthropic 패키지가 설치되지 않았습니다."


def _estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """호출 비용(USD) 추정. Anthropic 전용 — 로컬 모델명을 넣으면 안 된다.

    캐시를 켜면 캐시로 처리된 몫이 input_tokens 에서 빠진다. 캐시 항을 더하지
    않으면 비용이 실제보다 작게 나온다 — 아낀 것이 아니라 안 보이는 것이다.
    """
    input_price, output_price = PRICING.get(model, (1.00, 5.00))
    return (
        input_tokens * input_price
        + cache_write_tokens * input_price * CACHE_WRITE_RATE
        + cache_read_tokens * input_price * CACHE_READ_RATE
        + output_tokens * output_price
    ) / 1_000_000


class AnthropicBackend:
    """Claude Messages API 어댑터."""

    name = "anthropic"
    # Anthropic 에는 문법 제약 디코딩이 없다 — JSON 은 프롬프트로 요청하고
    # 파싱 폴백(_strip_fences + _parse_json)에 기댄다.
    supports_structured_output = False
    # 도구 결과를 줄이지 않는다 — 기존 응답 품질이 이 형태 기준이다.
    # (미설정 시 Anthropic 경로가 지금과 완전히 같아야 한다.)
    compact_tool_results = False

    def __init__(self, model: str):
        self.model = model

    def model_tag(self) -> str:
        return f"{self.name}:{self.model}"

    def unavailable_reason(self) -> str | None:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return "anthropic 패키지 미설치 — uv add anthropic 필요"
        if not os.getenv("ANTHROPIC_API_KEY"):
            return "ANTHROPIC_API_KEY 미설정"
        return None

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
        try:
            import anthropic
        except ImportError:
            return AgentResult(reply=_NO_PACKAGE_REPLY)

        client = anthropic.Anthropic()

        messages = trim_history(history)
        messages.append({"role": "user", "content": message})

        result = AgentResult(reply="", model=self.model_tag(), backend=self.name)

        for _ in range(MAX_ROUNDS):
            result.rounds += 1
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                # 고정부(도구 정의 + 시스템 프롬프트 ≈ 20KB)를 캐시한다. 렌더 순서가
                # tools → system → messages 라, 마지막 system 블록의 표시가 도구까지
                # 함께 묶는다. 두 번째 호출부터 이 몫이 0.1배 요금이 된다.
                # 캐시가 걸렸는지는 cache_read_tokens 로 확인한다 (0이면 안 걸린 것).
                system=[{
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }],
                tools=tools.definitions,
                messages=messages,
            )

            usage = response.usage
            result.input_tokens += usage.input_tokens
            result.output_tokens += usage.output_tokens
            # 캐시 필드는 캐시를 쓰지 않는 응답에는 없거나 None 이다
            result.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
            result.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0

            if response.stop_reason == "end_turn":
                texts = [b.text for b in response.content if b.type == "text"]
                result.reply = "\n".join(texts)
                break

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                texts = [b.text for b in response.content if b.type == "text"]
                result.reply = "\n".join(texts) if texts else "응답을 생성할 수 없습니다."
                break

            # 쓰기 도구가 포함되어 있으면 실행하지 않고 확인 요청으로 반환
            write_tool = next((tu for tu in tool_uses if tools.is_deferred(tu.name)), None)
            if write_tool:
                # 인자 값에는 지원자 이름·이메일이 들어올 수 있다. 키 이름만 남긴다 (J5)
                logger.info(
                    "pending_write_tool",
                    extra={"tool": write_tool.name, "tool_args": sorted(write_tool.input)},
                )
                result.tool_calls.append({"name": write_tool.name, "input": write_tool.input})

                texts = [b.text for b in response.content if b.type == "text"]
                result.reply = "\n".join(texts) if texts else ""
                result.pending_action = PendingAction(
                    tool_name=write_tool.name,
                    arguments=write_tool.input,
                    description=tools.describe(write_tool.name, write_tool.input),
                )
                break

            messages.append({"role": "assistant", "content": response.content})

            try:
                tool_results = []
                for tu in tool_uses:
                    logger.info("tool_call", extra={"tool": tu.name, "tool_args": sorted(tu.input)})
                    result.tool_calls.append({"name": tu.name, "input": tu.input})

                    output = tools.execute(tu.name, tu.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": output,
                    })
            except StopToolLoop as stop:
                # Anthropic 은 grammar 로 reply 를 강제할 수단이 없다 — note 를
                # 그대로 돌려주고 종료한다. 원리상 클라우드에도 이 상황이 가능해
                # tools 계층의 guard 는 백엔드와 무관하게 잡는다.
                logger.info(
                    "anthropic_stop_tool_loop",
                    extra={"reason": stop.reason},
                )
                result.reply = stop.note
                break

            messages.append({"role": "user", "content": tool_results})
        else:
            result.reply = "도구 호출 횟수 제한에 도달했습니다. 질문을 더 구체적으로 해주세요."

        result.cost_usd = _estimate_cost(
            self.model,
            result.input_tokens,
            result.output_tokens,
            result.cache_write_tokens,
            result.cache_read_tokens,
        )
        return result

    # ── 단발 생성 (요약 체인) ──────────────────────────────────────

    def complete(
        self,
        *,
        prompt: str,
        max_tokens: int,
        json_schema: dict | None = None,
    ) -> CompletionResult:
        """도구 없는 1회 호출. json_schema 는 무시한다 (능력 플래그가 False)."""
        import anthropic

        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        in_tokens = response.usage.input_tokens
        out_tokens = response.usage.output_tokens
        return CompletionResult(
            text=raw,
            input_tokens=in_tokens,
            output_tokens=out_tokens,
            stop_reason=response.stop_reason,
            cost_usd=_estimate_cost(self.model, in_tokens, out_tokens),
        )
