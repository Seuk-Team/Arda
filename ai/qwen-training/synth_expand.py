"""synth_seed.yaml 의 시드마다 Claude Haiku 로 변형을 만든다.

원리:
    각 시드는 "이런 요청 → 이런 도구 호출 → 이런 답변" 의 뼈대다. Haiku 에게 그 뼈대를
    주고 "동일한 의도로 다른 표현·다른 이름·다른 ID 를 써서 N 개 생성해라" 라고 시킨다.
    산출물은 시드와 동일 스키마의 JSONL — build_dataset.py 가 나중에 병합·마스킹한다.

산출물: synth_cases.jsonl (각 줄 하나가 {input, tool_calls, reply, pending_action, ...}).

사용:
    python synth_expand.py                              # 기본 pass=0 · 변형 4개
    VARIATIONS_PER_SEED=8 SYNTH_PASS=1 python synth_expand.py  # 두 번째 pass · 시드마다 8개 더

여러 pass 로 누적할 때 원칙:
    - `SYNTH_PASS` 를 매 실행에 새 값으로 (0, 1, 2, ...) — 캐시가 (seed_id, pass) 로 관리.
    - Haiku 는 확률적이라 pass 마다 표현이 달라진다 (같은 시드에서 다른 발화).
    - 단 카테고리 balance 는 확인해야 함 — 어떤 시드는 좋은 변형이 어렵다 (multi_turn 등).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml

# anthropic 은 Haiku 확장 경로에서만 필요하다 — 오프라인($0) 모드는 패키지 없이 돌아야
# 하므로 최상단에서 import 하지 않고, 실제 호출 직전에 지연 import 한다.


def _load_dotenv() -> None:
    """backend/.env 에서 ANTHROPIC_API_KEY 를 os.environ 에 채운다.

    python-dotenv 안 깔려도 돌게 · 직접 파싱. 이미 환경변수에 있으면 놔둔다.
    """
    if os.getenv("ANTHROPIC_API_KEY"):
        return
    env_path = Path(__file__).parent.parent.parent / "backend" / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


_load_dotenv()

SEED_PATH = Path(__file__).parent / "synth_seed.yaml"
OUT_PATH = Path(__file__).parent / "synth_cases.jsonl"
OFFLINE_PATH = Path(__file__).parent / "synth_offline.jsonl"  # 오프라인($0) 산출물
CACHE_PATH = Path(__file__).parent / ".synth_cache.jsonl"  # 이미 만든 (seed_id, pass) 는 스킵

MODEL = "claude-haiku-4-5-20251001"
# 시드 하나에서 몇 개의 변형을 만들지. 지금까지 4 로 돌아 188건 만들었음. env 로 오버라이드.
VARIATIONS_PER_SEED = int(os.getenv("VARIATIONS_PER_SEED", "4"))
# 여러 번 돌려 누적할 때 각 실행에 라벨을 붙인다 (2026-09-14). 캐시 키가
# (seed_id, pass) 라 같은 시드에서 pass 를 바꿔 다시 실행하면 새 변형이 추가된다.
# 예: 첫 실행 (기본 pass="0") · 두 번째 실행 (`SYNTH_PASS=1` 로 지정) → 시드마다
# `VARIATIONS_PER_SEED` 개 더 생성. Haiku 는 확률적이라 pass 마다 표현이 달라진다.
SYNTH_PASS = os.getenv("SYNTH_PASS", "0")
MAX_TOKENS = 2048
TEMPERATURE = 0.7

# Haiku 에게 통째로 던지는 지시. 각 시드가 뭘 만들지 이 프롬프트로 결정된다.
EXPAND_PROMPT = """\
당신은 채용 ATS 의 AI 어시스턴트 "아르" 학습 데이터를 만든다.

아래 시드 케이스와 동일한 의도·같은 카테고리의 변형을 {n}개 만들어라.

원칙:
- 사용자 발화(input)만 자연스럽게 바꿔라 — 담당자 톤(반말·간결) · 다른 이름·ID·기술 키워드 사용.
- tool_calls 구조와 answer 의 형식은 시드와 동일하게 유지.
- reply 는 시드의 reply_pattern 문자열을 반드시 포함하고, 아르 페르소나(존댓말·간결·표 대신 굵게+목록)로 답하라.
- 응답은 **JSON 만** 반환 — {{"cases": [...]}}
- 각 case 는: {{"input", "tool_calls", "reply", "pending_action"(bool), "history"(선택)}}

시드:
```yaml
{seed}
```

주의:
- 데이터 자체는 시연·시나리오여도 무방하나, 실제 사람 이름(연예인·정치인)이나 실제 회사명은 넣지 마라.
- 지어낸 지원자 정보(학력·경력·기술)를 answer 에 상세히 나열하지 마라 — 어차피 도구 결과가 앞에 있다고 가정하고, "확인했습니다" 정도로 짧게.
- 시드에 history 가 있으면 각 변형도 유사한 history 를 만들어라 (다른 이름으로).
- 카테고리별 원칙:
  - search: 부드러운 톤·도구 호출은 정확한 필드만
  - write: 확인 요청 문구 · pending_action=true (도구는 부르지만 아직 실행 아님)
  - mail: draft 는 pending 없음 · send 는 pending 필수
  - refuse: 채용 밖 질문 · "채용" 단어를 답에 포함
  - hallucination: 도구 결과가 없다고 가정 · "찾지 못" · "확인 필요"
"""


def load_seeds() -> list[dict[str, Any]]:
    data = yaml.safe_load(SEED_PATH.read_text(encoding="utf-8"))
    return data["seeds"]


def run_offline() -> int:
    """Claude API 없이($0) 시드 자체를 1:1 케이스로 굳힌다.

    `reply` 필드를 손으로 달아 둔 시드만 대상 — build_dataset 은 input+reply 가 있어야
    샘플로 받는다. Haiku 변형이 어려운/불필요한 도구(신규 도구·라우팅 교정)를 정확히
    한 번씩 앵커로 넣는 용도다. 산출물 synth_offline.jsonl 은 build_dataset 이 synth_cases
    와 함께 병합한다. Haiku 캐시(.synth_cache)를 건드리지 않으므로, 나중에 예산이 되면
    같은 시드를 Haiku 로 추가 확장하는 것과 공존한다.
    """
    seeds = load_seeds()
    n = 0
    with OFFLINE_PATH.open("w", encoding="utf-8") as f:
        for seed in seeds:
            reply = seed.get("reply")
            if not reply:
                continue  # 손 reply 없는(=Haiku 로 채우는) 시드는 건너뛴다
            case = {
                "input": seed["input"],
                "tool_calls": seed.get("tool_calls", []),
                "reply": reply,
                "pending_action": bool(seed.get("pending_action")),
                "_seed_id": seed["id"],
                "_category": seed.get("category"),
                "_pass": "offline",
            }
            if seed.get("history"):
                case["history"] = seed["history"]
            f.write(json.dumps(case, ensure_ascii=False) + "\n")
            n += 1
    print(f"[expand] 오프라인 {n}건 → {OFFLINE_PATH} (Claude API 미사용 · $0)")
    return 0


def load_cache() -> set[tuple[str, str]]:
    """이미 처리된 `(seed_id, pass)` 조합을 돌려준다. 같은 seed_id 라도 pass 가 다르면
    재생성 대상 — 여러 pass 를 돌려 데이터 누적할 수 있게 한다.
    """
    if not CACHE_PATH.exists():
        return set()
    done = set()
    for line in CACHE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            case = json.loads(line)
            # 옛 캐시에는 _pass 없음 → "0" 으로 취급 (첫 번째 실행분).
            done.add((case["_seed_id"], case.get("_pass", "0")))
        except (json.JSONDecodeError, KeyError):
            continue
    return done


def expand_one(client: Anthropic, seed: dict[str, Any]) -> list[dict[str, Any]]:
    prompt = EXPAND_PROMPT.format(
        n=VARIATIONS_PER_SEED,
        seed=yaml.dump(seed, allow_unicode=True, sort_keys=False),
    )
    # anthropic SDK v1.x messages.create 는 temperature 를 안 받는다 · 기본값 사용
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in resp.content if hasattr(block, "text"))

    # Haiku 가 앞뒤에 텍스트를 붙일 수 있으니 JSON 만 뽑아냄.
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"JSON 못 찾음: {text[:200]}")
    payload = json.loads(text[start : end + 1])
    return payload.get("cases", [])


def main() -> int:
    # 오프라인($0) 모드: Haiku 없이 손 reply 시드만 케이스화한다.
    if os.getenv("SYNTH_OFFLINE") or "--offline" in sys.argv:
        return run_offline()

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 없음", file=sys.stderr)
        return 1

    try:
        from anthropic import Anthropic
    except ImportError:
        print("anthropic 패키지 필요 · pip install -r requirements.txt", file=sys.stderr)
        return 1

    client = Anthropic()
    seeds = load_seeds()
    done = load_cache()
    print(
        f"[expand] 시드 {len(seeds)}건 · 이미 처리 {len(done)}건 "
        f"· pass={SYNTH_PASS} · 변형={VARIATIONS_PER_SEED}",
        file=sys.stderr,
    )

    # 이어 쓰기 — 이미 처리된 (seed_id, pass) 는 스킵.
    out_mode = "a" if CACHE_PATH.exists() else "w"
    cache_f = CACHE_PATH.open(out_mode, encoding="utf-8")

    total = 0
    for i, seed in enumerate(seeds, 1):
        sid = seed["id"]
        if (sid, SYNTH_PASS) in done:
            print(f"[expand] ({i}/{len(seeds)}) {sid} 스킵 (pass={SYNTH_PASS} 이미 있음)", file=sys.stderr)
            continue

        try:
            cases = expand_one(client, seed)
        except Exception as exc:
            print(f"[expand] ({i}/{len(seeds)}) {sid} 실패: {exc}", file=sys.stderr)
            time.sleep(2)
            continue

        for case in cases:
            case["_seed_id"] = sid
            case["_category"] = seed["category"]
            case["_pass"] = SYNTH_PASS
            cache_f.write(json.dumps(case, ensure_ascii=False) + "\n")
        cache_f.flush()
        total += len(cases)
        print(f"[expand] ({i}/{len(seeds)}) {sid} → {len(cases)}건 (pass={SYNTH_PASS})", file=sys.stderr)
        time.sleep(0.5)  # rate limit 여유

    cache_f.close()

    # 캐시 파일을 최종 산출물로 복사 (동일 내용).
    OUT_PATH.write_text(CACHE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[expand] 총 {total}건 신규 → {OUT_PATH} (누적 · pass={SYNTH_PASS})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
