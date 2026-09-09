"""학습한 모델로 사진 한 장의 표정을 맞혀 본다.

    python predict.py 사진.jpg
    python predict.py 사진1.jpg 사진2.png ...
    python predict.py 폴더

얼굴이 화면을 꽉 채운 사진일수록 잘 맞힌다 — FER2013 이 그런 사진으로만
학습돼 있어서다. 배경이 넓거나 얼굴이 작으면 값이 흐려진다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from PIL import Image
from transformers import ViTForImageClassification

from data import KOREAN, LABELS
from train import EVAL_TF, latest_run

HERE = Path(__file__).parent
MODEL_DIR = (latest_run() or HERE) / "best"
SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def paths_from(args: list[str]) -> list[Path]:
    out = []
    for a in args:
        p = Path(a)
        if p.is_dir():
            out += sorted(f for f in p.iterdir() if f.suffix.lower() in SUFFIXES)
        elif p.exists():
            out.append(p)
        else:
            print(f"없는 파일: {p}")
    return out


def main():
    files = paths_from(sys.argv[1:])
    if not files:
        raise SystemExit(__doc__)
    if not MODEL_DIR.exists():
        raise SystemExit(f"학습된 모델이 없다: {MODEL_DIR}\n먼저 `python train.py`.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ViTForImageClassification.from_pretrained(MODEL_DIR).to(device).eval()

    batch = torch.stack([EVAL_TF(Image.open(f).convert("RGB")) for f in files])
    with torch.no_grad():
        probs = torch.softmax(model(batch.to(device)).logits, -1).cpu()

    for f, p in zip(files, probs):
        order = p.argsort(descending=True)
        top = LABELS[order[0]]
        print(f"\n{f.name}  →  \033[1m{KOREAN[top]}\033[0m ({p[order[0]] * 100:.0f}%)")
        for i in order[:4]:
            bar = "█" * int(p[i] * 30)
            print(f"   {KOREAN[LABELS[i]]:>4s} {p[i] * 100:5.1f}%  {bar}")


if __name__ == "__main__":
    main()
