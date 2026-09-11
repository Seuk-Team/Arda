"""synth_seed.yaml 의 시드마다 Claude Haiku 로 변형을 만든다.

원리:
    각 시드는 "이런 요청 → 이런 도구 호출 → 이런 답변" 의 뼈대다. Haiku 에게 그 뼈대를
    주고 "동일한 의도로 다른 표현·다른 이름·다른 ID 를 써서 N 개 생성해라" 라고 시킨다.
    산출물은 시드와 동일 스키마의 JSONL — build_dataset.py 가 나중에 병합·마스킹한다.

산출물: synth_cases.jsonl (각 줄 하나가 {input, tool_calls, reply, pending_action, ...}).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import yaml

try:
    from anthropic import Anthropic
except ImportError:
    print("anthropic 패키지 필요 · pip install -r requirements.txt", file=sys.stderr)
    sys.exit(1)


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
CACHE_PATH = Path(__file__).parent / ".synth_cache.jsonl"  # 이미 만든 seed_id 는 스킵

MODEL = "claude-haiku-4-5-20251001"
VARIATIONS_PER_SEED = 4
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


def load_cache() -> set[str]:
    if not CACHE_PATH.exists():
        return set()
    done = set()
    for line in CACHE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            done.add(json.loads(line)["_seed_id"])
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
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY 없음", file=sys.stderr)
        return 1

    client = Anthropic()
    seeds = load_seeds()
    done = load_cache()
    print(f"[expand] 시드 {len(seeds)}건 · 이미 처리 {len(done)}건", file=sys.stderr)

    # 이어 쓰기 — 이미 처리된 시드는 스킵.
    out_mode = "a" if CACHE_PATH.exists() else "w"
    cache_f = CACHE_PATH.open(out_mode, encoding="utf-8")

    total = 0
    for i, seed in enumerate(seeds, 1):
        sid = seed["id"]
        if sid in done:
            print(f"[expand] ({i}/{len(seeds)}) {sid} 스킵 (캐시)", file=sys.stderr)
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
            cache_f.write(json.dumps(case, ensure_ascii=False) + "\n")
        cache_f.flush()
        total += len(cases)
        print(f"[expand] ({i}/{len(seeds)}) {sid} → {len(cases)}건", file=sys.stderr)
        time.sleep(0.5)  # rate limit 여유

    cache_f.close()

    # 캐시 파일을 최종 산출물로 복사 (동일 내용).
    OUT_PATH.write_text(CACHE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"[expand] 총 {total}건 신규 → {OUT_PATH} (누적)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
