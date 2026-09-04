"""
Michigan Real-Life Trial 데이터셋을 처리해 X.npy / y.npy 생성.

사용법:
    python build_dataset.py --clips_dir <Clips 폴더 경로>

Clips 폴더 구조:
    Clips/
      Deceptive/  → trial_lie_*.mp4  (레이블 1)
      Truthful/   → trial_truth_*.mp4 (레이블 0)
"""

import os
import glob
import argparse
import numpy as np
from tqdm import tqdm
from feature_extractor import extract_features


def build(clips_dir, out_dir):
    deceptive_dir = os.path.join(clips_dir, "Deceptive")
    truthful_dir  = os.path.join(clips_dir, "Truthful")

    pairs = []  # (path, label)
    for ext in ("*.mp4", "*.avi", "*.mov"):
        for p in glob.glob(os.path.join(deceptive_dir, ext)):
            pairs.append((p, 1))
        for p in glob.glob(os.path.join(truthful_dir, ext)):
            pairs.append((p, 0))

    if not pairs:
        print(f"[!] 비디오 파일을 찾지 못했습니다: {clips_dir}")
        return

    print(f"[*] 총 {len(pairs)}개 비디오 처리 시작 (거짓: {sum(l for _,l in pairs)}, 진실: {sum(1-l for _,l in pairs)})")

    X, y, skipped = [], [], 0
    for path, label in tqdm(pairs):
        features = extract_features(path)
        if features is None:
            print(f"  [skip] {os.path.basename(path)}")
            skipped += 1
            continue
        X.append(features)
        y.append(label)

    if not X:
        print("[!] 저장할 데이터가 없습니다.")
        return

    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "X.npy"), np.array(X))
    np.save(os.path.join(out_dir, "y.npy"), np.array(y))
    print(f"\n[완료] X: {np.array(X).shape} / 건너뜀: {skipped}개")
    print(f"  저장: {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips_dir", required=True, help="Clips 폴더 경로")
    parser.add_argument("--out_dir", default="processed", help="결과 저장 폴더")
    args = parser.parse_args()
    build(args.clips_dir, args.out_dir)
