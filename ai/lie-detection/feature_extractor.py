"""
비디오 파일 하나에서 음성 특징 + 얼굴 특징을 추출해 하나의 벡터로 반환.
mediapipe 1.0+ (Tasks API) 기준.

음성: MFCC(40) mean/std, 피치 mean/std, RMS mean/std, ZCR mean/std → 88차원
얼굴: EAR(좌/우), MAR, 눈썹높이, 눈 비대칭, 고개방향 × mean/std → 14차원
최종: 102차원 벡터
"""

import os
import numpy as np
import cv2
import librosa
import warnings
warnings.filterwarnings("ignore")

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "face_landmarker.task")

_base_options = mp_python.BaseOptions(model_asset_path=_MODEL_PATH)
_face_landmarker = mp_vision.FaceLandmarker.create_from_options(
    mp_vision.FaceLandmarkerOptions(
        base_options=_base_options,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        running_mode=mp_vision.RunningMode.IMAGE,
    )
)

_LEFT_EYE  = [33, 160, 158, 133, 153, 144]
_RIGHT_EYE = [362, 385, 387, 263, 373, 380]
_MOUTH     = [61, 291, 13, 14]
_LEFT_BROW = [70, 63, 105, 66, 107]
_RIGHT_BROW= [336, 296, 334, 293, 300]
_NOSE_TIP  = 4


def _lm_to_xy(landmarks, w, h):
    return [(lm.x * w, lm.y * h) for lm in landmarks]


def _ear(lm, indices):
    p = [lm[i] for i in indices]
    vert = (abs(p[1][1]-p[5][1]) + abs(p[2][1]-p[4][1])) / 2
    horiz = abs(p[0][0]-p[3][0])
    return vert / (horiz + 1e-6)


def _mar(lm):
    left, right, top, bot = [lm[i] for i in _MOUTH]
    return abs(top[1]-bot[1]) / (abs(left[0]-right[0]) + 1e-6)


def _brow_height(lm, brow_idx, eye_idx):
    brow_y = np.mean([lm[i][1] for i in brow_idx])
    eye_y  = np.mean([lm[i][1] for i in eye_idx])
    return eye_y - brow_y


def _head_pose_proxy(lm):
    nose_x  = lm[_NOSE_TIP][0]
    left_x  = lm[234][0]
    right_x = lm[454][0]
    center_x = (left_x + right_x) / 2
    face_w   = abs(right_x - left_x) + 1e-6
    return (nose_x - center_x) / face_w


def extract_visual(video_path, max_frames=300):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    rows = []
    timestamps = []
    frame_idx = 0

    while cap.isOpened() and frame_idx < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        if frame_idx % 3 != 0:
            continue

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = _face_landmarker.detect(mp_image)

        if not result.face_landmarks:
            continue

        lm = _lm_to_xy(result.face_landmarks[0], w, h)

        rows.append([
            _ear(lm, _LEFT_EYE),
            _ear(lm, _RIGHT_EYE),
            _mar(lm),
            _brow_height(lm, _LEFT_BROW,  _LEFT_EYE),
            _brow_height(lm, _RIGHT_BROW, _RIGHT_EYE),
            abs(_ear(lm, _LEFT_EYE) - _ear(lm, _RIGHT_EYE)),
            _head_pose_proxy(lm),
        ])
        timestamps.append(frame_idx / fps)

    cap.release()
    if len(rows) < 5:
        return None

    arr = np.array(rows)
    return np.concatenate([arr.mean(axis=0), arr.std(axis=0)]), arr, np.array(timestamps)


def analyze_timeseries(video_path):
    """
    시간대별 눈 깜빡임, 입 움직임, 고개 움직임을 분석해 사람이 읽기 좋은 관찰 목록 반환.
    반환: list of {time, event, value}
    """
    result = extract_visual(video_path)
    if result is None:
        return []

    _, arr, timestamps = result
    # arr columns: ear_l, ear_r, mar, brow_l, brow_r, asymm, pose

    EAR_BLINK  = 0.22   # 이 값 이하면 눈 감은 것
    WINDOW_SEC = 5       # 분석 구간 (초)
    total_sec  = float(timestamps[-1]) if len(timestamps) else 0
    observations = []

    # 구간별 분석
    t = 0
    while t < total_sec:
        mask = (timestamps >= t) & (timestamps < t + WINDOW_SEC)
        if mask.sum() < 3:
            t += WINDOW_SEC
            continue

        seg = arr[mask]
        ear_avg = (seg[:, 0] + seg[:, 1]) / 2

        # 눈 깜빡임 횟수 (EAR이 임계값 아래로 내려가는 횟수)
        blinks = int(np.sum(np.diff((ear_avg < EAR_BLINK).astype(int)) == 1))
        blink_rate = blinks / WINDOW_SEC  # 회/초

        mar_avg   = float(seg[:, 2].mean())
        pose_std  = float(seg[:, 6].std())
        asymm_avg = float(seg[:, 5].mean())

        t_label = f"{int(t)}~{int(t+WINDOW_SEC)}초"

        # 눈 깜빡임
        if blink_rate > 0.5:
            observations.append({"time": t_label, "key": "눈 깜빡임", "value": f"{blink_rate:.1f}회/초 (빠름)", "flag": "high"})
        elif blink_rate < 0.1:
            observations.append({"time": t_label, "key": "눈 깜빡임", "value": f"{blink_rate:.1f}회/초 (거의 안 깜빡임)", "flag": "low"})
        else:
            observations.append({"time": t_label, "key": "눈 깜빡임", "value": f"{blink_rate:.1f}회/초 (정상)", "flag": "normal"})

        # 고개 움직임
        if pose_std > 0.05:
            observations.append({"time": t_label, "key": "고개 움직임", "value": "많음", "flag": "high"})

        # 입 긴장
        if mar_avg < 0.03:
            observations.append({"time": t_label, "key": "입", "value": "입술 강하게 다뭄", "flag": "high"})
        elif mar_avg > 0.15:
            observations.append({"time": t_label, "key": "입", "value": "입 크게 벌림", "flag": "high"})

        # 얼굴 비대칭
        if asymm_avg > 0.04:
            observations.append({"time": t_label, "key": "얼굴 비대칭", "value": f"{asymm_avg:.3f} (높음)", "flag": "high"})

        t += WINDOW_SEC

    return observations


def extract_audio(video_path, sr=22050):
    import tempfile, subprocess, imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        subprocess.run(
            [ffmpeg, "-y", "-i", video_path, "-ac", "1", "-ar", str(sr), tmp.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True,
        )
        y, sr = librosa.load(tmp.name, sr=sr, mono=True, duration=60)
    except Exception:
        return None
    finally:
        os.remove(tmp.name)

    if len(y) < sr:
        return None

    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=40)
    rms  = librosa.feature.rms(y=y)
    zcr  = librosa.feature.zero_crossing_rate(y=y)
    f0, _, _ = librosa.pyin(y, fmin=50, fmax=500, frame_length=2048, hop_length=512)
    f0 = np.nan_to_num(f0)

    return np.concatenate([
        mfcc.mean(axis=1), mfcc.std(axis=1),
        rms.mean(axis=1),  rms.std(axis=1),
        zcr.mean(axis=1),  zcr.std(axis=1),
        [f0.mean(), f0.std()],
    ])  # 88차원


def extract_audio_from_array(y, sr=22050):
    """마이크 녹음 numpy 배열에서 직접 음성 특징 추출."""
    if len(y) < sr:
        return None
    mfcc = librosa.feature.mfcc(y=y.astype(np.float32), sr=sr, n_mfcc=40)
    rms  = librosa.feature.rms(y=y)
    zcr  = librosa.feature.zero_crossing_rate(y=y)
    f0, _, _ = librosa.pyin(y, fmin=50, fmax=500, frame_length=2048, hop_length=512)
    f0 = np.nan_to_num(f0)
    return np.concatenate([
        mfcc.mean(axis=1), mfcc.std(axis=1),
        rms.mean(axis=1),  rms.std(axis=1),
        zcr.mean(axis=1),  zcr.std(axis=1),
        [f0.mean(), f0.std()],
    ])


def extract_visual_from_frames(frames):
    """OpenCV 프레임 리스트(BGR)에서 직접 얼굴 특징 추출."""
    rows = []
    for i, frame in enumerate(frames):
        if i % 3 != 0:
            continue
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = _face_landmarker.detect(mp_image)
        if not result.face_landmarks:
            continue
        lm = _lm_to_xy(result.face_landmarks[0], w, h)
        rows.append([
            _ear(lm, _LEFT_EYE),
            _ear(lm, _RIGHT_EYE),
            _mar(lm),
            _brow_height(lm, _LEFT_BROW,  _LEFT_EYE),
            _brow_height(lm, _RIGHT_BROW, _RIGHT_EYE),
            abs(_ear(lm, _LEFT_EYE) - _ear(lm, _RIGHT_EYE)),
            _head_pose_proxy(lm),
        ])
    if len(rows) < 5:
        return None
    arr = np.array(rows)
    return np.concatenate([arr.mean(axis=0), arr.std(axis=0)])


def extract_features(video_path):
    audio      = extract_audio(video_path)
    vis_result = extract_visual(video_path)

    if audio is None and vis_result is None:
        return None
    if audio is None:
        audio = np.zeros(86)

    visual = vis_result[0] if vis_result is not None else np.zeros(14)
    return np.concatenate([audio, visual])
