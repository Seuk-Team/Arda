"""ViT 로 표정 7종을 분류하도록 학습시킨다 (ADR-0032).

구글이 공개한 ViT-base 는 이미 사진 백만 장으로 "사물 보는 법"을 배운 상태다.
거기서 마지막 분류층만 표정 7종으로 갈아 끼우고 이어서 학습한다(파인튜닝).
처음부터 배우게 하면 우리 3만 5천 장으로는 어림도 없다.

    python train.py                          # 다음 번호로 새 회차
    python train.py --name 03-증강만          # 이름을 직접
    python train.py --epochs 5 --no-weights   # 조건 바꿔 비교

**회차마다 폴더가 따로 생긴다** — `runs/01-기본/`, `runs/02-…/`. 앞 회차를 덮어쓰지
않아야 무엇을 바꿔서 무엇이 달라졌는지 비교할 수 있다(`python compare.py`).

**한 회차 안에서는 가장 좋은 것 하나만 남긴다.** 체크포인트 한 개가 330MB 라
에폭마다 남기면 하드가 금방 찬다. 회차가 쌓여 공간이 모자라면 `best/` 만
지우면 된다 — `history.json` 은 작고, 비교에 필요한 것은 그쪽이다.
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

from data import KOREAN, LABELS, Fer2013

HERE = Path(__file__).parent
OUT = HERE / "runs"

# 구글 ViT-base. 224×224 를 16×16 조각으로 잘라 보는 모델이다.
BASE_MODEL = "google/vit-base-patch16-224-in21k"

# ImageNet 평균·표준편차. ViT 가 이 값으로 정규화된 사진을 보도록 배웠다.
MEAN = [0.5, 0.5, 0.5]
STD = [0.5, 0.5, 0.5]

# 학습용만 좌우 뒤집기·자르기·색조를 한다. 같은 사진을 매번 다르게 보여 주면
# 외우지 못하고 특징을 배운다. 평가용에 하면 점수가 흔들려 못 쓴다.
#
# 1차(5 에폭 69.84%)보다 세게 잡았다. 마지막 에폭에서 loss 는 계속 떨어지는데
# 정확도는 0.25%p 밖에 안 올랐다 — 외우기 시작했다는 뜻이라 흔드는 폭을 키운다.
TRAIN_TF = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.RandomHorizontalFlip(),
    transforms.RandomResizedCrop(224, scale=(0.75, 1.0), ratio=(0.9, 1.1)),
    transforms.RandomAffine(degrees=15, translate=(0.08, 0.08), scale=(0.9, 1.1)),
    transforms.ColorJitter(brightness=0.3, contrast=0.3),
    transforms.ToTensor(),
    transforms.Normalize(MEAN, STD),
    # 얼굴 일부를 가려 한 부위에만 기대지 않게 한다(입만 보고 웃음이라 하지 않게).
    transforms.RandomErasing(p=0.25, scale=(0.02, 0.12)),
])
EVAL_TF = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(MEAN, STD),
])


def _next_name() -> str:
    """`02`, `03` … 앞 회차를 덮어쓰지 않게 다음 번호를 고른다."""
    used = [d.name for d in OUT.glob("[0-9][0-9]-*") if d.is_dir()]
    n = max((int(x[:2]) for x in used), default=0) + 1
    return f"{n:02d}-실험"


def processor():
    """평가용 변환(`EVAL_TF`)과 같은 전처리를 하는 HuggingFace 프로세서.

    학습은 torchvision 으로 하고 배포는 프로세서로 받는다. 두 길이 갈리면
    정확도가 조용히 떨어지므로 **여기 한 곳에서만** 값을 정한다.
    """
    from transformers import ViTImageProcessor

    return ViTImageProcessor(
        do_resize=True, size={"height": 224, "width": 224}, resample=2,
        do_rescale=True, rescale_factor=1 / 255,
        do_normalize=True, image_mean=MEAN, image_std=STD,
    )


def latest_run() -> Path | None:
    """모델이 들어 있는 가장 최근 회차. 평가·데모가 기본으로 쓴다."""
    runs = sorted(d for d in OUT.glob("*") if (d / "best").exists())
    return runs[-1] if runs else None


def build_model():
    return ViTForImageClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(LABELS),
        id2label={i: name for i, name in enumerate(LABELS)},
        label2id={name: i for i, name in enumerate(LABELS)},
    )


def class_weights(ds, device):
    """장수가 적은 표정에 더 큰 벌점을 준다.

    **왜 필요한가.** 1차 학습에서 웃음(7,215장)은 90.1% 를 맞혔는데 역겨움(436장)은
    32.4% 였다. 그냥 두면 모델은 흔한 표정만 맞혀도 전체 정확도가 오르므로 적은
    표정을 버리는 쪽이 이득이다. 가중치를 주면 그 이득이 사라진다.

    **전체 정확도는 오히려 조금 내려갈 수 있다.** 우리가 보고 싶은 것은 긴장·불안
    계열(무서움 47.2% · 슬픔 55.3%)이라 그 편이 낫다(ADR-0032).
    """
    counts = ds.label_counts()
    n = torch.tensor([counts[name] for name in LABELS], dtype=torch.float32)
    w = n.sum() / (len(LABELS) * n)      # 적을수록 크다
    return w.to(device)


@torch.no_grad()
def evaluate(model, loader, device, amp=False):
    """(전체 정확도, 표정별 정답률). **한 번만 돈다** — 두 번 돌면 에폭마다 30초를 더 쓴다.

    평가도 학습과 같은 정밀도로 한다. fp32 로 돌리면 학습이 잡아 둔 메모리가
    남아 있는 상태에서 8GB 를 넘긴다 — 첫 시도가 그렇게 죽었다.
    """
    model.eval()
    hit = torch.zeros(len(LABELS))
    total = torch.zeros(len(LABELS))
    for images, labels in loader:
        with torch.amp.autocast("cuda", enabled=amp):
            pred = model(images.to(device)).logits.argmax(-1).cpu()
        for t, p in zip(labels.tolist(), pred.tolist()):
            total[t] += 1
            hit[t] += t == p
    return (hit.sum() / total.sum()).item(), (hit / total.clamp(min=1)).tolist()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=9)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--lr", type=float, default=3e-5)
    # 8GB 카드라 fp16 으로 돈다. 메모리가 절반이고 이 카드에서는 더 빠르다.
    p.add_argument("--fp32", action="store_true", help="fp16 을 끄고 fp32 로")
    p.add_argument("--no-weights", action="store_true", help="클래스 가중치를 끈다")
    # FER2013 은 라벨 자체가 부정확한 것으로 알려져 있다(사람도 ~65%). 정답을
    # 100% 로 믿지 말라고 알려 주면 잡음에 덜 휘둘린다.
    p.add_argument("--smoothing", type=float, default=0.1)
    p.add_argument("--name", default="", help="회차 이름. 비우면 번호가 자동으로 붙는다")
    p.add_argument("--data", default="fer2013", choices=["fer2013", "ferplus"],
                   help="ferplus 는 같은 사진에 10명이 다시 매긴 라벨(build_ferplus.py)")
    args = p.parse_args()

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu":
        print("⚠ GPU 를 못 찾았다. CPU 로는 한 에폭에 몇 시간 걸린다.")
    else:
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    train_ds = Fer2013("train", TRAIN_TF, source=args.data)
    test_ds = Fer2013("test", EVAL_TF, source=args.data)
    print(f"데이터: {args.data} · 학습 {len(train_ds):,}장 · 평가 {len(test_ds):,}장")

    # num_workers=0: 윈도우는 워커마다 프로세스를 새로 띄우느라 오히려 느려질 때가 많다.
    train_dl = DataLoader(train_ds, batch_size=args.batch, shuffle=True, num_workers=0)
    test_dl = DataLoader(test_ds, batch_size=args.batch, num_workers=0)

    model = build_model().to(device)
    weights = None if args.no_weights else class_weights(train_ds, device)
    if weights is not None:
        print("클래스 가중치: " + " · ".join(
            f"{KOREAN[n]} {w:.2f}" for n, w in zip(LABELS, weights.tolist())))
    loss_fn = torch.nn.CrossEntropyLoss(weight=weights, label_smoothing=args.smoothing)
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr)
    steps = args.epochs * len(train_dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(optim, max_lr=args.lr, total_steps=steps)
    amp = device == "cuda" and not args.fp32
    scaler = torch.amp.GradScaler("cuda", enabled=amp)

    OUT.mkdir(exist_ok=True)
    out = OUT / (args.name or _next_name())
    out.mkdir(parents=True, exist_ok=True)
    print(f"결과 폴더: {out}")
    best = 0.0
    history = []

    for epoch in range(1, args.epochs + 1):
        model.train()
        started, seen, loss_sum = time.time(), 0, 0.0
        for i, (images, labels) in enumerate(train_dl, 1):
            images, labels = images.to(device), labels.to(device)
            optim.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=amp):
                # 모델이 안에서 계산하는 loss 를 쓰지 않는다 — 가중치와 스무딩을
                # 우리가 넣어야 한다.
                loss = loss_fn(model(images).logits, labels)
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
        acc, recalls = evaluate(model, test_dl, device, amp=amp)
        took = (time.time() - started) / 60
        print(f"\r  에폭 {epoch} 끝 — loss {loss_sum / seen:.4f} · "
              f"평가 정확도 {acc * 100:.2f}% · {took:.1f}분" + " " * 20)
        macro = sum(recalls) / len(recalls)
        print("    표정별: " + " · ".join(
            f"{KOREAN[n]} {r*100:.0f}%" for n, r in zip(LABELS, recalls)))
        print(f"    표정 평균(macro) {macro*100:.2f}%")
        history.append({"epoch": epoch, "loss": loss_sum / seen, "accuracy": acc,
                        "macro_recall": macro,
                        "per_class": dict(zip(LABELS, recalls))})

        # **가장 좋은 것만 남긴다.** 덮어쓰므로 폴더가 커지지 않는다.
        # 기준은 전체 정확도가 아니라 **표정 평균**이다 — 전체로 고르면 흔한
        # 표정(웃음 7,215장)만 잘 맞히는 모델이 뽑힌다.
        if macro > best:
            best = macro
            model.save_pretrained(out / "best")
            # **전처리 설정을 같이 남긴다.** 이게 없으면 받아 쓰는 쪽이 나름대로
            # 전처리해서 학습 때와 달라진다 — 에러가 아니라 값이 조금 달라질 뿐이라
            # 정확도가 조용히 떨어지고 원인이 안 보인다.
            processor().save_pretrained(out / "best")
            print(f"    → 최고 기록. {out / 'best'} 에 저장")

    (out / "history.json").write_text(
        json.dumps({"설정": vars(args), "best_macro_recall": best,
                    "best_accuracy": max(h["accuracy"] for h in history),
                    "epochs": history}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n최고 정확도 {best * 100:.2f}%  ·  다음: python evaluate.py")


if __name__ == "__main__":
    main()
