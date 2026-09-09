"""FER2013 사진 + FERPlus 라벨을 합쳐 학습용 파일을 만든다.

    python build_ferplus.py

## 왜 라벨을 바꾸나

FER2013 은 **한 사람이** 3만 5천 장에 라벨을 붙였다. 그래서 틀린 것이 많고,
모델이 맞게 답해도 틀렸다고 배운다. 우리가 71% 에서 막힌 것이 그 천장이다
(사람도 이 데이터에서 ~65% 밖에 못 맞힌다).

FERPlus(마이크로소프트, MIT)는 **같은 사진에 10명이 투표해** 라벨을 다시 매겼다.
사진을 바꾸는 것이 아니라 **정답지를 바꾸는 것**이다.

## 덤 — 버릴 것을 알려 준다

`unknown`(판단 불가) · `NF`(얼굴 아님)가 표시돼 있다. 지금은 그것까지 넣고
배우고 있었다. 여기서 뺀다.

`contempt`(경멸)는 FERPlus 가 새로 넣은 8번째 표정인데 **쓰지 않는다** —
1·2차와 표정 7종을 맞춰야 비교가 된다.

## 순서

FERPlus 는 라벨만 있고 사진이 없다. 원본 `fer2013.csv` 의 **줄 순서**로 짝을
맞추는데, 우리가 처음 받은 파일(`Jeneral/fer-2013`)은 감정별로 묶여 있어 순서가
깨져 있었다. 그래서 원본 순서가 남아 있는 것을 따로 받아 쓴다.

순서가 맞는지는 **원래 라벨과 FERPlus 다수결의 일치율**로 확인한다 — 맞으면
60~70%(FERPlus 가 고친 만큼 차이), 어긋나면 20% 안팎이다.
"""

from __future__ import annotations

import csv
import io
import pickle
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from data import LABELS

HERE = Path(__file__).parent
DATA = HERE / "data"

# FERPlus 표 머리말 → 우리 표정 이름. `contempt` 는 빼서 7종을 유지한다.
TO_OURS = {
    "neutral": "neutral", "happiness": "happy", "surprise": "surprise",
    "sadness": "sad", "anger": "angry", "disgust": "disgust", "fear": "fear",
}
VOTE_COLUMNS = list(TO_OURS) + ["contempt", "unknown", "NF"]

# 원본 사진 (줄 순서 유지). 라벨 이름은 여기 순서를 따른다.
PARQUETS = {
    "Training": DATA / "_train.parquet",
    "PublicTest": DATA / "_pub.parquet",
    "PrivateTest": DATA / "_privateTest.parquet",
}
ORIGINAL_NAMES = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]


def majority(row: dict) -> str | None:
    """10명 투표의 최다 득표. `contempt`·`unknown`·`NF` 가 이기면 버린다(None)."""
    votes = {c: int(row[c]) for c in VOTE_COLUMNS}
    top = max(votes, key=votes.get)
    return TO_OURS.get(top)


def main() -> None:
    plus = list(csv.DictReader((DATA / "ferplus.csv").open(encoding="utf-8")))
    by_usage: dict[str, list[dict]] = {}
    for r in plus:
        by_usage.setdefault(r["Usage"], []).append(r)

    out: dict[str, list[dict]] = {"train": [], "test": []}
    dropped = Counter()
    agree = compare = 0

    for usage, path in PARQUETS.items():
        table = pq.read_table(path)
        images = table.column("image").to_pylist()
        labels = table.column("label").to_pylist()
        rows = by_usage[usage]
        assert len(images) == len(rows), f"{usage}: {len(images)} vs {len(rows)}"

        split = "train" if usage == "Training" else "test"
        for img, old, row in zip(images, labels, rows):
            new = majority(row)
            if new is None:
                dropped[max({c: int(row[c]) for c in ("contempt", "unknown", "NF")},
                            key=lambda c: int(row[c]))] += 1
                continue
            compare += 1
            agree += new == ORIGINAL_NAMES[old]
            out[split].append({"img_bytes": img["bytes"], "labels": new})

    print(f"순서 확인 — 원래 라벨과 일치 {agree / compare * 100:.1f}% "
          f"(60~70%면 맞다 · 20% 안팎이면 어긋난 것)")
    assert agree / compare > 0.45, "순서가 어긋났다 — 사진과 라벨이 짝이 안 맞는다"

    print(f"버린 사진: " + " · ".join(f"{k} {v:,}장" for k, v in dropped.items()))
    for split, rows in out.items():
        path = DATA / f"ferplus_{split}.pt"
        path.write_bytes(pickle.dumps(rows))
        counts = Counter(r["labels"] for r in rows)
        print(f"\n{split}: {len(rows):,}장 → {path.name}")
        for name in LABELS:
            print(f"  {name:9s} {counts[name]:6,}")


if __name__ == "__main__":
    main()
