# 거짓말 탐지 서비스. 백엔드(backend/Dockerfile)와 따로 두는 이유는 의존성 때문이다 —
# mediapipe·opencv·librosa 를 api 이미지에 넣으면 면접 API 빌드까지 같이 무거워진다.

FROM python:3.13-slim

# slim 이미지에 없는 동적 라이브러리들. 없으면 import 가 아니라 **모델을 만드는 시점에**
# 죽어서 원인이 늦게 드러난다 — mediapipe 가 C 라이브러리를 그때 dlopen 한다.
#   libgl1·libglib2.0-0  : opencv
#   libegl1·libgles2     : mediapipe (libEGL.so.1 — GPU 없이도 찾는다)
#   libsndfile1          : librosa/soundfile
# faster-whisper(ctranslate2)는 추가 패키지가 필요 없다 — 리눅스 휠이 libgomp 를
# 통째로 안고 온다(휠 안의 `libgomp-….so.1.0.0` 확인함).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libegl1 \
        libgles2 \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성을 먼저 넣어 레이어를 나눈다 — 코드만 고쳤을 때 재설치하지 않는다
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ViT 표정 (ADR-0032). torch·transformers 가 이미지에 ~2.5GB 더한다. 스위치는
# `VIT_MODEL` env — 비어 있으면 feature_extractor.py 가 load 를 건너뛰므로,
# 라이브러리만 있어 문제 없음. 실제로 켜지려면 compose 에서 env 를 준다.
# whisper_cache 볼륨(/root/.cache/huggingface)이 ViT 캐시도 같이 받는다.
COPY requirements-vit.txt .
RUN pip install --no-cache-dir -r requirements-vit.txt

COPY . .

EXPOSE 5000

# **GPU 에서 전사하려면 이 이미지로는 안 된다.** `STT_DEVICE=cuda` 를 주면
# ctranslate2 가 `libcublas.so.12` · `libcuda.so.1` 을 dlopen 하는데 python:slim 에는
# 없다. 시연 때 GPU 를 쓰려면 nvidia CUDA 베이스 이미지로 바꾸고 `--gpus all` 로
# 띄워야 한다. **기본값이 `cpu` 인 이유가 이것이다** — 잘못 켜면 모델을 다 올린 뒤
# 첫 전사에서야 죽는다(ADR-0032).
#
# **워커 1개로 고정한다.** 영상 분석 한 건이 최대 약 574MiB 를 쓰는데(실측)
# 서버가 백엔드와 같은 t3.medium(4GB)이고 db·api·worker 가 같은 박스에 있다.
# 전사를 켜면 여기에 모델 ~1GB 가 더 붙는다. 늘리려면 서버 사양을 먼저 바꿔야 한다.
#
# uvicorn 인 이유는 WebSocket(실시간 면접) 때문이다 — gunicorn 의 sync 워커는 WS 를
# 처리하지 못한다.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
