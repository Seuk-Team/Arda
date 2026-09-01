# 07. 배포 — 실서버 구성과 사용법

> **작성**: 2026-08-27 bestcow (인프라) · W2 실배포 1차 완료분. 변경은 인프라 도메인 소관.

## 주소 (전 팀원 공통)

| 무엇 | URL | 비고 |
|---|---|---|
| **API** | https://api.arda.seuk.cloud | Swagger는 `/docs`. HTTPS만 — 8000 직접 접근은 막혀 있다 |
| **프론트** | https://arda-nu.vercel.app | main 머지 → 1~2분 내 자동 재배포. 커스텀 도메인 `arda.seuk.cloud` 검증 마무리 중 |
| 공개 지원 링크 | `https://arda.seuk.cloud/apply/<token>` | 서버 `PUBLIC_APP_BASE_URL` 기준으로 생성 (B6) |

**프론트·앱의 API 베이스 주소는 `https://api.arda.seuk.cloud`다** — W3 연동 때 이 값을 쓴다. HTTPS라 mixed content·Flutter 예외 설정 문제 없음.

## 운영 서버 계정 (중요)

**운영 서버는 공개 회원가입이 잠겨 있다** (`APP_ENV=production` — 공개 signup 차단, #117). **전 팀원 admin 계정 발급됨 (08/28)** — 초기 비밀번호는 팀 채널 공지 참고. 추가 계정이 필요하면 아무 admin이나 로그인 후 `POST /auth/signup`(Swagger `/docs`)으로 만든다. 로컬 개발은 기존처럼 자유 가입.

## 구성 (요약)

```
브라우저 ── https ──> Vercel (frontend/app, main 자동 배포)
브라우저/앱 ── https ──> Caddy(443, 인증서 자동) ──> FastAPI api:8000   ┐
                                                     PostgreSQL db      ├ EC2 (docker compose)
                                                     SQS 워커 worker    ┘
파일: 브라우저 ── presigned URL ──> S3 (서버 미경유)
메일: api → SQS 큐 → worker → SES (샌드박스 — 해제 신청 08/27 거절, 검증된 수신자만 발송 가능)
```

- EC2: 서울, t3.micro + 스왑 2G, 고정 IP(Elastic IP). SSH는 팀장 PC에서만 열려 있다.
- 컨테이너 4개(db·api·worker·caddy) 전부 `restart: unless-stopped` — 재부팅 자동 복구.
- 서버 compose는 `docker-compose.prod.yml`(로컬 개발용 루트 compose와 별개 — --reload 없음, DB 포트 비공개).
- **S3 버킷 CORS (2026-08-31 설정)**: 이력서는 브라우저에서 S3 로 직행하는데, 버킷에 CORS 규칙이 **없어서 브라우저 업로드가 막혀 있었다.** 아래를 넣어 풀었다.

  | 항목 | 값 |
  |---|---|
  | AllowedMethods | `PUT` |
  | AllowedOrigins | `https://arda.seuk.cloud` · `https://arda-nu.vercel.app` · `http://localhost:5173` |
  | AllowedHeaders | `*` (preflight 의 Content-Type 통과용) |

  **프론트 주소가 늘면 여기에도 추가해야 한다.** 빠지면 그 출처에서만 업로드가 실패하는데, **API 는 정상이고 서버 로그에도 안 남는다** — CORS 는 브라우저만 검사하기 때문이다. 서버 간 PUT(테스트·curl)은 영향을 받지 않아서, 이 결함은 브라우저로 실제 파일을 올려봐야만 드러난다.
  버킷이 공개되는 설정이 아니다 — 업로드 권한은 그대로 presigned URL 이 정한다.

## 2026-08-31 저녁 — pgvector 도입과 그 과정의 장애

**증상**: 재배포 직후 API 가 재시작 루프(`exit=3`, `restarts=10`)에 빠져 `/health` 가 502.

**원인**: [ADR-0021](../03_decision/0021-RAG-시맨틱-검색.md)(RAG)이 DB 커넥션마다
`CREATE EXTENSION IF NOT EXISTS vector` 를 거는데 운영 DB 이미지(`postgres:16-alpine`)에
확장이 없었다. 커넥션 생성에서 예외가 나면서 lifespan 이 죽었다 — **확장 하나 때문에
API 전체가 안 뜬 것**이다.

**조치 2단계**
1. **fix-forward**(`6c7308a`): 확장을 못 켜면 경고만 남기고 넘어간다. `create_all` 도
   `application_embeddings`(vector 타입)를 건너뛰게 했다 — 그 CREATE TABLE 이 실패하면
   뒤 테이블까지 못 만든다. 시맨틱 검색만 꺼지고 API 는 뜬다.
2. **DB 이미지 교체**: `postgres:16-alpine` → **`pgvector/pgvector:pg16`**. 같은 PG 16 이라
   `arda_pgdata` 볼륨을 그대로 쓴다. 교체 후 `CREATE EXTENSION vector`(0.8.6) 성공,
   `application_embeddings` 생성 확인, 데이터 무사(users 7 · applications 7).

**교체 시 한 것 (다음에도 그대로)**
- 먼저 덤프: `docker compose -f docker-compose.prod.yml exec -T db pg_dump -U postgres -d arda > ~/arda-db-backup-<날짜>.sql` (서버 `~/arda-db-backup-20260831.sql`, compose 원본은 `docker-compose.prod.yml.bak`)
- 이미지 줄만 교체 후 `docker compose -f docker-compose.prod.yml up -d db`
- **alpine(musl) → debian(glibc)** 로 libc 가 바뀌므로 텍스트 인덱스 정렬 기준이 달라질 수 있다 → `REINDEX DATABASE arda;`
- api 재기동 후 기동 로그에 pgvector 경고가 **없는지** 확인

**남은 것**
- **로컬 compose(`docker-compose.yml`)는 2026-08-31 에 `pgvector/pgvector:pg16` 으로 맞췄다** — repo 로 환경을 세워도 같은 장애가 안 난다. 다만 **기존 로컬 `pgdata` 볼륨(alpine=musl)을 쓰던 사람은** 베이스가 glibc 로 바뀌므로 `docker compose down -v`(권장) 또는 `REINDEX DATABASE arda;` 가 필요하다 — compose 의 `db` 주석에 같은 내용이 적혀 있다.
- `docker-compose.prod.yml` 은 여전히 **서버에만 있고 repo 에 없다.** 운영 이미지 교체도 repo 에 안 남았다 — 서버를 새로 만들면 그쪽만 alpine 으로 되돌아간다. `infra/` 로 올리는 게 맞다(인프라 오너).
- 기존 지원자 7명의 **임베딩 백필**이 없다. 테이블만 있고 임베딩은 요약 생성 시점에 만들어진다(`summarizer.py`) — 기존 건까지 검색되게 하려면 백필 필요(에이전트 오너).

**배포 관련 두 가지 기억할 것**
- 백엔드는 수동 배포라 **프론트(Vercel 자동)와 쉽게 어긋난다.** 이번에도 배포본 프롬프트가 `#151`·`#153` 이전 버전이라 에이전트가 자기 이름("아르")을 몰랐다.
- ~~컨테이너 `Started` 이후 실제 서비스까지 약 2분~~ → **2026-09-01(`df25669`) 이후 15초.** 그 2분은 런타임 venv 재설치 시간이었고 지금은 없다(아래 "G4 배포와 디스크 고갈"). 배포 직후 502 가 계속되면 기다릴 게 아니라 로그를 본다.

## 2026-09-01 — G4 배포와 디스크 고갈

**증상**: 재배포 빌드가 `torch` 내려받다 `No space left on device`. 디스크 97%(590M 남음).

**원인**: **컨테이너가 뜰 때마다 venv 를 쓰기 레이어에 다시 설치하고 있었다.** 이미지는 382MB 인데 `arda-api-1` 5.62GB · `arda-worker-1` 5.18GB — 둘이 10.8GB 를 먹어 19GB 디스크에 새 이미지가 들어갈 자리가 없었다. CMD·compose `command` 가 `uv run …` 이라 기동 때 잠금 파일과 환경을 맞추고, 어긋난다고 판단하면 통째로 재설치한다. 게다가 그렇게 깔린 것이 CPU 가 아니라 **CUDA torch(`2.13.0+cu130`)** 였다 — `2193f28` 이 CPU-only 로 락을 재생성하기 전 배포본이 런타임에 직접 끌어온 것이다.

**조치**: `backend/Dockerfile` 의 CMD 와 서버 `docker-compose.prod.yml` 의 `command` 를 **`/app/.venv/bin/…` 직접 호출**로 바꿨다 (`df25669`). 기동이 곧 실행이라 재설치가 일어나지 않는다.

| | 전 | 후 |
|---|---|---|
| 컨테이너 쓰기 레이어 | api 5.62GB · worker 5.18GB | **각 4.1kB** |
| 이미지 | 382MB (venv 없음) | 1.42GB (CPU torch 포함) |
| 디스크 | 97% | **48%** |
| 기동 → 서비스 | 약 2분 | **15초** |

**공간이 모자랄 때의 순서** (다음에도 그대로):

1. `docker builder prune -af` + `docker image prune -af` — 안전하지만 이번엔 부족했다(약 900MB)
2. 그래도 모자라면 **`docker compose -f docker-compose.prod.yml stop api worker && rm -f api worker`** → 약 10GB 확보. **다운타임 ~6분**(빌드 + 기동). db·caddy 는 계속 뜬 상태다
3. **`--volumes` 는 절대 붙이지 않는다** — `arda_pgdata` 가 날아간다

⚠️ **`docker-compose.prod.yml` 의 `command` 두 줄은 서버에서 직접 고쳤다**(백업 `docker-compose.prod.yml.bak-g4`). 그 파일은 여전히 repo 에 없어서 **서버를 새로 만들면 `uv run` 으로 되돌아간다.** `infra/` 로 올리는 게 맞다(인프라 오너).

## 메일 발송 주체와 회신 주소 (G4)

발신 주소는 언제나 `SES_FROM_EMAIL`(`no-reply@arda.seuk.cloud`) 하나다. 담당자 개인 주소를 From 에 넣으면 외부 메일(gmail)에서 **DMARC 정렬이 깨져 스팸함으로 간다.** 개인을 드러내는 것은 **From 표시 이름과 Reply-To** 가 맡는다.

| `email_logs.actor_kind` | From 표시 이름 = 본문 서명 | Reply-To |
|---|---|---|
| `human` | `Arda 채용 담당자 {이름}` | 그 사람의 `users.email` |
| `agent` | `Arda 채용 에이전트 아르` | `MAIL_REPLY_TO` |
| `system` | `Arda 채용팀` | `MAIL_REPLY_TO` |

**서버 `.env` 에 `MAIL_REPLY_TO=seukathon@gmail.com`** (2026-09-01 설정). Reply-To 는 SES 검증 대상이 아니라 실제 수신 가능한 메일함이면 된다. **비우면 아르·시스템 발송의 회신이 증발한다** — 문구가 전부 "이 메일에 회신해 주시기 바랍니다"라고 말하기 때문이다. 합격·불합격은 주체와 무관하게 사람 이름으로 서명한다(설계 근거는 [G4 지시서](../02_tasks/G4-설정-실동작-메일-발송.md) 결정 6~8).

## 재배포 (현재는 수동 — 팀장)

main 기준 `git archive` → scp → 서버에서 `docker compose -f docker-compose.prod.yml up -d --build`. **CI/CD(J4, main 머지 시 자동 배포)는 W3에 이 절차를 대체한다.** 그 전까지 "배포 서버에 반영해달라"는 팀 채널로.

## 1회성 DB 이행

스키마는 `create_all` 로 만들지만([db.py](../../backend/app/db.py)), **이미 데이터가 있는 DB** 는 값·제약을 바꿀 수단이 없다. 그런 변경은 `backend/scripts/` 에 SQL 파일로 두고 여기에 실행법을 적는다.

| 파일 | 언제 | 실행 | 상태 |
|---|---|---|---|
| `migrate_roles_to_member.sql` | 역할 2종화 배포 시 1회 ([ADR-0017](../03_decision/0017-등급-이분화.md)) | `psql "$DATABASE_URL" -f backend/scripts/migrate_roles_to_member.sql` | **2026-08-31 실행 완료** |
| `upgrade_settings_mail.sql` | 설정 실동작·메일 발송 배포 시 1회 ([G4](../02_tasks/G4-설정-실동작-메일-발송.md)) | `psql "$DATABASE_URL" -f backend/scripts/upgrade_settings_mail.sql` | **2026-09-01 실행 완료** |

**2026-08-31 실행 기록**: 새 코드를 먼저 배포(`docker compose -f docker-compose.prod.yml up -d --build` — api·worker 재생성, 컨테이너의 `ROLES` 가 `("admin", "member")` 인 것을 확인)한 뒤 컨테이너 안에서 돌렸다. `UPDATE 1`(interviewer 1명 → member), 결과 `admin 6 / member 1`, 제약이 `CHECK (role IN ('admin','member'))` 로 교체된 것까지 확인. 서버에서는 `docker compose -f docker-compose.prod.yml exec -T db psql -U postgres -d arda -v ON_ERROR_STOP=1 -f - < backend/scripts/migrate_roles_to_member.sql` 로 실행한다.

**2026-09-01 실행 기록 (G4)**: 덤프(`~/arda-db-backup-20260901-g4.sql`) → `.env` 에 `MAIL_REPLY_TO` 추가(`backend/.env.bak-g4` 백업) → SQL 실행 `COMMIT` → 재배포 순으로 진행했다. 반영 확인: `users.is_active`, `email_logs.subject/body/actor_kind/actor_id`, `ck_email_logs_stage` 에 `custom`, `email_logs_actor_id_fkey`. 배포 후 신규 7경로가 전부 401(라우트 살아 있고 인증 걸림), 워커 `restarts=0`, 실발송 2통(사람·에이전트) `sent` 확인.

**2026-09-01 — 손 SQL 시대 종료 (alembic 전환)**. 이 표는 여기까지다. 이후 스키마 변경은 `backend/alembic/versions/` 에 리비전으로 쌓이고, 배포 때 `upgrade head` 한 번이면 따라온다.

운영 DB 를 alembic 관리 아래로 넣은 절차 (실행 완료):

1. **실측 먼저.** `stamp` 는 "이미 이 상태다"라고 선언하는 것이라 실제와 다르면 그 차이가 영구히 숨는다. 확인 결과 — `ai_summary_model` **50**(미이행) · `application_embeddings` 있음 · pgvector 있음 · `alembic_version` 없음 · role `admin 6 / member 1`
2. **`ALTER TABLE applications ALTER COLUMN ai_summary_model TYPE varchar(200);`** — 0002 의 1단계를 손으로. 넓히기만 하므로 비파괴
3. **`alembic_version` 생성 + `0002` 삽입** — `stamp head` 와 같은 효과. 서버에 alembic 을 설치하지 않았다(디스크가 빠듯하고, `stamp` 는 행 하나 쓰는 게 전부다)
4. 확인: 폭 **200** · version **0002** · 행 1개

> ⚠️ **`stamp head` 만 돌렸으면 안 됐다.** 인계받은 안내는 "운영은 이행을 이미 마쳤으니 stamp 만"이었는데 **실측에서 폭이 50 이었다.** 그대로 찍었으면 alembic 이 0002 를 적용했다고 기록하고 **다시는 안 고쳤다.**

> **왜 지금 급했나 — 두 버그가 물려 있었다.** 운영 요약 21건 중 15건이 `{"insufficient": true, "gist": "", ...}` 빈 껍데기이고 태그가 전부 44자(`chain_summarize.v1` 한 단계뿐)다. `SUMMARY_MAX_TOKENS=500` 에서 step1 이 잘려 JSON 이 깨진 것(`96204f9` 가 1500 으로 고쳤으나 **미배포**). 폭 50 이 아직 안 문 이유가 바로 이것이다 — 태그가 44자라 들어갔다. **수정을 배포하면 태그가 81자가 되면서 그때부터 저장이 죽는다.** 그래서 ALTER 가 재배포보다 먼저여야 했다.

**남은 것**: 재배포(`96204f9` 포함) → 빈 껍데기 15건 재생성. 코드를 고쳐도 이미 저장된 값은 안 바뀐다.

**⚠️ 팀원 로컬 DB 도 같은 SQL 이 필요하다.** `create_all` 은 **기존 테이블에 컬럼을 못 붙인다.** pull 만 받고 로컬을 띄우면 새 코드의 ORM 이 `users.is_active` 를 SELECT 에 실어서 **전 요청이 500** 난다. 둘 중 하나를 한다:

```
# (권장) 로컬 데이터를 버리고 새로 만든다 — create_all 이 전부 만들어 준다
docker compose down -v && docker compose up -d db

# 데이터를 살리려면 이행 SQL 을 돌린다 (멱등, 재실행 무해)
psql "$DATABASE_URL" -f backend/scripts/upgrade_settings_mail.sql
```

**`upgrade_settings_mail.sql` 은 순서가 반대다 — SQL 먼저, 재배포 나중.** 새 코드의 ORM 이 `users.is_active` 를 SELECT 에 실으므로 컬럼 없이 새 코드가 뜨면 전 요청이 죽는다(구 코드는 새 컬럼이 있어도 무해하다). `ADD COLUMN IF NOT EXISTS` 로 멱등하게 써 두어 재실행해도 안전하다. 신규 테이블 `email_templates` 는 `create_all` 이 만들므로 SQL 에 없다. 배포 전에 `MAIL_REPLY_TO`(지원자 회신을 받을 팀 공용 주소)를 서버 `.env` 에 넣어야 한다 — 비우면 회신이 증발한다.

역할 이행은 `recruiter`·`interviewer` → `member` 로 바꾸고 `ck_users_role` 체크 제약을 새 값으로 갈아끼운다. **새 코드(`ROLES = ("admin", "member")`)가 올라간 뒤에 돌린다.** 트랜잭션 하나로 묶여 있어 중간에 실패하면 전부 되돌아가고, 모르는 role 값이 남아 있으면 일부러 멈춘다.

## 도메인별로 달라진 것 (08/27)

| 도메인 | 달라진 것 |
|---|---|
| 프론트 | Vercel 자동 배포 연결 완료 — 머지하면 바로 URL에 뜬다. 수직 슬라이스(게이트 마지막 조건)는 지원 폼 화면 대기 중 |
| 앱 | 실 API 베이스 주소 확보 — W3 연동 때 위 주소 사용 |
| 에이전트 | ANTHROPIC_API_KEY 서버 주입·실호출 검증 완료 — 배포 URL 기준 E2E 데모 가능. AI 요약이 운영에서 실동작 |
| 백엔드 | 코어 API 전부 배포 Swagger에서 동작. 워커 SQS 대기 중 — 실발송 E2E는 수직 슬라이스 때. Dockerfile `scripts/` COPY 누락은 레포에서 수정됨(#124) — 서버 이미지는 다음 재배포 때 반영 |

## 주의

- 시크릿(SSH 키·admin 비밀번호·API 키)은 이 문서에 없다 — 필요하면 팀장에게.
- SSH 키 없는 PC에서 서버 작업이 필요하면: AWS 콘솔 → EC2 Instance Connect(브라우저 셸, 유저 `ubuntu`). 단, 보안그룹에 SSH 소스 `13.209.1.56/29`(서울 Instance Connect 대역)를 **임시 추가**하고 작업 후 제거한다 (08/28 실사용).
- SES는 샌드박스 유지 — **해제(발송 한도 증가) 신청이 08/27 거절됨.** 실발송 테스트는 검증된 수신자(팀원 메일 등록)로만 가능하고, 데모도 이 방식으로 충분. SNS 바운스·컴플레인트 알림 연결 후 **08/28 재신청 제출 — 결과 대기.**


## 로컬 AI 모델 — 런타임에 인터넷을 타지 않게 (2026-09-01)

`sentence-transformers` 와 `faster-whisper` 는 모델이 없으면 **첫 사용 시점에 HuggingFace 에서 내려받는다.** 그래서 그냥 두면:

1. 에어갭·온프레미스 환경에서 죽는다
2. 프라이빗 서브넷이면 NAT 게이트웨이가 있어야 한다 — **"외부 호출 0건"이 아니게 된다**
3. 첫 요청만 수십 초 걸린다. 담당자 눈에는 "가끔 멈추는 앱"이다

**빌드 때 굽고 런타임엔 잠근다.** `backend/Dockerfile` 이 이미 그렇게 한다:

```dockerfile
ENV HF_HOME=/app/.hf
RUN /app/.venv/bin/python scripts/prefetch_models.py
ENV HF_HUB_OFFLINE=1
```

`HF_HUB_OFFLINE=1` 을 거는 이유는 속도가 아니라 **실패를 눈에 띄게** 하기 위해서다. 모델이 빠졌을 때 조용히 내려받으면 그 사실을 아무도 모른다.

**GPU 장비(로컬 STT·채팅용)는 STT 모델도 받아야 한다** — 이미지에는 안 들어 있다(optional extra 라 t3.micro 에 얹지 않는다):

```bash
uv sync --extra local
uv run python scripts/prefetch_models.py --stt
```

실측(2026-09-01, RTX 3050): 임베딩 `ko-sroberta` 11초 · STT `large-v3` 70초. 받은 뒤 `HF_HUB_OFFLINE=1` 상태에서 임베딩 로드와 한국어 전사가 모두 정상 동작하는 것을 확인했다.

**캐시 경로가 빌드와 런타임에서 같아야 의미가 있다.** 볼륨으로 덮어쓰면 구운 것이 가려진다 — `HF_HOME` 을 볼륨 밖에 두거나, 볼륨 쪽에 다시 받아라.
