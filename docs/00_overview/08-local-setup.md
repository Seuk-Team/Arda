# 08. 로컬 환경 — 셋업과 이행 체크리스트

> **이 문서는 "내 PC 에서 왜 안 되지"의 답을 모아 둔 곳이다.** 코드가 아니라 **각자의 로컬 환경**이 원인인 것들만 적는다.
> 스키마·환경변수가 바뀌어 **기존 로컬 환경에 손을 대야 하는 일이 생기면 아래 이행 목록에 추가한다.** 코드는 pull 로 따라오지만 DB 와 `.env` 는 안 따라온다.

## 1. 이행 목록 — 오래된 로컬 환경에 필요한 조치

새로 클론했거나 DB 볼륨을 지우고 다시 만든 사람은 **해당 없다.** 예전부터 쓰던 로컬 DB 만 대상이다.

### 2026-09-01 · `ai_summary_model` 폭 (필수)

```sql
ALTER TABLE applications ALTER COLUMN ai_summary_model TYPE varchar(200);
```

**안 하면 AI 요약이 안 생긴다.** 증상이 고약하다 — Claude 호출 3번을 다 끝낸 뒤 `commit()` 에서 `StringDataRightTruncation` 으로 죽는다. 즉 **돈은 쓰고 결과는 버린다.** 게다가 `generate_summary_bg` 가 `BackgroundTasks` 라 **화면에는 아무 에러도 안 뜬다.**

원인: `models.py` 는 `String(200)` 인데 이 컬럼이 만들어질 당시에는 50 이었고, **`create_all` 은 기존 테이블의 컬럼 타입을 넓혀 주지 않는다.** ([01-erd](01-erd.md) 해당 행에 경위를 적어 뒀다.)

확인:

```sql
select character_maximum_length from information_schema.columns
 where table_name='applications' and column_name='ai_summary_model';
```

> **일반 규칙**: `create_all` 은 **없는 테이블을 만들 뿐** 기존 테이블에 컬럼을 붙이거나 타입을 바꾸지 않는다. alembic 도입 전까지는 스키마를 바꾼 사람이 이 목록에 SQL 을 남긴다.

## 2. 평소 셋업

```bash
git pull
cd backend && uv sync
docker compose up -d --build      # --build 는 아래 이유로 필요할 때가 있다
```

- **`uv sync` 만으로 충분하다.** 로컬 AI 모델(Ollama·faster-whisper)·GPU·새 API 키는 **설치할 필요 없다** — 3절 참고.
- **`--build` 가 필요한 때**: 의존성이 바뀌었을 때, 그리고 2026-09-01 부터는 이미지가 임베딩 모델(약 440MB)을 빌드 단계에 굽는다. **첫 빌드가 느려지고 인터넷이 필요하다.** 대신 그 뒤로는 첫 검색 요청이 멈추지 않는다 ([07-deploy](07-deploy.md) 로컬 AI 모델 절).

## 3. 백엔드 스위치 — 기본값이 곧 기존 동작이다

에이전트의 AI 호출은 백엔드를 고를 수 있다. **아래를 아무것도 설정하지 않으면 지금까지와 완전히 동일하게 돈다.** 로컬 모델을 쓰고 싶은 사람만 값을 넣는다.

| 환경변수 | 기본 | 로컬로 돌리려면 |
|---|---|---|
| `AGENT_CHAT_BACKEND` | `anthropic` | `ollama` |
| `AGENT_SUMMARY_BACKEND` | `anthropic` | `ollama` |
| `STT_BACKEND` | `openai` | `faster_whisper` (`uv sync --extra local` 필요) |

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
