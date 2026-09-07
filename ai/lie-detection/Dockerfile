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
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0

COPY . .

EXPOSE 5000

# **워커 1개로 고정한다.** 영상 분석 한 건이 최대 약 560MB 를 쓰는데(로컬 실측)
# 서버가 t3.small(2GB)이고 db·api·worker 가 같은 박스에 있다. 둘이 동시에 돌면 넘친다.
# 늘리려면 서버 사양이나 배치를 먼저 바꿔야 한다.
#
# timeout 이 긴 이유: 영상 길이에 따라 분석이 분 단위까지 간다. gunicorn 기본값 30초면
# 정상 처리 중인 요청을 죽인다.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", \
     "--workers", "1", "--threads", "1", \
     "--timeout", "300", \
     "app:app"]
