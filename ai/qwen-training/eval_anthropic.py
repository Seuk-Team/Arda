"""Claude 를 **파인튜닝 Qwen 과 같은 자로** 재는 평가 (2026-09-12).

## 왜 필요했나

"로컬 Qwen 으로 바꿀 만한가" 를 묻는데 비교할 숫자가 한쪽뿐이었다 — 파인튜닝 Qwen
6/23(26.1%) 만 있고 **Claude 를 같은 케이스·같은 채점기로 돌린 기록이 없었다.**
그 상태로는 "누가 더 낫다" 를 말할 수 없다. 이 스크립트가 나머지 반쪽을 만든다.

## 같은 자로 재는 방법

- 케이스: `dataset.test.jsonl` (23건) — Qwen 평가와 **같은 파일**
- 채점: `judge.evaluate_one` — Qwen 평가와 **같은 함수** (eval.py 에서 떼어낸 것)
- 프롬프트: 케이스의 system 메시지 그대로 (우리 운영 프롬프트다)
- 도구: `app.agent.tools.TOOL_DEFINITIONS` 를 **네이티브 tool-use 로** 넘긴다.
  Qwen 은 `<tool_call>` 텍스트를 뱉고 Claude 는 구조화된 블록을 주므로, 받은
  블록을 같은 텍스트 형식으로 **되돌려서** 채점기에 넣는다. 채점 규칙은 한 벌이다.

## 읽을 때 주의 (정직한 한계)

1. **이 평가의 상한은 23 이 아니다.** 정답을 그대로 채점기에 넣으면 19/23 만
   통과한다 — 4건은 `pending_pass` 규칙과 정답이 어긋나 있고(확인을 받은 **뒤**의
   실행 응답인데 채점기가 확인 문구를 요구한다), 그중 하나는 존재하지 않는 도구
   (`update_candidate_stage`) 를 정답으로 갖고 있다. 그래서 **정답 상한 대비**
   비율도 같이 찍는다.
2. Qwen 쪽 수치는 로컬 HF 생성 경로에서 나왔고 이쪽은 Anthropic API 다. 채점기는
   같지만 **생성 경로가 다르다** — 이 차이는 없앨 수 없으니 숫자를 볼 때 감안한다.

사용:
    python eval_anthropic.py                    # 기본 haiku (운영과 같은 모델)
    python eval_anthropic.py --model claude-sonnet-5
    python eval_anthropic.py --limit 3          # 비용 확인용
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import judge

ROOT = Path(__file__).parent
RESULTS_DIR = ROOT / "results"
BACKEND = ROOT.parent.parent / "backend"

DEFAULT_MODEL = "claude-haiku-4-5-20251001"  # 운영이 쓰는 모델 (agent_traces 실측)


def _load_env() -> None:
    """backend/.env 의 ANTHROPIC_API_KEY 를 쓴다. 키를 코드·로그에 남기지 않는다."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return
    env = BACKEND / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith("ANTHROPIC_API_KEY="):
            os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()
            return


def _tool_definitions() -> list[dict[str, Any]]:
    """운영이 아르에게 주는 도구 목록 그대로. 평가용으로 따로 만들지 않는다."""
    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault("APP_ENV", "dev")
    from app.agent.tools import TOOL_DEFINITIONS

    return list(TOOL_DEFINITIONS)


def _flatten(content: Any) -> str:
    """정답 형식(text/tool_use 블록 리스트)을 사람이 쓴 문장으로 되돌린다."""
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            # 앞선 턴의 도구 호출은 "그렇게 했다" 정도로만 남긴다 — 이 평가는
            # 마지막 한 턴의 판단을 보는 것이고, 과거 턴을 재현하지는 않는다.
            parts.append(f"({block.get('name')} 실행)")
    return "\n".join(p for p in parts if p)


def to_messages(sample: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """(system, messages) — 마지막 assistant(정답)는 잘라낸다."""
    system = ""
    msgs: list[dict[str, str]] = []
    for m in sample["messages"][:-1]:
        if m["role"] == "system":
            system = _flatten(m["content"])
            continue
        msgs.append({"role": m["role"], "content": _flatten(m["content"])})
    return system, msgs


def render_as_qwen(text: str, tool_uses: list[dict[str, Any]]) -> str:
    """Claude 응답을 채점기가 읽는 `<tool_call>` 형식으로 되돌린다."""
    out = text
    for tu in tool_uses:
        payload = json.dumps({"name": tu["name"], "arguments": tu["input"]}, ensure_ascii=False)
        out += f"\n<tool_call>{payload}</tool_call>"
    return out


def gold_ceiling(samples: list[dict[str, Any]]) -> int:
    """정답을 그대로 채점했을 때 몇 개가 통과하는가 (= 이 평가의 상한)."""
    ok = 0
    for s in samples:
        last = s["messages"][-1]["content"]
        if isinstance(last, list):
            text = "\n".join(b.get("text", "") for b in last if b.get("type") == "text")
            uses = [b for b in last if b.get("type") == "tool_use"]
        else:
            text, uses = last, []
        if judge.evaluate_one(s, render_as_qwen(text, uses))["passed"]:
            ok += 1
    return ok


def run(model: str, samples: list[dict[str, Any]]) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic()
    tools = _tool_definitions()

    per_cat: dict[str, dict[str, int]] = {}
    per_src: dict[str, dict[str, int]] = {}
    results: list[dict[str, Any]] = []
    in_tok = out_tok = 0

    for i, sample in enumerate(samples, 1):
        system, msgs = to_messages(sample)
        resp = client.messages.create(
            model=model,
            max_tokens=1024,
            # `temperature` 는 넘기지 않는다 — 운영 코드
            # (`app/agent/backends/anthropic_backend.py`) 도 넘기지 않고, 이 SDK
            # 버전(1.0.0)은 인자로 받지도 않는다. 운영과 같은 조건으로 재는 것이
            # 이 평가의 목적이다.
            system=system,
            tools=tools,
            messages=msgs,
        )
        in_tok += resp.usage.input_tokens
        out_tok += resp.usage.output_tokens

        text = "".join(b.text for b in resp.content if b.type == "text")
        uses = [{"name": b.name, "input": b.input} for b in resp.content if b.type == "tool_use"]
        generated = render_as_qwen(text, uses)

        judgment = judge.evaluate_one(sample, generated)
        meta = sample.get("_meta", {})
        cat, src = meta.get("category", "unknown"), meta.get("source", "unknown")
        per_cat.setdefault(cat, {"passed": 0, "failed": 0})
        per_cat[cat]["passed" if judgment["passed"] else "failed"] += 1
        per_src.setdefault(src, {"passed": 0, "failed": 0})
        per_src[src]["passed" if judgment["passed"] else "failed"] += 1

        results.append({
            "category": cat, "source": src, **judgment,
            "stop_reason": resp.stop_reason,
            "generated": generated[:500],
        })
        print(f"[{i}/{len(samples)}] {cat:<24} {'통과' if judgment['passed'] else '실패'}"
              f"  기대={judgment['expected_tools']} 받음={judgment['got_tools']}", file=sys.stderr)

    total = len(samples)
    passed = sum(1 for r in results if r["passed"])
    fail_reasons = {"tool_match": 0, "no_tool_violation": 0, "pending_pass": 0, "soft_pass": 0}
    for r in results:
        if r["passed"]:
            continue
        c = r["checks"]
        if not c["tool_match"]:
            fail_reasons["tool_match"] += 1
        if c["no_tool_violation"]:
            fail_reasons["no_tool_violation"] += 1
        if not c["pending_pass"]:
            fail_reasons["pending_pass"] += 1
        if not (c["args_pass"] or c["text_pass"]):
            fail_reasons["soft_pass"] += 1

    # Anthropic 공개 단가 (2026-09 · haiku 4.5). 모델을 바꾸면 이 값도 바꿔야 한다.
    rate_in, rate_out = 1.00 / 1_000_000, 5.00 / 1_000_000
    cost = in_tok * rate_in + out_tok * rate_out

    return {
        "run_at": datetime.now(UTC).isoformat(),
        "model": model,
        "cases_file": "dataset.test.jsonl",
        "judge": "judge.evaluate_one (eval.py 와 동일)",
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": passed / total if total else 0.0,
            "by_category": per_cat,
            "by_source": per_src,
            "fail_reasons": fail_reasons,
        },
        "tokens": {"input": in_tok, "output": out_tok, "cost_usd": round(cost, 4)},
        "results": results,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=0, help="0 = 전체")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    _load_env()
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 가 없다 (backend/.env 확인)", file=sys.stderr)
        return 2

    samples = [
        json.loads(line)
        for line in (ROOT / "dataset.test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.limit:
        samples = samples[: args.limit]

    ceiling = gold_ceiling(samples)
    print(f"정답 상한: {ceiling}/{len(samples)} "
          f"(정답을 그대로 채점해도 이만큼만 통과한다)", file=sys.stderr)

    report = run(args.model, samples)
    report["gold_ceiling"] = ceiling

    RESULTS_DIR.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else RESULTS_DIR / (
        f"{args.model}-{datetime.now(UTC):%Y-%m-%d}.json"
    )
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    s = report["summary"]
    print()
    print(f"모델      : {args.model}")
    print(f"통과      : {s['passed']}/{s['total']}  ({s['pass_rate']:.1%})")
    print(f"정답 상한 : {ceiling}/{s['total']}  → 상한 대비 {s['passed'] / ceiling:.1%}"
          if ceiling else "")
    print(f"실패 사유 : {s['fail_reasons']}")
    print(f"토큰·비용 : 입력 {report['tokens']['input']:,} · 출력 "
          f"{report['tokens']['output']:,} · ${report['tokens']['cost_usd']}")
    print(f"저장      : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
