"""학습한 모델이 뭘 맞히고 뭘 틀리는지 본다.

정확도 하나로는 어디가 문제인지 모른다. **혼동 행렬**은 "무서움을 슬픔으로 잘못
봤다" 같은 걸 칸마다 보여 준다 — 표정 데이터는 종류별 장수가 크게 달라서
(웃음 7,215장 vs 역겨움 436장) 전체 정확도가 높아도 적은 쪽은 거의 못 맞히는
일이 흔하다. 그건 정확도만 봐서는 안 보인다.

    python evaluate.py
    python evaluate.py --model runs/best
"""

from __future__ import annotations

import argparse
from pathlib import Path

import torch
from torch.utils.data import DataLoader
from transformers import ViTForImageClassification

from data import KOREAN, LABELS, Fer2013
from train import EVAL_TF, latest_run

HERE = Path(__file__).parent


@torch.no_grad()
def collect(model, loader, device):
    """(정답, 예측) 을 전부 모은다."""
    model.eval()
    truths, preds = [], []
    for images, labels in loader:
        preds.append(model(images.to(device)).logits.argmax(-1).cpu())
        truths.append(labels)
    return torch.cat(truths), torch.cat(preds)


def confusion(truths, preds, n):
    m = torch.zeros(n, n, dtype=torch.int32)
    for t, p in zip(truths.tolist(), preds.tolist()):
        m[t][p] += 1
    return m


def main():
    p = argparse.ArgumentParser()
    # 비우면 모델이 들어 있는 가장 최근 회차를 쓴다
    p.add_argument("--model", default="")
    p.add_argument("--batch", type=int, default=64)
    args = p.parse_args()

    if not Path(args.model).exists():
        raise SystemExit(f"모델이 없다: {args.model}\n먼저 `python train.py` 를 돌린다.")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = ViTForImageClassification.from_pretrained(model_dir).to(device)
    loader = DataLoader(Fer2013("test", EVAL_TF), batch_size=args.batch)

    truths, preds = collect(model, loader, device)
    n = len(LABELS)
    m = confusion(truths, preds, n)
    total = int(m.sum())

    print(f"\n전체 정확도  {m.diag().sum().item() / total * 100:.2f}%   ({total:,}장)\n")

    # ── 혼동 행렬 ──
    head = "".join(f"{KOREAN[name][:3]:>7s}" for name in LABELS)
    print(f"{'정답\\예측':>10s}{head}")
    for i, name in enumerate(LABELS):
        row = "".join(f"{int(v):>7d}" for v in m[i])
        print(f"{KOREAN[name]:>10s}{row}")

    # ── 종류별 성적 ──
    # 장수가 크게 다르므로 종류마다 따로 본다. 적은 표정을 통째로 못 맞히는 것이
    # 여기서 0% 로 드러난다.
    print(f"\n{'표정':>8s}{'장수':>8s}{'맞힘':>8s}{'재현율':>9s}{'정밀도':>9s}")
    for i, name in enumerate(LABELS):
        got, actual, said = int(m[i][i]), int(m[i].sum()), int(m[:, i].sum())
        recall = got / actual if actual else 0
        precision = got / said if said else 0
        print(f"{KOREAN[name]:>8s}{actual:>8,}{got:>8,}"
              f"{recall * 100:>8.1f}%{precision * 100:>8.1f}%")

    print("\n재현율 = 그 표정 중 몇 %를 맞혔나   ·   정밀도 = 그 표정이라 답한 것 중 몇 %가 맞았나")

    # 가장 자주 틀리는 짝
    wrong = [(int(m[i][j]), i, j) for i in range(n) for j in range(n) if i != j]
    print("\n가장 많이 헷갈린 것")
    for count, i, j in sorted(wrong, reverse=True)[:5]:
        print(f"  {KOREAN[LABELS[i]]} → {KOREAN[LABELS[j]]} 로 {count:,}번")


if __name__ == "__main__":
    main()
