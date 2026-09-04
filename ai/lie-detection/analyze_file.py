"""
비디오 파일을 분석해 거짓말 여부를 판정.

실행:
    .venv\Scripts\python.exe analyze_file.py <비디오파일 경로>
    .venv\Scripts\python.exe analyze_file.py  (인자 없으면 파일 선택 다이얼로그)
"""

import sys
import pickle
import numpy as np
import warnings
warnings.filterwarnings("ignore")

from feature_extractor import extract_features


def analyze(video_path):
    print(f"\n[*] 분석 중: {video_path}")
    print("    (30초~1분 소요될 수 있습니다...)")

    feat = extract_features(video_path)
    if feat is None:
        print("[!] 특징 추출 실패 — 얼굴/음성이 충분히 감지되지 않았습니다.")
        return

    model = pickle.load(open("model.pkl", "rb"))
    feat2d = feat.reshape(1, -1)

    pred = model.predict(feat2d)[0]
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(feat2d)[0]
        conf_lie   = proba[1]
        conf_truth = proba[0]
    else:
        conf_lie   = 1.0 if pred == 1 else 0.0
        conf_truth = 1.0 - conf_lie

    print("\n" + "=" * 40)
    if pred == 1:
        print("  판정: ❌ 거짓말 가능성")
    else:
        print("  판정: ✅ 진실 가능성")
    print(f"  진실 확률: {conf_truth*100:.1f}%")
    print(f"  거짓 확률: {conf_lie*100:.1f}%")
    print("=" * 40)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        path = filedialog.askopenfilename(
            title="분석할 비디오 파일 선택",
            filetypes=[("비디오 파일", "*.mp4 *.avi *.mov *.mkv"), ("모든 파일", "*.*")]
        )
        if not path:
            print("파일이 선택되지 않았습니다.")
            sys.exit(0)

    analyze(path)
