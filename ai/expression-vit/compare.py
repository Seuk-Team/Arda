"""회차들을 나란히 본다.

    python compare.py

**전체 정확도와 표정 평균을 같이 본다.** 전체만 보면 흔한 표정(웃음 7,215장)만
잘 맞히는 모델이 좋아 보인다 — 우리가 쓰고 싶은 것은 긴장·불안 계열이다.
"""

import json
from pathlib import Path

from data import KOREAN, LABELS

RUNS = Path(__file__).parent / "runs"


def main():
    rows = []
    for d in sorted(RUNS.iterdir()):
        f = d / "history.json"
        if not f.is_file():
            continue
        h = json.loads(f.read_text(encoding="utf-8"))
        # **한 회차 안에서 기준을 섞지 않는다.** 표정 평균이 기록된 에폭이 있으면
        # 그중에서 고른다 — 전체 정확도(69%)와 표정 평균(63%)은 단위가 달라
        # 섞어서 max 를 하면 엉뚱한 에폭이 뽑힌다.
        scored = [e for e in h["epochs"] if "macro_recall" in e]
        best = (max(scored, key=lambda e: e["macro_recall"]) if scored
                else max(h["epochs"], key=lambda e: e["accuracy"]))
        rows.append((d.name, h, best))

    if not rows:
        raise SystemExit("아직 회차가 없다. `python train.py` 를 먼저 돌린다.")

    print(f"\n{'회차':<18}{'에폭':>5}{'전체':>9}{'표정평균':>10}   설정")
    for name, h, best in rows:
        cfg = h.get("설정", {})
        bits = []
        if cfg:
            bits.append(f"{cfg.get('epochs')}에폭")
            if cfg.get("no_weights") is False:
                bits.append("가중치")
            if cfg.get("smoothing"):
                bits.append(f"스무딩{cfg['smoothing']}")
        macro = best.get("macro_recall")
        print(f"{name:<18}{best['epoch']:>5}{best['accuracy']*100:>8.2f}%"
              f"{(macro*100 if macro else float('nan')):>9.2f}%   {' · '.join(bits)}")

    print(f"\n표정별 (각 회차의 가장 좋은 에폭)")
    print(f"{'회차':<18}" + "".join(f"{KOREAN[n][:3]:>7s}" for n in LABELS))
    for name, _, best in rows:
        per = best.get("per_class")
        if not per:
            print(f"{name:<18}{'(기록 없음 — 1차는 표정별을 안 남겼다)':>20}")
            continue
        print(f"{name:<18}" + "".join(f"{per[n]*100:>6.0f}%" for n in LABELS))


if __name__ == "__main__":
    main()
