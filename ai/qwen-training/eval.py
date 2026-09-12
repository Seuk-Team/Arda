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
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# 판정은 **한 벌만** 둔다 — eval_anthropic.py(Claude) 와 같은 함수를 쓴다.
# 채점기가 두 벌이면 두 모델의 숫자를 나란히 놓을 수 없다.
from judge import evaluate_one

ROOT = Path(__file__).parent
TEST_PATH = ROOT / "dataset.test.jsonl"
RESULTS_DIR = ROOT / "results"

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
