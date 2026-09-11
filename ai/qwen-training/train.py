"""Qwen3-8B QLoRA 학습 (RTX 4060 8GB).

- 4-bit nf4 + double quant · bfloat16 compute
- LoRA r=16 · attention + MLP projection 전부
- gradient checkpointing · batch 1 · grad accum 8 (실효 8)
- max_seq_length=2048 (OOM 나면 1024 로 내림)

산출물: output/checkpoint-*/adapter_model.safetensors
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import torch
from datasets import Dataset
from peft import LoraConfig, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
)
from trl import SFTConfig, SFTTrainer

ROOT = Path(__file__).parent
# ADR-0032 는 ollama `qwen3:8b` (Q4) 로 표기 · HF 상 대응은 `Qwen/Qwen3-8B` (Instruct 접미어 없음)
MODEL_ID = os.getenv("MODEL_ID", "Qwen/Qwen3-8B")
OUTPUT_DIR = ROOT / "output"
# T4 16GB (G4dn) 는 4096 여유 · median 4287 커버 · 4060 8GB 였다면 2048 · 환경변수로 오버라이드
MAX_SEQ_LENGTH = int(os.getenv("MAX_SEQ_LENGTH", "4096"))
NUM_EPOCHS = int(os.getenv("NUM_EPOCHS", "3"))
LEARNING_RATE = float(os.getenv("LEARNING_RATE", "2e-4"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
GRAD_ACCUM = int(os.getenv("GRAD_ACCUM", "8"))


def _render_assistant(content: Any) -> str:
    """assistant content(list[dict]) → 학습 대상 문자열.

    Qwen3 는 tool_call 을 `<tool_call>{"name":...,"arguments":...}</tool_call>` XML 로
    다룬다. 우리는 build_dataset.py 가 만든 list-of-blocks 구조를 그 형식으로 렌더링한다.
    """
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", ""))
        elif btype == "tool_use":
            payload = json.dumps(
                {"name": block["name"], "arguments": block.get("input", {})},
                ensure_ascii=False,
            )
            parts.append(f"<tool_call>\n{payload}\n</tool_call>")
    return "\n".join(p for p in parts if p)


def format_sample(sample: dict[str, Any], tokenizer) -> str:
    """{messages, _meta} → tokenizer chat_template 적용된 문자열."""
    rendered_messages = []
    for m in sample["messages"]:
        content = _render_assistant(m["content"]) if m["role"] == "assistant" else m["content"]
        rendered_messages.append({"role": m["role"], "content": content})
    return tokenizer.apply_chat_template(
        rendered_messages, tokenize=False, add_generation_prompt=False,
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    if not torch.cuda.is_available():
        print("[train] CUDA 없음 — 4060 을 못 본다. 드라이버·pytorch 빌드 확인.", file=sys.stderr)
        return 1
    print(f"[train] GPU: {torch.cuda.get_device_name(0)} · VRAM {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB", file=sys.stderr)

    train_path = ROOT / "dataset.train.jsonl"
    val_path = ROOT / "dataset.val.jsonl"
    if not train_path.exists():
        print("[train] dataset 없음 — build_dataset.py 먼저", file=sys.stderr)
        return 1

    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    print(f"[train] 모델 로드: {MODEL_ID}", file=sys.stderr)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb_cfg,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )
    model = prepare_model_for_kbit_training(model)

    # trl 1.13 SFTTrainer 는 peft_config 를 받아 자기 안에서 LoRA 를 씌우므로
    # 여기선 정의만 하고 넘긴다 · get_peft_model 을 미리 부르지 않는다.
    lora_cfg = LoraConfig(
        r=16,
        lora_alpha=32,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    train_raw = load_jsonl(train_path)
    val_raw = load_jsonl(val_path) if val_path.exists() else []
    print(f"[train] train={len(train_raw)} val={len(val_raw)}", file=sys.stderr)

    train_texts = [format_sample(s, tokenizer) for s in train_raw]
    val_texts = [format_sample(s, tokenizer) for s in val_raw] if val_raw else []

    train_ds = Dataset.from_dict({"text": train_texts})
    val_ds = Dataset.from_dict({"text": val_texts}) if val_texts else None

    args = SFTConfig(
        output_dir=str(OUTPUT_DIR),
        num_train_epochs=NUM_EPOCHS,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        learning_rate=LEARNING_RATE,
        warmup_ratio=0.03,
        lr_scheduler_type="cosine",
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        eval_strategy="epoch" if val_ds else "no",
        optim="paged_adamw_8bit",
        report_to="none",
        # SFT 전용
        max_length=MAX_SEQ_LENGTH,
        dataset_text_field="text",
        packing=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
        peft_config=lora_cfg,
    )

    print("[train] 학습 시작", file=sys.stderr)
    trainer.train()
    trainer.save_model(str(OUTPUT_DIR / "final"))
    tokenizer.save_pretrained(str(OUTPUT_DIR / "final"))
    print(f"[train] 완료 → {OUTPUT_DIR / 'final'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
