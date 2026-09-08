"""ViT 로 표정 7종을 분류하도록 학습시킨다 (ADR-0032).

구글이 공개한 ViT-base 는 이미 사진 백만 장으로 "사물 보는 법"을 배운 상태다.
거기서 마지막 분류층만 표정 7종으로 갈아 끼우고 이어서 학습한다(파인튜닝).
처음부터 배우게 하면 우리 3만 5천 장으로는 어림도 없다.

    python train.py                  # 기본값으로 학습
    python train.py --epochs 5 --batch 32

**체크포인트는 가장 좋은 것 하나만 남긴다.** 이 PC 는 여유 공간이 8GB 뿐이고
한 개가 330MB 다. 에폭마다 남기면 몇 번 만에 하드가 찬다.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from torchvision import transforms
from transformers import ViTForImageClassification

from data import LABELS, Fer2013

HERE = Path(__file__).parent
OUT = HERE / "runs"

# 구글 ViT-base. 224×224 를 16×16 조각으로 잘라 보는 모델이다.
BASE_MODEL = "google/vit-base-patch16-224-in21k"

# ImageNet 평균·표준편차. ViT 가 이 값으로 정규화된 사진을 보도록 배웠다.
MEAN = [0.5, 0.5, 0.5]
STD = [0.5, 0.5, 0.5]

# 학습용만 좌우 뒤집기·살짝 자르기를 한다. 같은 사진을 매번 조금씩 다르게 보여
# 주면 외우지 못하고 특징을 배운다. 평가용에 하면 점수가 흔들려 못 쓴다.
TRAIN_TF = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomAffine(degrees=10, translate=(0.05, 0.05), scale=(0.95, 1.05)),
    transforms.ToTensor(),
    transforms.Normalize(MEAN, STD),
])
EVAL_TF = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(MEAN, STD),
])


def build_model():
    return ViTForImageClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(LABELS),
        id2label={i: name for i, name in enumerate(LABELS)},
        label2id={name: i for i, name in enumerate(LABELS)},
    )


@torch.no_grad()
def accuracy(model, loader, device, amp=False) -> float:
    """평가도 학습과 같은 정밀도로 돈다.

    fp32 로 돌리면 학습 때 잡아 둔 메모리가 아직 남아 있는 상태에서 8GB 를
    넘긴다 — 첫 에폭 평가에서 그렇게 죽었다.
    """
    model.eval()
    right = total = 0
    for images, labels in loader:
        with torch.amp.autocast("cuda", enabled=amp):
            pred = model(images.to(device)).logits.argmax(-1).cpu()
        right += (pred == labels).sum().item()
        total += labels.numel()
    return right / total


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--lr", type=float, default=3e-5)
    # 8GB 카드라 fp16 으로 돈다. 메모리가 절반이고 이 카드에서는 더 빠르다.
    p.add_argument("--fp32", action="store_true", help="fp16 을 끄고 fp32 로")
    args = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        print("⚠ GPU 를 못 찾았다. CPU 로는 한 에폭에 몇 시간 걸린다.")
    else:
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    train_ds = Fer2013("train", TRAIN_TF)
    test_ds = Fer2013("test", EVAL_TF)
    print(f"학습 {len(train_ds):,}장 · 평가 {len(test_ds):,}장")

    # num_workers=0: 윈도우는 워커마다 프로세스를 새로 띄우느라 오히려 느려질 때가 많다.
    train_dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=0)
    test_dl = DataLoader(test_ds, batch_size=args.batch, num_workers=0)

    model = build_model().to(device)
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr)
    steps = args.epochs * len(train_dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(optim, max_lr=args.lr, total_steps=steps)
    amp = device == "cuda" and not args.fp32
    scaler = torch.amp.GradScaler("cuda", enabled=amp)

    OUT.mkdir(exist_ok=True)
    best = 0.0
    history = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        started, seen, loss_sum = time.time(), 0, 0.0
        for i, (images, labels) in enumerate(train_dl, 1):
            images, labels = images.to(device), labels.to(device)
            optim.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=amp):
                loss = model(images, labels=labels).loss
            scaler.scale(loss).backward()
            scaler.step(optim)
            scaler.update()
            sched.step()

            loss_sum += loss.item() * labels.numel()
            seen += labels.numel()
            if i % 50 == 0 or i == len(train_dl):
                per = (time.time() - started) / i
                left = per * (len(train_dl) - i)
                print(f"\r  에폭 {epoch}  {i}/{len(train_dl)}  "
                      f"loss {loss_sum / seen:.4f}  남은 시간 {left / 60:.1f}분",
                      end="", flush=True)

        # 학습이 잡고 있던 조각을 돌려준 뒤 평가한다. 8GB 카드에서는 이것만으로도
        # 여유가 크게 달라진다.
        torch.cuda.empty_cache() if device == 'cuda' else None
        acc = accuracy(model, test_dl, device, amp=amp)
        took = (time.time() - started) / 60
        print(f"\r  에폭 {epoch} 끝 — loss {loss_sum / seen:.4f} · "
              f"평가 정확도 {acc * 100:.2f}% · {took:.1f}분" + " " * 20)
        history.append({"epoch": epoch, "loss": loss_sum / seen, "accuracy": acc})

        # **가장 좋은 것만 남긴다.** 덮어쓰므로 폴더가 커지지 않는다.
        if acc > best:
            best = acc
            model.save_pretrained(OUT / "best")
            print(f"    → 최고 기록. {OUT / 'best'} 에 저장")

    (OUT / "history.json").write_text(
        json.dumps({"best_accuracy": best, "epochs": history}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n최고 정확도 {best * 100:.2f}%  ·  다음: python evaluate.py")


if __name__ == "__main__":
    main()
