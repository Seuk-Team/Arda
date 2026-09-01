# backend/Dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# 의존성을 먼저 복사해 레이어 캐시를 살린다 — 코드만 바뀌면 재설치하지 않는다
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# scripts 는 app 보다 덜 바뀌므로 먼저 복사해 캐시를 더 오래 살린다.
# create_admin.py 가 여기 있다 — production 은 공개 가입이 잠겨 있어 최초 admin 을
# 이 스크립트로만 만들 수 있다. 빠지면 부트스트랩이 불가능하다 (07-deploy).
COPY scripts ./scripts
COPY app ./app

# 임베딩 모델을 이미지에 굽는다. 안 하면 **첫 검색 요청 때 HuggingFace 에서
# 내려받는다** — 에어갭에서는 죽고, 프라이빗 서브넷이면 NAT 가 필요하며,
# 그 요청만 수십 초 걸린다. 런타임에 인터넷을 안 타게 하는 것이 목적이다.
ENV HF_HOME=/app/.hf
RUN /app/.venv/bin/python scripts/prefetch_models.py

# 굽고 난 뒤에는 잠근다. 모델이 빠졌으면 조용히 받지 말고 바로 실패해야 눈에 띈다.
# (STT 로컬 모델은 여기서 안 받는다 — GPU 장비 전용이고 optional extra 다)
ENV HF_HUB_OFFLINE=1

EXPOSE 8000

# **`uv run` 이 아니라 이미지 안 venv 를 직접 부른다.**
#
# `uv run` 은 기동할 때마다 잠금 파일과 환경을 맞춘다. 이미지에 이미 venv 가
# 있으면 대개 그냥 쓰지만, 어긋난다고 판단하면 **컨테이너 쓰기 레이어에 통째로
# 다시 설치한다.** 운영에서 실제로 그렇게 됐다 — 이미지는 382MB 인데 컨테이너
# 하나가 4.9GB 였고(그것도 CPU 가 아니라 CUDA torch 였다), api·worker 둘이
# 10.8GB 를 먹어 19GB 디스크에 새 이미지가 들어갈 자리가 없었다.
# venv 를 직접 부르면 기동이 곧 실행이라 그 일이 일어나지 않는다.
# (07-deploy 의 "Started 이후 실제 서비스까지 약 2분"도 이 재설치 시간이었다.)
#
# --reload 는 로컬 개발용이다. 루트 docker-compose.yml 이 command 를 덮지 않아
# 이 CMD 를 그대로 쓴다. 운영은 docker-compose.prod.yml 이 --reload 없이 덮는다.
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
