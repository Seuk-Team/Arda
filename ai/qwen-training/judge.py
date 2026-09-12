"""판정 규칙 — 모델이 무엇이든 **같은 자로 잰다**.

원래 eval.py 안에 있었다. 2026-09-12 에 Claude 를 같은 규칙으로 재려고 떼어냈다 —
채점기가 두 벌이면 "26% vs 85%" 같은 숫자를 나란히 놓을 수 없다. 이 파일은
torch·transformers 를 import 하지 않는다: GPU 없이도 채점만 돌 수 있어야 한다.

판정 요약 (evaluate_one):
- hard : 도구 이름 일치 · no-tool 위반 없음 · 쓰기 도구면 확인 문구 있음
- soft : 인자 부분 일치 **또는** 응답 키워드 2/3 이상
- 종합 : hard 전부 + soft 하나 이상
"""
from __future__ import annotations

import json
import re
from typing import Any

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
