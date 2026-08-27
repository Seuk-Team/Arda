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

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
