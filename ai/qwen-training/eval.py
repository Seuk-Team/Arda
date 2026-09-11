"""dataset.test.jsonl 에 대해 학습된 어댑터를 평가.

판정 규칙 (baseline `qwen3-8b-final-2026-09-08.json` 을 재현):
- 도구 이름 집합 일치
- 도구 인자 부분 매치 (gold 의 각 키/값이 예측에 포함)
- 응답 문자열 · gold 텍스트 핵심 구절이 예측에 포함 (2 어절 이상)
- pending_action · 쓰기 도구를 gold 가 포함하면 예측 응답에 "확인" 문구가 있어야 함
- 도구 남발 방지 · gold 가 도구 0개면 예측도 0개여야 함

각 규칙은 필수(hard)와 참고(soft)로 나뉜다:
- hard: 도구 이름 · pending_action · no-tool 위반
- soft: 인자·응답 문구 (통계로만 쓴다)

pass = 전부 hard 통과 + 인자 매치 · 응답 매치 중 하나 이상
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

ROOT = Path(__file__).parent
TEST_PATH = ROOT / "dataset.test.jsonl"
RESULTS_DIR = ROOT / "results"

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)

# 확인 카드가 필요한 쓰기 도구 (TOOLS.md §2 · draft_email 은 부수효과 없어서 제외).
WRITE_TOOLS_NEED_CONFIRM = {
    "change_stage",
    "assign_interviewer",
    "create_schedule_proposal",
    "send_email",
}

CONFIRM_MARKERS = ["확인", "진행할까", "보낼까", "변경할까", "할까요"]

_TOKENIZE = re.compile(r"[가-힣]+|[A-Za-z]+|\d+")


def extract_tool_calls(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for match in TOOL_CALL_RE.finditer(text):
        try:
            payload = json.loads(match.group(1))
            if "name" in payload:
                out.append(payload)
        except json.JSONDecodeError:
            continue
    return out


def extract_text_before_tool(text: str) -> str:
    """도구 호출 앞의 순수 텍스트 부분만."""
    first = TOOL_CALL_RE.search(text)
    if first:
        return text[: first.start()].strip()
    return text.strip()


def expected_from_sample(sample: dict[str, Any]) -> dict[str, Any]:
    """마지막 assistant content 에서 기대 도구·인자·텍스트 추출."""
    last = sample["messages"][-1]
    if last["role"] != "assistant":
        return {"tools": [], "args_by_tool": {}, "text": "", "pending": False}

    tool_names: list[str] = []
    args_by_tool: dict[str, dict[str, Any]] = {}
    text_parts: list[str] = []
    content = last["content"]

    if isinstance(content, list):
        for b in content:
            if b.get("type") == "text":
                text_parts.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                name = b.get("name")
                if not name:
                    continue
                tool_names.append(name)
                args_by_tool[name] = b.get("input") or {}
    elif isinstance(content, str):
        text_parts.append(content)

    pending = bool(sample.get("_meta", {}).get("pending_action")) or any(
        t in WRITE_TOOLS_NEED_CONFIRM for t in tool_names
    )

    return {
        "tools": tool_names,
        "args_by_tool": args_by_tool,
        "text": "\n".join(text_parts),
        "pending": pending,
    }


def _keywords(text: str, k: int = 3) -> list[str]:
    """텍스트에서 핵심 어휘 몇 개 추출 (2어절 이상)."""
    toks = _TOKENIZE.findall(text)
    # 길이 2 이상만 · 중복 제거 · 앞에서 k 개
    seen = []
    for t in toks:
        if len(t) >= 2 and t not in seen:
            seen.append(t)
        if len(seen) >= k:
            break
    return seen


def _args_partial_match(got: dict[str, Any], expected: dict[str, Any]) -> bool:
    """gold 인자의 각 키·값이 got 에 그대로 있으면 통과."""
    if not expected:
        return True  # 기대치 없으면 통과
    for k, v in expected.items():
        if k not in got:
            return False
        if got[k] != v:
            # 리스트 부분 매치는 관대하게 (stage 리스트 순서 등)
            if isinstance(v, list) and isinstance(got[k], list) and set(map(str, v)) <= set(map(str, got[k])):
                continue
            return False
    return True


def load_model(base_model_id: str, adapter_dir: Path):
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    tok = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        base_model_id, quantization_config=bnb, device_map="auto", trust_remote_code=True,
    )
    if adapter_dir.exists():
        model = PeftModel.from_pretrained(model, str(adapter_dir))
        print(f"[eval] LoRA 어댑터 로드: {adapter_dir}", file=sys.stderr)
    else:
        print(f"[eval] 어댑터 없음 · base 만 · {adapter_dir}", file=sys.stderr)
    model.eval()
    return tok, model


def prompt_from_sample(sample: dict[str, Any], tok) -> str:
    # 마지막 assistant 를 잘라내고, 나머지에 generation prompt 붙임
    msgs = sample["messages"][:-1]
    rendered = []
    for m in msgs:
        content = m["content"]
        if isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
        else:
            text = content
        rendered.append({"role": m["role"], "content": text})
    return tok.apply_chat_template(rendered, tokenize=False, add_generation_prompt=True)


def evaluate_one(sample: dict[str, Any], generated: str) -> dict[str, Any]:
    """생성 결과 하나에 대한 판정."""
    expected = expected_from_sample(sample)
    got_tools_full = extract_tool_calls(generated)
    got_tool_names = [tc["name"] for tc in got_tools_full]
    got_args_by_tool = {tc["name"]: tc.get("arguments") or {} for tc in got_tools_full}
    got_text = extract_text_before_tool(generated)

    # 1. 도구 이름 (hard)
    exp_set = set(expected["tools"])
    got_set = set(got_tool_names)
    tool_match = exp_set == got_set
    hallucinated = got_set - exp_set
    missed = exp_set - got_set

    # 2. no-tool 위반 (hard) · gold 가 0개인데 예측이 도구 부름
    no_tool_violation = (not expected["tools"]) and bool(got_tool_names)

    # 3. 인자 부분 매치 (soft)
    arg_matches: dict[str, bool] = {}
    for name in exp_set:
        arg_matches[name] = _args_partial_match(
            got_args_by_tool.get(name, {}),
            expected["args_by_tool"].get(name, {}),
        )
    args_pass = all(arg_matches.values()) if arg_matches else True

    # 4. 응답 문구 (soft) · gold text 의 키워드 2/3 이상이 생성에 있으면 통과
    exp_keywords = _keywords(expected["text"], k=3)
    if exp_keywords:
        hit = sum(1 for w in exp_keywords if w in got_text)
        text_pass = hit >= max(1, len(exp_keywords) * 2 // 3)
    else:
        text_pass = True

    # 5. pending_action (hard) · gold 가 쓰기 도구를 부르면 응답에 "확인" 문구
    if expected["pending"]:
        pending_pass = any(marker in got_text for marker in CONFIRM_MARKERS)
    else:
        pending_pass = True

    # 종합 판정 · hard 3개 모두 통과 + soft(args OR text) 중 하나 이상
    hard_pass = tool_match and not no_tool_violation and pending_pass
    soft_pass = args_pass or text_pass
    passed = hard_pass and soft_pass

    return {
        "passed": passed,
        "checks": {
            "tool_match": tool_match,
            "no_tool_violation": no_tool_violation,
            "args_pass": args_pass,
            "text_pass": text_pass,
            "pending_pass": pending_pass,
        },
        "expected_tools": expected["tools"],
        "got_tools": got_tool_names,
        "hallucinated": sorted(hallucinated),
        "missed": sorted(missed),
        "arg_matches": arg_matches,
        "keywords_expected": exp_keywords,
    }


def evaluate(tok, model, samples: list[dict[str, Any]], max_new_tokens: int = 512) -> dict[str, Any]:
    per_cat: dict[str, dict[str, int]] = {}
    per_src: dict[str, dict[str, int]] = {}
    results: list[dict[str, Any]] = []

    for i, sample in enumerate(samples, 1):
        prompt = prompt_from_sample(sample, tok)
        inputs = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(
                **inputs, max_new_tokens=max_new_tokens, do_sample=False,
                pad_token_id=tok.pad_token_id,
            )
        gen = tok.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        judgment = evaluate_one(sample, gen)

        cat = sample.get("_meta", {}).get("category", "unknown")
        src = sample.get("_meta", {}).get("source", "unknown")
        per_cat.setdefault(cat, {"passed": 0, "failed": 0})
        per_cat[cat]["passed" if judgment["passed"] else "failed"] += 1
        per_src.setdefault(src, {"passed": 0, "failed": 0})
        per_src[src]["passed" if judgment["passed"] else "failed"] += 1

        results.append({
            "category": cat,
            "source": src,
            **judgment,
            "generated": gen[:500],
        })
        if i % 5 == 0:
            print(f"[eval] {i}/{len(samples)}", file=sys.stderr)

    total = len(samples)
    passed = sum(1 for r in results if r["passed"])

    # 세부 통계 · 어느 hard 규칙에서 자주 걸리는지
    fail_reasons = {"tool_match": 0, "no_tool_violation": 0, "pending_pass": 0, "soft_pass": 0}
    for r in results:
        if r["passed"]:
            continue
        checks = r["checks"]
        if not checks["tool_match"]:
            fail_reasons["tool_match"] += 1
        if checks["no_tool_violation"]:
            fail_reasons["no_tool_violation"] += 1
        if not checks["pending_pass"]:
            fail_reasons["pending_pass"] += 1
        if not (checks["args_pass"] or checks["text_pass"]):
            fail_reasons["soft_pass"] += 1

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0.0,
        "by_category": per_cat,
        "by_source": per_src,
        "fail_reasons": fail_reasons,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", default="Qwen/Qwen3-8B")
    parser.add_argument("--adapter", default=str(ROOT / "output" / "final"))
    parser.add_argument("--limit", type=int, default=0, help="0 = 전체")
    args = parser.parse_args()

    if not TEST_PATH.exists():
        print("[eval] dataset.test.jsonl 없음 — build_dataset.py 먼저", file=sys.stderr)
        return 1

    samples = [json.loads(l) for l in TEST_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        samples = samples[: args.limit]
    print(f"[eval] test 샘플 {len(samples)}건", file=sys.stderr)

    tok, model = load_model(args.base_model, Path(args.adapter))
    summary = evaluate(tok, model, samples)

    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = RESULTS_DIR / f"qwen3-8b-lora-{stamp}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[eval] pass_rate={summary['pass_rate']*100:.1f}% ({summary['passed']}/{summary['total']}) → {out_path}")
    print(f"[eval] fail 원인: {summary['fail_reasons']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
