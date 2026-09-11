"""raw_traces.json + synth_cases.jsonl → dataset.{train,val,test}.jsonl.

두 소스를 하나의 학습 형식으로 병합한다:

    {"messages": [{"role": "system", ...},
                  {"role": "user", ...},
                  {"role": "assistant", ...}],
     "_meta": {source: real|synth, category, seed_id}}

**개인정보 마스킹**: agent_traces 는 실지원자 이메일·이름이 섞여 들어올 수 있다.
학습 데이터가 유출되면 곧 개인정보 유출이라 규칙 기반으로 미리 지운다.
- 이메일 → APPLICANT_EMAIL
- 8자리 생년월일 (19xx / 20xx) → APPLICANT_DOB
- 전화번호 (010-xxxx-xxxx 등) → APPLICANT_PHONE
- application_id 는 그대로 둔다 (모델이 학습해야 하는 부분)
"""

from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent
RAW_PATH = ROOT / "raw_traces.json"
SYNTH_PATH = ROOT / "synth_cases.jsonl"
INTERVIEW_SEED_PATH = ROOT / "synth_seed_interview.yaml"
PROMPTS_DIR = ROOT.parent.parent / "backend" / "app" / "agent" / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "agent.v1.md"
OUT_TRAIN = ROOT / "dataset.train.jsonl"
OUT_VAL = ROOT / "dataset.val.jsonl"
OUT_TEST = ROOT / "dataset.test.jsonl"

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")

SPLIT = (0.8, 0.1, 0.1)
SEED = 42

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
DOB_RE = re.compile(r"\b(19|20)\d{6}\b")
PHONE_RE = re.compile(r"\b01[016789][-. ]?\d{3,4}[-. ]?\d{4}\b")


def mask_pii(text: str) -> str:
    text = EMAIL_RE.sub("APPLICANT_EMAIL", text)
    text = DOB_RE.sub("APPLICANT_DOB", text)
    text = PHONE_RE.sub("APPLICANT_PHONE", text)
    return text


def load_system_prompt() -> str:
    # v1.md 의 {{user_name}} · {{user_role}} 는 시연용 값으로 채운다 — 학습 시엔 담당자 이름을
    # 알 필요 없고, 오히려 하나의 값이 반복되면 모델이 시스템 프리픽스에 조건 걸지 않게 한다.
    raw = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    return raw.replace("{{user_name}}", "담당자").replace("{{user_role}}", "admin")


def load_raw_traces() -> list[dict[str, Any]]:
    if not RAW_PATH.exists():
        print(f"[build] {RAW_PATH.name} 없음 — fetch_traces.py 를 먼저 돌려라", file=sys.stderr)
        return []
    return json.loads(RAW_PATH.read_text(encoding="utf-8"))


def load_synth_cases() -> list[dict[str, Any]]:
    if not SYNTH_PATH.exists():
        print(f"[build] {SYNTH_PATH.name} 없음 — synth_expand.py 를 먼저 돌려라", file=sys.stderr)
        return []
    out = []
    for line in SYNTH_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _render_prompt(template: str, vars: dict[str, Any]) -> str:
    """{{name}} 자리표시자 → vars[name]."""
    def repl(m):
        key = m.group(1)
        return str(vars.get(key, f"{{{{{key}}}}}"))  # 빠진 키는 원문 유지
    return _PLACEHOLDER.sub(repl, template)


def load_interview_seeds() -> list[dict[str, Any]]:
    """synth_seed_interview.yaml → 학습 샘플. 각 시드는 자기 시스템 프롬프트를 씀."""
    if not INTERVIEW_SEED_PATH.exists():
        return []
    try:
        import yaml  # 여기서만 필요
    except ImportError:
        print("[build] yaml 없음 — pip install pyyaml", file=sys.stderr)
        return []

    data = yaml.safe_load(INTERVIEW_SEED_PATH.read_text(encoding="utf-8"))
    samples: list[dict[str, Any]] = []
    for seed in data.get("seeds", []):
        prompt_file = seed.get("system_prompt_file")
        if not prompt_file:
            continue
        prompt_path = PROMPTS_DIR / prompt_file
        if not prompt_path.exists():
            print(f"[build] 프롬프트 파일 없음: {prompt_path}", file=sys.stderr)
            continue
        template = prompt_path.read_text(encoding="utf-8")
        rendered_system = _render_prompt(template, seed.get("template_vars", {}))

        assistant_text = seed.get("assistant_json", "").strip()
        if not assistant_text:
            continue

        samples.append({
            "messages": [
                {"role": "system", "content": rendered_system},
                # user 턴은 형식상 · 실제 데이터는 system 에 다 들어감
                {"role": "user", "content": "JSON 으로만 답하라."},
                {"role": "assistant", "content": [{"type": "text", "text": assistant_text}]},
            ],
            "_meta": {
                "source": "seed_interview",
                "category": seed.get("category"),
                "seed_id": seed.get("id"),
                "chain": prompt_file.replace(".v1.md", "").replace(".v2.md", "").replace(".v3.md", ""),
            },
        })
    return samples


def _tool_use_content(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """도구 호출을 Anthropic tool_use 블록 형식으로 변환.

    Haiku 가 우리 스키마 대신 {tool, arguments} 로 뱉는 경우도 있어 둘 다 받는다.
    이름을 못 뽑는 항목은 조용히 스킵.
    """
    out: list[dict[str, Any]] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        name = tc.get("name") or tc.get("tool")
        if not name:
            continue
        args = tc.get("input") if tc.get("input") is not None else tc.get("arguments", {})
        out.append({"type": "tool_use", "name": name, "input": args})
    return out


def _synth_to_sample(case: dict[str, Any], system_prompt: str) -> dict[str, Any] | None:
    """synth_cases 의 case → 학습 샘플."""
    if not case.get("input") or not case.get("reply"):
        return None

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    # history 가 있으면 앞에 붙인다 (multi_turn 케이스).
    for h in case.get("history") or []:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": mask_pii(case["input"])})

    assistant_content: list[dict[str, Any]] = []
    reply_text = mask_pii(case["reply"])
    if reply_text.strip():
        assistant_content.append({"type": "text", "text": reply_text})
    tool_calls = case.get("tool_calls") or []
    if tool_calls:
        assistant_content.extend(_tool_use_content(tool_calls))

    if not assistant_content:
        return None

    messages.append({"role": "assistant", "content": assistant_content})

    return {
        "messages": messages,
        "_meta": {
            "source": "synth",
            "category": case.get("_category"),
            "seed_id": case.get("_seed_id"),
            "pending_action": bool(case.get("pending_action")),
        },
    }


def _real_trace_to_sample(row: dict[str, Any], system_prompt: str) -> dict[str, Any] | None:
    """agent_traces row → 학습 샘플. label_verdict='bad' 는 제외."""
    if row.get("label_verdict") == "bad":
        return None
    user_msg = row.get("user_message") or ""
    assistant_reply = row.get("assistant_reply") or ""
    if not user_msg or not assistant_reply:
        return None

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    for h in row.get("history") or []:
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            if isinstance(content, str):
                messages.append({"role": role, "content": mask_pii(content)})

    messages.append({"role": "user", "content": mask_pii(user_msg)})

    assistant_content: list[dict[str, Any]] = [
        {"type": "text", "text": mask_pii(assistant_reply)},
    ]
    for tc in row.get("tool_calls") or []:
        if isinstance(tc, dict) and tc.get("name"):
            assistant_content.append(
                {"type": "tool_use", "name": tc["name"], "input": tc.get("input", {})},
            )

    messages.append({"role": "assistant", "content": assistant_content})

    return {
        "messages": messages,
        "_meta": {
            "source": "real",
            "trace_id": row.get("id"),
            "backend": row.get("backend"),
        },
    }


def main() -> int:
    system_prompt = load_system_prompt()
    print(f"[build] system prompt {len(system_prompt)}자", file=sys.stderr)

    samples: list[dict[str, Any]] = []

    for case in load_synth_cases():
        sample = _synth_to_sample(case, system_prompt)
        if sample:
            samples.append(sample)
    print(f"[build] synth 샘플 {len([s for s in samples if s['_meta']['source']=='synth'])}건", file=sys.stderr)

    for row in load_raw_traces():
        sample = _real_trace_to_sample(row, system_prompt)
        if sample:
            samples.append(sample)
    real_n = len([s for s in samples if s['_meta']['source']=='real'])
    print(f"[build] real 샘플 {real_n}건", file=sys.stderr)

    # 인터뷰 chain (interview_probe · findings · findings_turn · score)
    interview_samples = load_interview_seeds()
    samples.extend(interview_samples)
    print(f"[build] interview chain 샘플 {len(interview_samples)}건", file=sys.stderr)

    if not samples:
        print("[build] 빈 데이터셋 — 스크립트 순서 확인", file=sys.stderr)
        return 1

    random.seed(SEED)
    random.shuffle(samples)

    n = len(samples)
    n_train = int(n * SPLIT[0])
    n_val = int(n * SPLIT[1])
    train = samples[:n_train]
    val = samples[n_train : n_train + n_val]
    test = samples[n_train + n_val :]

    for path, part in [(OUT_TRAIN, train), (OUT_VAL, val), (OUT_TEST, test)]:
        with path.open("w", encoding="utf-8") as f:
            for s in part:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"[build] {path.name}: {len(part)}건", file=sys.stderr)

    print(f"[build] 완료 · 총 {n}건 · train={len(train)} val={len(val)} test={len(test)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
