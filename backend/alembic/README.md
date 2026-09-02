# 마이그레이션 (alembic)

## 왜 들어왔나

`create_all` 은 **없는 테이블을 만들 뿐** 기존 테이블의 컬럼을 붙이거나 타입을 넓히지 않는다. 2026-09-01 하루에 그 대가를 두 번 치렀다.

- 로컬 DB 의 `users.role` 체크 제약이 옛 값이라 **테스트 101건이 error**
- 운영 `applications.ai_summary_model` 이 `varchar(50)` 이라 **AI 요약이 전건 실패** — Claude 호출 3번을 끝낸 뒤 저장에서 죽어 돈은 쓰고 결과는 버렸고, `BackgroundTasks` 라 화면에 에러도 안 떴다

두 번 다 "각자 손으로 SQL 을 돌려라"로 수습했다. 이 폴더는 그것을 코드로 옮긴 것이다.

## 쓰는 법

**alembic 은 런타임 의존성이 아니다** — 서버가 뜰 때 돌지 않는다. 그래서 `[dependency-groups] dev` 에 있고, 운영 이미지는 `uv sync --frozen --no-dev` 라 **들어가지 않는다**(`uv export --no-dev` 로 실측 확인).

> **왜 처음엔 뺐다가 이제 넣었나** (2026-09-02)
>
> 도입(`5941ae7`) 당시에는 `pyproject`·`uv.lock` 을 아예 건드리지 않고 `uv run --with alembic` 으로 그때그때 받아 썼다. **Dockerfile 이 uv `0.5.11` 로 핀돼 있는데 `uv.lock` 은 그보다 새 uv 가 쓴 형식이어서, 잠금 파일을 다시 쓰면 이미지 빌드가 깨질까 봐** 피한 것이다. 근거 있는 판단이었다.
>
> 뒤집은 이유는 둘이다. **첫째, 버전이 아무 데도 안 박힌다.** `--with` 는 매번 최신을 받아오므로 사람마다·CI 마다 **다른 alembic 으로 같은 리비전을 돌리게 된다.** 지금은 잘 돌아도 alembic 이 바뀌면 어느 날 한 명만 실패한다. 둘째, **걱정했던 위험이 실제로는 성립하지 않았다** — 이번에 다시 쓴 `uv.lock` 은 형식(`version = 1` · `revision = 3`)이 그대로이고 기존 패키지 버전도 하나도 안 움직였다(`alembic` `mako` 두 줄만 추가). 그리고 그 `revision = 3` 은 이 변경 **이전부터** 있던 값이고, 09/01 저녁 운영 재배포가 그 잠금 파일로 성공했다.
>
> 즉 원래 판단이 틀렸던 게 아니라 **전제가 이미 바뀌어 있었다.** 다만 Dockerfile 의 uv 핀과 잠금 파일 형식이 어긋나 있는 것 자체는 그대로다 — 별건으로 정리할 것.

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/arda"

uv run alembic upgrade head        # 최신으로
uv run alembic check               # 모델과 어긋난 곳이 있는지
uv run alembic current             # 지금 리비전
```

### 이미 쓰던 DB 가 있다면

`0001` 은 **2026-09-01 시점 스키마 전체**다. 그 이전 이력이 없으므로, 그 사이에 만들어진 DB 를 자동으로 따라잡히게 할 방법은 없다. 상황별로 다르다.

| 내 DB | 할 일 |
|---|---|
| 새로 만든다 | `alembic upgrade head` — 끝 |
| **로컬 개발 DB** (버려도 되는 것) | **지우고 다시 만든 뒤** `upgrade head`. 이게 가장 확실하다 |
| **이미 09/01 스키마와 같다** (운영처럼 손으로 이행을 마친 경우) | `alembic stamp head` — 실행하지 않고 "여기까지 왔다"고만 표시 |

> ### ⚠️ `stamp` 전에는 반드시 실제 스키마를 조회한다
>
> **`stamp` 는 아무것도 고치지 않는다. "이미 됐다"고 장부에만 적는 것이다.** 어긋난 DB 에 찍으면 alembic 이 **다시는 그것을 고치지 않는다** — 문제가 영구히 숨는다.
>
> 실제로 09/01 에 그럴 뻔했다. 인계 문서는 "운영은 이행을 마쳤으니 `stamp head` 만"이라고 안내했는데, **실측해 보니 `ai_summary_model` 이 아직 50 이었다.** 그대로 찍었으면 AI 요약은 계속 저장에서 죽고 원인은 안 보였을 것이다. (팀장이 조회로 잡아냈다.)
>
> ```sql
> -- 0002 가 고치는 두 가지를 눈으로 확인한다
> select character_maximum_length from information_schema.columns
>  where table_name='applications' and column_name='ai_summary_model';   -- 200 이어야 stamp
> select count(*) from users where role in ('recruiter','interviewer');  -- 0 이어야 stamp
> ```
>
> **둘 중 하나라도 어긋나면 `stamp head` 가 아니라 `stamp 0001` → `upgrade head` 다.** 그러면 `0002` 가 실제로 고친다. 판단이 서지 않으면 이쪽을 고른다 — `0002` 는 이미 맞는 DB 에서 아무 일도 하지 않는다.

`0002` 는 알려진 두 가지 어긋남만 잡는 **안전망**이지, 임의의 옛 DB 를 현재로 끌어올리지는 못한다. 실제로 09/01 오전에 만든 로컬 DB 조차 그날 오후 컬럼 추가를 따라가지 못해 테스트 169건이 error 였다 — 그때는 다시 만드는 것이 답이었다.

**여기서부터는 다르다.** 앞으로의 변경은 전부 리비전으로 쌓이므로 `upgrade head` 하나로 따라온다.

## 스키마를 바꿀 때

1. `app/models.py` 를 고친다
2. 리비전을 만든다 — `uv run alembic revision --autogenerate -m "무엇을"`
3. **생성된 파일을 읽는다.** autogenerate 는 완벽하지 않다 — 실제로 `use_alter` 순환 FK 를 빠뜨렸고 `alembic check` 로 잡았다
4. `alembic upgrade head` 로 적용하고 `alembic check` 로 어긋남이 없는지 확인
5. 코드와 **같은 커밋**에 넣고 `01-erd.md` 도 함께 갱신한다 (CLAUDE.md 규칙)

## 리비전

| ID | 무엇 |
|---|---|
| `0001` | 2026-09-01 시점 스키마 전체. 이 시점 이전 이력은 없다 — 그때까지는 `create_all` 로 살았다 |
| `0002` | 오래된 DB 따라잡기: 역할 2종화(ADR-0017) · `ai_summary_model` 50 → 200 |

## create_all 은 어떻게 되나

**아직 남아 있다** (`main.py` lifespan · `tests/conftest.py` · `scripts/create_admin.py`). 새 DB 를 세우는 데는 그대로 쓰고, **바뀐 것을 따라가는 일만** alembic 이 맡는다.

기동 시 자동 마이그레이션은 걸지 않았다 — 배포 중 스키마가 조용히 바뀌는 것보다, 사람이 보고 돌리는 편이 지금 규모에 맞다.

## pgvector 없는 환경

`application_embeddings` 는 `vector` 타입을 쓴다. 확장이 없는 DB 에서는 **그 테이블만 건너뛴다** — 만들려다 실패하면 alembic 이 한 트랜잭션이라 나머지 테이블까지 통째로 롤백된다. 시맨틱 검색만 꺼지고 나머지는 정상이다.
