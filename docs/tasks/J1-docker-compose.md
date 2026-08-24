# [J1] Docker Compose — 로컬 실행 환경

> 담당: 팀원4 · 역할 E(인프라·인증) · 브랜치: `feat/j1-docker-compose`
> **PR 단위**: 이 지시서 전체 = PR 1개

## 배경

지금은 각자 로컬에 Postgres를 깔아야 백엔드를 돌릴 수 있다. 사람마다 버전·포트·비밀번호가 달라지면 **"제 컴퓨터에선 되는데요"가 시작된다.**

`docker compose up` 한 줄로 DB와 API가 함께 뜨게 만든다. 2주차 이후 모든 백엔드 작업이 이 위에서 돌아가고, 4주차 AWS 배포(J2)도 여기서 만든 이미지를 그대로 쓴다.

## 선행 조건 — 없으면 중단

- [ ] `backend/app/main.py`가 있고 `uvicorn app.main:app`으로 뜬다 — [J0 앱 뼈대](J0-앱-뼈대.md) **PR이 머지돼 있다.** 아직이면 기다린다
- [ ] `backend/pyproject.toml`에 `fastapi`·`uvicorn`이 들어 있다
- [ ] 로컬에 Docker Desktop이 설치돼 있고 `docker compose version`이 동작한다

ERD 확정과는 **무관하다.** 스키마가 바뀌어도 이 작업은 영향받지 않는다.

## 가장 중요한 규칙 — 없는 것을 만들지 않는다

- **애플리케이션 코드를 건드리지 않는다.** `backend/app/` 아래는 이번 작업 대상이 아니다. 앱이 안 뜨면 고치지 말고 팀 채널에 알린다.
- **워커 서비스는 실제로 만들지 않는다.** SQS 워커(G2)는 3주차 작업이고 코드가 없다. **주석으로 자리만** 남긴다.
- **마이그레이션 도구(Alembic)를 넣지 않는다.** [backend/app/db.py](../../backend/app/db.py)에 적혀 있듯 스키마가 굳기 전까지는 `create_all`로 만들고 바뀌면 DB를 지운다.
- **비밀번호를 파일에 하드코딩해도 되는 것은 로컬 개발용 `postgres/postgres`뿐이다.** 그 외 어떤 실제 시크릿도 넣지 않는다.

## 완료 조건

- [ ] `docker-compose.yml` — **저장소 루트**에 둔다 (빌드 컨텍스트가 `./backend`라 루트가 편하다)
- [ ] `backend/Dockerfile`
- [ ] `backend/.dockerignore`
- [ ] 서비스 2개: `db`(Postgres 16) · `api`(FastAPI). **워커는 주석 자리만**
- [ ] `db`에 **헬스체크**가 있고, `api`는 `depends_on: condition: service_healthy`로 DB가 준비된 뒤 뜬다
- [ ] `db` 데이터는 **named volume**에 남는다 — `docker compose restart` 후에도 데이터가 살아 있다
- [ ] `api`의 `DATABASE_URL`이 `localhost`가 아니라 **`db` 서비스 이름**을 가리킨다
- [ ] `backend/app/`을 볼륨으로 마운트하고 `--reload`를 켠다 — 코드를 고치면 컨테이너를 다시 안 띄워도 반영된다
- [ ] `docker compose up` 한 번으로 `http://localhost:8000/docs`가 열린다
- [ ] `README.md`나 문서를 고치지 않는다 (문서 갱신은 별도 확인 절차)

## 완성 예시

**아래가 정답 형태다. 값을 바꾸지 말고 그대로 쓴다.**

```yaml
# docker-compose.yml (저장소 루트)
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres   # 로컬 전용. 실제 시크릿을 넣지 않는다
      POSTGRES_DB: arda
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d arda"]
      interval: 3s
      timeout: 3s
      retries: 20

  api:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:postgres@db:5432/arda
    ports:
      - "8000:8000"
    volumes:
      - ./backend/app:/app/app        # 코드 고치면 바로 반영
    depends_on:
      db:
        condition: service_healthy

  # worker:  # G2 SQS 메일 워커 — 3주차. 코드가 생기면 그때 연다
  #   build: ./backend
  #   command: uv run python -m app.worker
  #   depends_on:
  #     db:
  #       condition: service_healthy

volumes:
  pgdata:
```

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

# 의존성을 먼저 복사해 레이어 캐시를 살린다 — 코드만 바뀌면 재설치하지 않는다
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

```
# backend/.dockerignore
.venv/
__pycache__/
*.pyc
.env
.pytest_cache/
```

## 참고 문서

- [infra/README.md](../../infra/README.md) — 인프라 구성 (Docker · AWS · CI/CD)
- [backend/app/db.py](../../backend/app/db.py) — `DATABASE_URL` 환경변수 이름과 기본값
- [backend/.env.example](../../backend/.env.example) — 로컬 실행 시 쓰는 키 이름

## Claude에게 시키기

```
0단계.
backend/pyproject.toml, backend/app/db.py, backend/.env.example, infra/README.md 를 읽어라.
읽은 뒤, 컨테이너에서 DB 에 붙으려면 DATABASE_URL 이 어떤 값이어야 하는지와
그 이유를 3줄로 설명해라. 아직 파일을 만들지 마라.

1단계.
backend/Dockerfile 과 backend/.dockerignore 를 만들어라.
python:3.12-slim 기반, uv 로 의존성 설치.
pyproject.toml 과 uv.lock 을 먼저 복사해 레이어 캐시를 살리고, 그 다음에 app 을 복사한다.
backend/app/ 아래 코드를 수정하지 마라.

2단계.
저장소 루트에 docker-compose.yml 을 만들어라.
db(postgres:16-alpine, 헬스체크 pg_isready, named volume) 와
api(build ./backend, DATABASE_URL 은 db 서비스 이름을 가리킴, ./backend/app 마운트) 두 개.
api 는 depends_on 으로 db 가 healthy 가 된 뒤에 뜬다.
워커는 만들지 말고 주석으로 자리만 남겨라.

3단계.
docker compose up -d 로 띄우고, 아래 검증 명령을 순서대로 실행해 결과를 보여줘라.
실패하면 고치기 전에 원인을 먼저 설명해라.
```

```
마지막 단계 — 여기서 멈추지 마라.

위 작업을 끝내고 PR 을 올렸으면, 이어서 다음 할 일을 스스로 찾아 그대로 수행해라.

1. docs/weekly/ 의 이번 주 문서를 전부 읽어라.
   W1.md 가 본 계획이고 W1-2 · W1-3 … 번호가 큰 것이 나중에 정해진 것이다. 뒤엣것이 우선한다.
2. 거기서 내 다음 작업을 찾아라. 없으면 docs/tasks/J7-더미데이터-생성기.md 의 파트 A 에서
   backend/scripts/seed/ 에 아직 없는 배치를 가져가라.
3. 찾은 작업의 지시서를 docs/tasks/ 에서 열고, 선행 조건을 먼저 확인해라.
   선행 조건이 안 채워졌으면 거기서 멈추고 무엇이 막혔는지 알려줘라.
4. 선행 조건이 채워졌으면 새 브랜치를 만들고 그 지시서의 "Claude에게 시키기" 를
   0단계부터 순서대로 수행해라. 지시서 하나 = PR 하나다.
5. 그 작업도 끝나면 1번으로 돌아가 반복해라.

지키는 것:
- 지시서가 있는 작업만 한다. docs/tasks/ 에 지시서가 없으면 "지시서 없음" 이라고 말하고 멈춘다.
- 지시서에 적힌 산출 파일 밖을 고치지 않는다. 다른 사람 파일과 공용 파일은 건드리지 않는다.
  (공용: frontend/mockups/mockup.html · docs/01-erd.md · docs/02-api.md · backend/app/models.py)
- 작업 사이마다 git status 를 확인해서 지시서에 없는 파일이 있으면 되돌린다.
```

**주의**: Claude가 `backend/app/` 수정, Alembic 추가, `pyproject.toml` 의존성 변경, 실제 AWS 자격증명 입력을 제안하면 **수락하지 말고** 팀 채널에 물어본다.

## 검증 방법

```bash
docker compose up -d --build
docker compose ps
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/docs
docker compose exec db pg_isready -U postgres -d arda
docker compose restart api && sleep 5 && curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/docs
docker compose down && docker compose up -d && docker compose exec db psql -U postgres -d arda -c '\dt'
```

기대 결과:

- `docker compose ps`에 `db`가 **healthy**, `api`가 **running**
- `/docs` → **200**
- `pg_isready` → `accepting connections`
- `restart` 후에도 **200** (의존 순서가 제대로 잡혀 있다는 뜻)
- `down` → `up` 후 `\dt`에 이전 테이블이 그대로 있다 (**named volume이 붙어 있다는 뜻**)
- `docker compose logs api`에 트레이스백이 없다

정리:

```bash
docker compose down          # 컨테이너만 내림 (데이터 유지)
docker compose down -v       # 데이터까지 지움 — 스키마 바뀌었을 때만
```

## 막히면 · 되돌리기

- **30분 넘게 막히면 혼자 붙들지 말고 팀 채널에 묻는다.** 특히 **포트 5432가 이미 쓰이는 경우**가 흔하다 — 로컬에 Postgres가 이미 떠 있으면 그것을 끄거나 팀 채널에 알린다. compose 쪽 포트를 임의로 바꾸지 마라(다른 사람과 값이 달라진다).
- **결과가 이상해지면 고치려 들지 말고 버린다.**

```bash
docker compose down -v
git checkout -- .
```

그래도 이상하면 브랜치째 버리고 처음부터 다시 시작한다.

```bash
git checkout main && git branch -D feat/j1-docker-compose
```

- **`git status`에 `backend/app/`이나 `docs/`가 떠 있으면 범위를 벗어난 것이다.** 되돌리고 팀 채널에 알린다.

## PR 체크리스트

- [ ] PR 본문에 위 검증 결과를 붙였다 (`docker compose ps` 출력 + `/docs` 응답 코드)
- [ ] `backend/app/` · `docs/` · 다른 사람 파일을 **수정하지 않았다**
- [ ] 실제 시크릿이 파일에 없다 (로컬 전용 `postgres/postgres`만)
- [ ] 스키마·API 변경 없음
