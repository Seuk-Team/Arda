"""LoRA 어댑터를 base 모델에 병합해 단일 모델로 저장.

Ollama·llama.cpp 는 어댑터 개념이 없다. 병합해서 하나의 safetensors 로 만들어야
GGUF 변환 파이프라인에 태울 수 있다.

주의: 병합 결과는 fp16 이라 ~15GB · 디스크 여유 확인.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="HF 모델 ID · 예: Qwen/Qwen3-8B")
    parser.add_argument("--adapter", required=True, help="LoRA 어댑터 폴더 · 예: ../qwen-training/output/final")
    parser.add_argument("--out", required=True, help="병합 결과 저장 폴더")
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.mkdir(parents=True, exist_ok=True)

    print(f"[merge] base = {args.base}", file=sys.stderr)
    print(f"[merge] adapter = {args.adapter}", file=sys.stderr)
    print(f"[merge] out = {out_path}", file=sys.stderr)

    print("[merge] 토크나이저 로드·저장", file=sys.stderr)
    tok = AutoTokenizer.from_pretrained(args.base, trust_remote_code=True)
    tok.save_pretrained(out_path)

    # base 를 CPU 로 로드 (GPU 8GB 로는 병합 힘듦 · fp16 · ~15GB RAM 필요)
    print("[merge] base 모델 로드 (CPU · fp16)", file=sys.stderr)
    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch.float16,
        device_map="cpu",
        trust_remote_code=True,
    )

    print("[merge] LoRA 어댑터 붙임", file=sys.stderr)
    model = PeftModel.from_pretrained(model, args.adapter)

    print("[merge] merge_and_unload · 병합 실행", file=sys.stderr)
    model = model.merge_and_unload()

    print(f"[merge] 저장 → {out_path}", file=sys.stderr)
    model.save_pretrained(out_path, safe_serialization=True)

    print(f"[merge] 완료 · 다음 단계: convert_to_gguf.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
