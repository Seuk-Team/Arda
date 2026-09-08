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


def _detect(frame):
    """BGR 프레임 → (픽셀 좌표 랜드마크, RGB 프레임). 얼굴이 없으면 (None, rgb).

    검출은 한 번만 한다 — 특징 7개와 ViT 용 얼굴 사진이 **같은 검출 결과**에서
    나와야 두 신호가 같은 얼굴을 가리킨다.
    """
    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    result = _face_landmarker.detect(
        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    )
    if not result.face_landmarks:
        return None, rgb
    return _lm_to_xy(result.face_landmarks[0], w, h), rgb


def _row_of(lm):
    return [
        _ear(lm, _LEFT_EYE),
        _ear(lm, _RIGHT_EYE),
        _mar(lm),
        _brow_height(lm, _LEFT_BROW,  _LEFT_EYE),
        _brow_height(lm, _RIGHT_BROW, _RIGHT_EYE),
        abs(_ear(lm, _LEFT_EYE) - _ear(lm, _RIGHT_EYE)),
        _head_pose_proxy(lm),
    ]


def face_row(frame):
    """BGR 프레임 한 장 → 얼굴 특징 7개. 얼굴이 없으면 None.

    영상 파일과 실시간 스트림이 **같은 값을 보게** 하려고 한 곳에 둔다.
    두 경로가 따로 계산하면 같은 사람이 매체에 따라 다른 신호를 내게 된다.
    """
    lm, _ = _detect(frame)
    return None if lm is None else _row_of(lm)


# ── 표정 (ViT · ADR-0032) ─────────────────────────────────────
# **비어 있으면 꺼진 채로 돈다.** torch 가 없는 이미지에서도 그대로 뜨고, 판정은
# 지금과 같은 100차원으로 간다. 켜면 표정 7종 평균·표준편차 14개가 더 붙는다.
#   켤 때: pip install -r requirements-vit.txt && export VIT_MODEL=trpakov/vit-face-expression
VIT_MODEL = os.environ.get("VIT_MODEL", "").strip()
VIT_BATCH = int(os.environ.get("VIT_BATCH", "16"))

_vit = None


def _vit_pair():
    """(전처리기, 모델). 처음 부를 때 한 번만 올린다(~0.9GB, torch 포함)."""
    global _vit
    if _vit is None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForImageClassification

        proc = AutoImageProcessor.from_pretrained(VIT_MODEL)
        model = AutoModelForImageClassification.from_pretrained(VIT_MODEL).eval()
        _vit = (proc, model, torch)
    return _vit


def _crop_of(lm, rgb):
    """랜드마크가 덮는 사각형만 잘라 낸다. 너무 작으면 None.

    ViT 표정 모델은 얼굴 사진으로 학습돼 있어 배경이 들어가면 값이 흐려진다.
    자를 좌표는 이미 뽑아 둔 랜드마크에서 나온다 — 검출기를 하나 더 두지 않는다.
    """
    h, w = rgb.shape[:2]
    xs = [p[0] for p in lm]
    ys = [p[1] for p in lm]
    x0, x1 = int(max(0, min(xs))), int(min(w, max(xs)))
    y0, y1 = int(max(0, min(ys))), int(min(h, max(ys)))
    if x1 - x0 < 60 or y1 - y0 < 60:
        return None
    return rgb[y0:y1, x0:x1]


def expression_rows(crops):
    """얼굴 사진들 → 표정 7종 확률. 꺼져 있거나 사진이 없으면 None.

    **이 값은 진위 판정이 아니다.** 법정 영상 실측에서 거짓 영상이 happy 55~64%,
    진실 영상이 fear 71% 로 나왔다 — 표정만으로는 갈리지 않는다(ADR-0032 결정 6).
    특징 벡터의 한 부분으로만 쓴다.
    """
    if not VIT_MODEL or not crops:
        return None
    from PIL import Image

    proc, model, torch = _vit_pair()
    out = []
    for i in range(0, len(crops), VIT_BATCH):
        batch = [Image.fromarray(c) for c in crops[i : i + VIT_BATCH]]
        with torch.no_grad():
            logits = model(**proc(images=batch, return_tensors="pt")).logits
        out.append(torch.softmax(logits, -1).numpy())
    return np.concatenate(out)


def extract_visual(video_path, max_frames=300, with_crops=False):
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    rows = []
    timestamps = []
    crops = []
    frame_idx = 0

    while cap.isOpened() and frame_idx < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        if frame_idx % 3 != 0:
            continue

        lm, rgb = _detect(frame)
        if lm is None:
            continue
        rows.append(_row_of(lm))
        timestamps.append(frame_idx / fps)
        if with_crops:
            crop = _crop_of(lm, rgb)
            if crop is not None:
                crops.append(crop)

    cap.release()
    if len(rows) < 5:
        return None

    arr = np.array(rows)
    summary = np.concatenate([arr.mean(axis=0), arr.std(axis=0)])
    if with_crops:
        return summary, arr, np.array(timestamps), crops
    return summary, arr, np.array(timestamps)


# 얼굴 신호를 "많다·적다"로 부르는 기준. 파일 분석과 실시간이 **같은 값**을 봐야
# 같은 사람이 매체에 따라 다른 말을 듣지 않는다.
EAR_BLINK  = 0.22   # 이 값 이하면 눈 감은 것
BLINK_FAST = 0.5    # 회/초 — 이보다 잦으면 빠름
BLINK_SLOW = 0.1    # 회/초 — 이보다 드물면 거의 안 깜빡임
POSE_MOVE  = 0.05   # 고개 흔들림(표준편차)
MAR_TIGHT  = 0.03   # 입술 다뭄
MAR_OPEN   = 0.15   # 입 벌림
ASYMM_HIGH = 0.04   # 좌우 눈 비대칭


def face_signals(arr, seconds):
    """얼굴 행 묶음 → 사람이 읽는 관찰 목록.

    `analyze_timeseries` 가 구간마다 하는 일을 임의의 한 구간에 대해 한다.
    실시간 창(4초)에도 그대로 쓰려고 떼어 놨다.

    `arr` 열 순서: ear_l, ear_r, mar, brow_l, brow_r, asymm, pose
    """
    if len(arr) < 3 or seconds <= 0:
        return []

    ear_avg = (arr[:, 0] + arr[:, 1]) / 2
    blinks  = int(np.sum(np.diff((ear_avg < EAR_BLINK).astype(int)) == 1))
    rate    = blinks / seconds

    out = []
    if rate > BLINK_FAST:
        out.append({"key": "눈 깜빡임", "value": f"{rate:.1f}회/초 (빠름)", "flag": "high"})
    elif rate < BLINK_SLOW:
        out.append({"key": "눈 깜빡임", "value": f"{rate:.1f}회/초 (거의 안 깜빡임)", "flag": "low"})
    else:
        out.append({"key": "눈 깜빡임", "value": f"{rate:.1f}회/초 (정상)", "flag": "normal"})

    if float(arr[:, 6].std()) > POSE_MOVE:
        out.append({"key": "고개 움직임", "value": "많음", "flag": "high"})

    mar_avg = float(arr[:, 2].mean())
    if mar_avg < MAR_TIGHT:
        out.append({"key": "입", "value": "입술 강하게 다뭄", "flag": "high"})
    elif mar_avg > MAR_OPEN:
        out.append({"key": "입", "value": "입 크게 벌림", "flag": "high"})

    asymm = float(arr[:, 5].mean())
    if asymm > ASYMM_HIGH:
        out.append({"key": "얼굴 비대칭", "value": f"{asymm:.3f} (높음)", "flag": "high"})

    return out


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

        t_label = f"{int(t)}~{int(t+WINDOW_SEC)}초"
        for sig in face_signals(arr[mask], WINDOW_SEC):
            observations.append({"time": t_label, **sig})

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
    """영상 하나 → 특징 벡터.

    `VIT_MODEL` 이 꺼져 있으면 **100차원**(음성 86 + 얼굴 14) 그대로다.
    켜면 표정 7종의 평균·표준편차 14개가 뒤에 붙어 **114차원**이 된다.
    두 길이는 서로 다른 모델을 쓴다(`model.pkl` · `model_vit.pkl`).
    """
    audio      = extract_audio(video_path)
    vis_result = extract_visual(video_path, with_crops=bool(VIT_MODEL))

    if audio is None and vis_result is None:
        return None
    if audio is None:
        audio = np.zeros(86)

    visual = vis_result[0] if vis_result is not None else np.zeros(14)
    feat = np.concatenate([audio, visual])

    if not VIT_MODEL:
        return feat

    probs = expression_rows(vis_result[3]) if vis_result is not None else None
    if probs is None:
        # 얼굴 사진이 없으면 표정 자리를 0 으로 채운다. 100차원 경로와 달리 여기서는
        # 길이를 맞춰야 모델이 받는다 — "표정을 못 봤다"가 0 으로 표현되는 셈이고,
        # 학습 때도 같은 방식이라 모델이 그 뜻을 배운다.
        probs = np.zeros((1, 7))
    return np.concatenate([feat, probs.mean(axis=0), probs.std(axis=0)])
