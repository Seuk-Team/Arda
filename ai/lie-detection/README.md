# 거짓말 탐지 서비스

면접 영상에서 음성·표정 특징을 뽑아 진실/거짓을 분류하는 **별도 서비스**다.

Arda 백엔드와 분리해 둔 이유는 의존성 때문이다 — mediapipe·librosa·opencv 는 무겁고,
영상 분석은 CPU 를 오래 쓴다. 면접 API 가 그 영향을 받으면 안 된다.
인터페이스(`POST /analyze` → JSON)만 유지하면 나중에 백엔드 안으로 합쳐도 호출부는 그대로다.

## 실행

```bash
cd ai/lie-detection
uv venv
uv pip install -r requirements.txt
.venv/Scripts/python.exe app.py     # Windows
# .venv/bin/python app.py           # macOS/Linux
```

`http://localhost:5000` 에서 영상을 올려 확인할 수 있다.

`face_landmarker.task`(MediaPipe 얼굴 모델)와 `model.pkl`(학습된 분류기)은 레포에 포함돼 있어
따로 받을 필요가 없다.

## API

### `POST /analyze`

multipart/form-data 로 `video` 필드에 영상 파일을 보낸다.

```json
{
  "pred": 1,
  "truth_pct": 0.4,
  "lie_pct": 99.6,
  "observations": [
    { "time": "0~5초", "key": "눈 깜빡임", "value": "0.8회/초 (빠름)", "flag": "high" }
  ]
}
```

- `pred` — `0` 진실 / `1` 거짓
- `truth_pct`, `lie_pct` — 모델이 낸 확률(%)
- `observations` — 5초 구간별 관찰. **모델 판정과는 별개인 규칙 기반 참고 지표다.**
  `flag` 가 `high` 라고 거짓이라는 뜻이 아니라 평균에서 벗어났다는 표시일 뿐이다.

얼굴이나 음성을 잡지 못하면 `{"error": "..."}` 를 돌려준다.

## 파일

| 파일 | 역할 |
|------|------|
| `app.py` | Flask 서버 — 웹 UI + `/analyze` API |
| `feature_extractor.py` | 영상 → 100차원 특징 벡터. 구간별 관찰도 여기서 만든다 |
| `train.py` | `processed/` 의 X·y 로 모델 학습 → `model.pkl` |
| `build_dataset.py` | 학습용 영상 폴더 → `processed/X.npy`, `y.npy` |
| `analyze_file.py` | CLI 로 영상 하나 분석 |
| `realtime.py` | 웹캠 실시간 판정 (카메라 필요) |

## 모델

Michigan Real-Life Trial 데이터(실제 법정 증언, 거짓 61 · 진실 60)로 학습했다.
5-fold 교차검증 정확도는 다음과 같다.

| 모델 | 정확도 |
|------|--------|
| **MLP** | **76.0%** (채택) |
| SVM (RBF) | 73.6% |
| RandomForest | 73.6% |
| GradBoost | 70.2% |

**121개 표본으로 낸 76% 다.** 참고 지표로 쓸 수는 있어도 이것만으로 사람을 판단하면 안 된다.
합격·불합격 같은 결정에 단독 근거로 쓰지 말 것.

특징 100개는 음성 86개(MFCC 40개의 평균·표준편차, RMS, 영점교차율, 피치)와
얼굴 14개(눈 크기 좌·우, 입 벌림, 눈썹 높이 좌·우, 좌우 비대칭, 고개 방향의 평균·표준편차)로 이뤄진다.

## 재학습

```bash
.venv/Scripts/python.exe build_dataset.py --clips_dir <영상폴더>
.venv/Scripts/python.exe train.py
```

`build_dataset.py` 는 폴더명 `Deceptive`/`Truthful` 로 레이블을 잡는다.
학습 데이터(`processed/`)와 가상환경(`.venv/`)은 커밋하지 않는다.
