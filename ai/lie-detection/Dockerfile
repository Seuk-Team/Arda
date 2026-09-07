# 거짓말 탐지 서비스. 백엔드(backend/Dockerfile)와 따로 두는 이유는 의존성 때문이다 —
# mediapipe·opencv·librosa 를 api 이미지에 넣으면 면접 API 빌드까지 같이 무거워진다.

FROM python:3.13-slim

# slim 이미지에 없는 동적 라이브러리들. 없으면 import 가 아니라 **모델을 만드는 시점에**
# 죽어서 원인이 늦게 드러난다 — mediapipe 가 C 라이브러리를 그때 dlopen 한다.
#   libgl1·libglib2.0-0  : opencv
#   libegl1·libgles2     : mediapipe (libEGL.so.1 — GPU 없이도 찾는다)
#   libsndfile1          : librosa/soundfile
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

COPY . .

EXPOSE 5000

# **워커 1개로 고정한다.** 영상 분석 한 건이 최대 약 574MiB 를 쓰는데(실측)
# 서버가 t3.small(2GB)이고 db·api·worker 가 같은 박스에 있다. 둘이 동시에 돌면 넘친다.
# 늘리려면 서버 사양이나 배치를 먼저 바꿔야 한다.
#
# uvicorn 인 이유는 WebSocket(실시간 면접) 때문이다 — gunicorn 의 sync 워커는 WS 를
# 처리하지 못한다.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
