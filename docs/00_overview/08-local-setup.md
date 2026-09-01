# 08. 로컬 환경 — 셋업과 이행 체크리스트

> **이 문서는 "내 PC 에서 왜 안 되지"의 답을 모아 둔 곳이다.** 코드가 아니라 **각자의 로컬 환경**이 원인인 것들만 적는다.
> 스키마·환경변수가 바뀌어 **기존 로컬 환경에 손을 대야 하는 일이 생기면 아래 이행 목록에 추가한다.** 코드는 pull 로 따라오지만 DB 와 `.env` 는 안 따라온다.

## 1. 이행 목록 — 이제 alembic 이 한다

**2026-09-01 오후에 alembic 이 도입됐다** (`backend/alembic/README.md`). 그 전까지 이 자리에 손 SQL 을 적었지만, 지금은 **마이그레이션을 돌리는 것으로 끝난다.**

```bash
cd backend
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/arda"   # 자기 포트로
uv run --with alembic alembic upgrade head
```

> **⚠️ 쓰던 DB 에 그냥 `upgrade head` 를 돌리면 실패한다.** `0001` 이 테이블을 **처음부터 만드는** 리비전이라 이미 있는 테이블과 부딪힌다 (재현으로 확인).
>
> ```
> psycopg.errors.DuplicateTable: relation "users" already exists
> ```
>
> 처음 한 번만 아래 중 하나로 넘어가면, 그 뒤로는 `upgrade head` 한 줄로 계속 따라온다.
>
> | 내 DB | 할 일 |
> |---|---|
> | 새로 만든다 | `alembic upgrade head` |
> | **쓰던 로컬 DB** (버려도 되는 것) | `docker compose down -v` 로 지우고 다시 만든 뒤 `upgrade head` — **대부분 여기** |
> | 이미 최신 스키마다 (손으로 이행을 마친 경우) | `alembic stamp 0001` → `upgrade head` |
>
> **`stamp head` 는 함부로 쓰지 않는다.** `stamp` 는 아무것도 고치지 않고 "이미 됐다"고 장부에만 적는다 — 어긋난 DB 에 찍으면 **alembic 이 다시는 고치지 않아 문제가 영구히 숨는다.** 09/01 에 실제로 그럴 뻔했다(인계 안내는 "운영은 stamp 만"이었는데 조회해 보니 `ai_summary_model` 이 아직 50 이었다). `stamp 0001` → `upgrade head` 를 쓰면 `0002` 가 실제로 고치므로 그쪽이 안전하다.

`0002_catch_up_old_databases` 가 오래된 로컬 DB 를 따라잡게 해 준다 — `users.role` 체크 제약과 `applications.ai_summary_model` 폭(50 → 200) 둘 다 여기 들어 있다. **이미 맞는 DB 면 아무것도 안 한다.**

> **왜 이게 필요했나**: `create_all` 은 **없는 테이블을 만들 뿐** 기존 테이블의 컬럼을 붙이거나 타입을 넓히지 않는다. `ai_summary_model` 이 50 인 DB 에서는 AI 요약이 Claude 호출 3번을 다 끝낸 뒤 저장에서 죽었다 — **돈은 쓰고 결과는 버렸고, `BackgroundTasks` 라 화면에 에러도 안 떴다.**

**스키마를 바꿨으면 마이그레이션을 같이 올린다.** 이 문서에 손 SQL 을 적는 시대는 끝났다.

## 2. 평소 셋업

```bash
git pull
cd backend && uv sync
uv run --with alembic alembic upgrade head   # 스키마 최신화 (1절의 '처음 한 번' 을 마친 뒤부터)
docker compose up -d --build      # --build 는 아래 이유로 필요할 때가 있다
```

- **`uv sync` 만으로 충분하다.** 로컬 AI 모델(Ollama·faster-whisper)·GPU·새 API 키는 **설치할 필요 없다** — 3절 참고.
- **`--build` 가 필요한 때**: 의존성이 바뀌었을 때, 그리고 2026-09-01 부터는 이미지가 임베딩 모델(약 440MB)을 빌드 단계에 굽는다. **첫 빌드가 느려지고 인터넷이 필요하다.** 대신 그 뒤로는 첫 검색 요청이 멈추지 않는다 ([07-deploy](07-deploy.md) 로컬 AI 모델 절).

## 3. 백엔드 스위치 — 기본값이 곧 기존 동작이다

에이전트의 AI 호출은 백엔드를 고를 수 있다. **아래를 아무것도 설정하지 않으면 지금까지와 완전히 동일하게 돈다.** 로컬 모델을 쓰고 싶은 사람만 값을 넣는다.

| 환경변수 | 기본 | 로컬로 돌리려면 | main 반영 |
|---|---|---|---|
| `STT_BACKEND` | `openai` | `faster_whisper` (`uv sync --extra local` 필요) | ✅ |
| `AGENT_CHAT_BACKEND` | `anthropic` | `ollama` | ✅ |
| `AGENT_SUMMARY_BACKEND` | `anthropic` | `ollama` | ✅ |

셋 다 main 에 있다(2026-09-01 반영, 480 passed). 로컬로 돌리려면 Ollama 와 모델이 필요하다 — `ollama pull qwen3:4b`. 실측 속도·정확도는 [ADR-0024](../03_decision/0024-sLLM-로컬-모델-전략.md) 09-01 개정 절.

**GPU 없이 로컬 모델을 검증해야 한다면** 각자 Ollama 를 깔 필요가 없다. 어댑터가 `OLLAMA_HOST` 를 보므로 **GPU 장비 한 대에만 띄우고 나머지는 그쪽을 가리키면 된다.** 포트를 열지 말고 SSH 터널을 권한다:

```bash
ssh -L 11434:localhost:11434 <gpu-host>
# 다른 창에서
OLLAMA_HOST=http://localhost:11434 AGENT_CHAT_BACKEND=ollama uv run ...
```

어댑터의 유닛 테스트는 **mock 기반이라 Ollama 없이 돈다.** 회귀 확인은 `uv run pytest` 로 충분하고, 실제 추론이 필요한 사람은 에이전트 오너뿐이다.

모르는 값을 넣으면 **조용히 폴백하지 않고 즉시 예외**로 죽는다. 오타 하나로 개인정보가 외부로 나가면 안 되기 때문이다. 설계 근거는 [ADR-0024](../03_decision/0024-sLLM-로컬-모델-전략.md).

## 4. 자주 물리는 함정

**5432 포트를 다른 PostgreSQL 이 선점한 경우.** Windows 에 네이티브 PostgreSQL 서비스가 있으면 컨테이너 DB 가 정상 기동해도 연결이 그쪽으로 간다. 인증이 실패하고 **DB 의존 테스트가 통째로 error** 가 난다 — 코드 문제가 아니다. 네이티브 서비스를 끄거나, 공용 `docker-compose.yml` 은 두고 개인 오버라이드로 다른 포트를 함께 매핑해 쓴다.

```bash
# 예: 개인 오버라이드 파일에 55432 를 얹고
DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:55432/arda" uv run pytest
```

**MinIO 버킷 이름.** 로컬 S3 는 `minio-init` 이 **`arda-local`** 버킷을 만든다. `S3_BUCKET` 을 실 AWS 이름(`arda-resumes-teamseuk`)으로 둔 채 업로드하면 **전건 404** 로 죽고, 그 404 는 S3 로 직접 PUT 하다 나는 것이라 **API 로그에 안 남는다.** 원인 찾는 데 오래 걸린다.

**요약·임베딩은 응답 뒤에 돈다.** `BackgroundTasks` 라 접수 API 가 201 을 줘도 요약은 아직이다. 실패해도 화면에 안 뜬다 — **DB 에서 건수를 세서 확인해야 한다.**

```sql
select count(*) from applications where ai_summary is not null;
select count(*) from application_embeddings;
```

**`.env` 는 프로세스 시작 때 한 번만 읽는다.** 값을 고쳤으면 API 를 재시작해야 반영된다.
