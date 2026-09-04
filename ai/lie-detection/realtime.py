"""
실시간 거짓말 탐지.
카메라 + 마이크로 5초씩 수집 → 특징 추출 → 모델 예측 → 화면 표시.

실행:
    .venv\Scripts\python.exe realtime.py
"""

import cv2
import numpy as np
import pickle
import threading
import time
import sounddevice as sd
from collections import deque
from feature_extractor import extract_audio_from_array, extract_visual_from_frames
import warnings
warnings.filterwarnings("ignore")

SR = 22050
WINDOW_SEC = 5           # 분석 윈도우 (초)
ANALYZE_EVERY = 3        # 몇 초마다 새로 분석할지

model = pickle.load(open("model.pkl", "rb"))

# 공유 버퍼
frame_buf = deque(maxlen=300)   # 최대 300프레임
audio_buf = deque(maxlen=SR * WINDOW_SEC)

result_label = "대기 중..."
result_conf  = 0.0
result_color = (200, 200, 200)
analyzing    = False


def audio_callback(indata, frames, time_info, status):
    audio_buf.extend(indata[:, 0])


def analyze_loop():
    global result_label, result_conf, result_color, analyzing
    while True:
        time.sleep(ANALYZE_EVERY)
        if len(frame_buf) < 10 or len(audio_buf) < SR * 2:
            continue

        analyzing = True
        frames_snap = list(frame_buf)
        audio_snap  = np.array(list(audio_buf), dtype=np.float32)

        audio_feat  = extract_audio_from_array(audio_snap, sr=SR)
        visual_feat = extract_visual_from_frames(frames_snap)

        if audio_feat is None:
            audio_feat  = np.zeros(86)
        if visual_feat is None:
            visual_feat = np.zeros(14)

        feat = np.concatenate([audio_feat, visual_feat]).reshape(1, -1)

        pred = model.predict(feat)[0]
        if hasattr(model, "predict_proba"):
            conf = model.predict_proba(feat)[0].max()
        else:
            conf = 1.0

        result_label = "거 짓 말" if pred == 1 else "진   실"
        result_conf  = conf
        result_color = (0, 60, 220) if pred == 1 else (0, 180, 60)
        analyzing    = False


def draw_overlay(frame, label, conf, is_analyzing):
    h, w = frame.shape[:2]

    # 반투명 하단 바
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 110), (w, h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

    color = (100, 100, 100) if is_analyzing else result_color

    status = "분석 중..." if is_analyzing else label
    cv2.putText(frame, status, (20, h - 65),
                cv2.FONT_HERSHEY_DUPLEX, 1.4, color, 2, cv2.LINE_AA)

    if not is_analyzing:
        bar_w = int((w - 40) * conf)
        cv2.rectangle(frame, (20, h - 40), (20 + bar_w, h - 20), color, -1)
        cv2.rectangle(frame, (20, h - 40), (w - 20, h - 20), (150, 150, 150), 1)
        cv2.putText(frame, f"{conf*100:.0f}%", (w - 70, h - 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)

    # 녹화 인디케이터
    cv2.circle(frame, (w - 20, 20), 8, (0, 0, 220), -1)
    return frame


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[!] 카메라를 열 수 없습니다.")
        return

    stream = sd.InputStream(samplerate=SR, channels=1, callback=audio_callback)
    stream.start()

    t = threading.Thread(target=analyze_loop, daemon=True)
    t.start()

    print("[*] 실시간 탐지 시작. 'q' 키로 종료.")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_buf.append(frame.copy())
        draw_overlay(frame, result_label, result_conf, analyzing)
        cv2.imshow("Lie Detector", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    stream.stop()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
