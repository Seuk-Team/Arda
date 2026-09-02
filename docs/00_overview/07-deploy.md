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

**scp 없이 (2026-09-02 부터)**: 레포가 공개라 서버가 직접 받는다 — `~/arda` 에서 `curl -sL https://github.com/Team-Seuk/Arda/archive/<sha>.tar.gz -o /tmp/arda.tgz && tar xzf /tmp/arda.tgz --strip-components=1 -C ~/arda && echo <sha> > DEPLOYED_COMMIT`, 그 뒤 `build` → `up -d` 를 **나눠서**. `docker-compose.prod.yml`·`Caddyfile` 은 레포에 없어 tar 가 덮지 않는다 — 원본은 [infra/](../../infra/) 에 회수해 뒀다(2026-09-02). 서버 것과 다르면 서버가 진실이고 infra/ 를 고친다.

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

~~**남은 것**: 재배포(`96204f9` 포함) → 빈 껍데기 15건 재생성.~~ **둘 다 2026-09-01 낮에 완료** — 아래 [2026-09-01 재배포](#2026-09-01-재배포-팀장) 절. 코드를 고쳐도 이미 저장된 값은 안 바뀌므로 재생성이 따로 필요했다.

> 위에서 "태그가 81자가 된다"고 봤으나 **실측은 91자**였다(`anthropic:` 접두어 몫). 폭 200 으로 넓혀 둔 덕에 문제는 없었다.

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
- SSH 키 없는 PC에서 서버 작업이 필요하면: AWS 콘솔 → EC2 Instance Connect(브라우저 셸, 유저 `ubuntu`). 단, 보안그룹에 SSH 소스 `13.209.1.56/29`(서울 Instance Connect 대역)를 **임시 추가**하고 작업 후 제거한다 (08/28 · 09/02 실사용).
- **AWS 권한 (2026-09-02 이관)**: 계정은 학원 크레딧 때문에 팀장 명의로 유지한다. 운영은 IAM 유저로 — `woojeongalex`(콘솔, 그룹 `arda-ops` = PowerUserAccess: EC2·S3·SES·SQS 전부, IAM·결제 제외) · `arda-server`(콘솔 없음, 서버 `.env` 전용 — S3 버킷 하나·SES 발송·SQS 만 허용하는 `arda-server-policy`). **서버 `.env` 의 AWS 키는 09/02 부터 `arda-server` 것**이고 팀장 개인 키는 비활성화했다. 키가 새면 `arda-server` 키만 재발급하면 된다.
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

## 2026-09-01 재배포 (팀장)

`ba78a9d` 기준. `git archive main` → scp → 서버에서 tar 해제 → `up -d --build`.

| 단계 | 결과 |
|---|---|
| `docker builder prune -f` | 1.76GB 회수 (빌드 전 9.6G → 11G 여유) |
| 빌드 | **약 6분**, OOM 없음. 이미지 382MB → **791MB**(임베딩 모델을 구운 몫) |
| `up -d` | api·worker 재생성, 16초 뒤 정상 |
| `/health` | 200 |
| 신규 경로 401 | `/postings`·`/users`·`/email-templates` — 라우트 살아 있고 인증 걸림 |
| CORS preflight | 허용 출처 200 + `Access-Control-Allow-Origin`, 모르는 출처 400에 헤더 없음 |

**t3.micro(RAM 1GiB)에서 임베딩 모델 프리페치가 OOM 날 것을 걱정했으나 통과했다**(스왑 2G 여유 있었고 `dmesg` 에 OOM 기록 없음). 다만 이미지가 두 배가 됐으니 디스크 여유를 계속 봐야 한다.

**빌드와 `up` 을 나눠 돌렸다** — `docker compose build` 로 먼저 만들고 성공을 확인한 뒤 `up -d` 했다. 빌드가 실패해도 돌던 컨테이너가 안 죽는다. G4 때 디스크 고갈로 api·worker 를 내려야 했던 것과 대비되는 지점이다.

### 재배포 뒤에 한 것

1. **AI 요약 재생성.** 배포 전 21건 중 15건이 `{"insufficient": true, "gist": "", ...}` 빈 껍데기였다 — `SUMMARY_MAX_TOKENS=500` 에서 step1 이 잘려 JSON 이 깨진 것(`96204f9` 가 1500 으로 수정). **관문 확인**: 내용 있는 지원서 1건을 먼저 재생성해 태그가 **91자**(`anthropic:...chain_summarize.v1+chain_evaluate.v1+chain_recommend.v1`)로 저장되고 `insufficient: false` 가 나오는 것을 확인한 뒤 나머지를 돌렸다. **폭 50 이었으면 여기서 죽었다** — ALTER 가 재배포보다 먼저여야 했던 이유다.
2. **`insufficient: true` 가 남는 것이 정상인 건도 있다.** id 7·8 은 **자소서 0자·첨부 0개인 테스트 계정**(`음머(테스트)`·`김데모`)이라 그 판정이 정답이다. 버그로 오해하기 쉬우니 적어 둔다.
3. **Vercel rewrite 제거 머지.** CORS 가 운영에 살아 있는 것을 실측으로 확인한 뒤 머지했다. 이로써 **지원자 자소서를 포함한 모든 API 요청이 제3자(Vercel) 서버를 통과하던 경로가 없어졌다.** 프론트는 `VITE_API_BASE` 로 API 를 직접 부른다.

**백업**: `~/docker-compose.prod.yml.bak-0901deploy` · `~/backend.env.bak-0901deploy`.

## 2026-09-01 저녁 재배포 (팀장)

`046cee9` 기준. 같은 절차 — `git archive origin/main` → scp → 서버에서 tar 해제 → `up -d --build`.

들어간 것: 요약 분량 축소(`6905c37`) · alembic 도입(`5941ae7`) · `create_admin` 부트스트랩 수정(`d96749e`). 프론트 몫(아르 요약 제목·앰버 제거, 면접 포인트 숨김)은 Vercel 자동 배포로 이미 반영돼 있었다.

| 단계 | 결과 |
|---|---|
| 임베딩 모델 프리페치 | **66.7초** (`#15 DONE 97.0s`). HF 익명 다운로드 경고는 속도 제한 안내일 뿐 |
| `up -d --build` | api·worker 재생성 |
| `ps` | api·worker `Up`, db `Up 24h (healthy)`, caddy `Up 5d` |
| COMMAND | `/app/.venv/bin/uvic…` · `/app/.venv/bin/pyth…` — `df25669` 의 직접 호출 유지 |
| `/health` | `{"status":"ok"}` |

**DB 작업은 없었다.** `5941ae7` 이 alembic 을 들여왔지만 **런타임 의존성이 아니라 컨테이너 기동 때 돌지 않는다**(`backend/alembic/README.md`). 운영은 09/01 낮에 실측 후 `0002` 로 stamp 를 마쳤으므로 이번 배포에 이행이 걸려 있지 않다.

**이번에 하지 않은 것** — 다음에 참고:

- **빌드 전 `df -h` 를 건너뛰었다.** G4 때 디스크 고갈로 깨진 적이 있으니 원래는 봐야 한다. 결과적으로 통과했지만 확인하고 들어간 것은 아니다
- **빌드와 `up` 을 나누지 않았다.** 직전 재배포는 `build` 성공을 확인한 뒤 `up` 했는데, 이번엔 `up -d --build` 한 번으로 갔다. 빌드가 깨졌으면 돌던 컨테이너가 같이 내려갔을 것이다
- ~~**AI 요약 재생성은 안 했다.**~~ **같은 날 밤에 21건 재생성 완료** — 아래 "AI 요약 재생성" 절. `6905c37` 은 프롬프트만 짧게 만들 뿐 **이미 저장된 요약은 안 바뀐다**

### 같은 날 — 메일 시연용 실제 주소 반영 (운영 DB)

SES 샌드박스라 검증된 주소로만 발송된다. 시연 대상 5명의 `applications.email` 을 팀원 실주소로 바꿨다.

| id | 공고 | 지원자 | 주소 |
|---|---|---|---|
| 9 | 1 | 곽민재 | `ssuvisdev@gmail.com` |
| 10 | 1 | 문해린 | `dnwjdwkd11@gmail.com` |
| 12 | 1 | 서지호 | `fennec925@gmail.com` |
| 15 | 1 | 한도윤 | `minmom7898@gmail.com` |
| 20 | 2 | 유하람 | `hisoyeon04@gmail.com` |

⚠️ **원안 SQL 은 `UNIQUE(job_posting_id, email)` 에 걸려 롤백됐다.** 테스트 행 **id 8 `김데모` 가 공고 1 에서 `ssuvisdev@gmail.com` 을 이미 쓰고 있어서** 같은 공고의 곽민재(id 9) 배정이 거부됐다. **지원자만 세고 테스트 행을 빠뜨린 것이 원인이다.** id 8 을 `demo.kim@example.com` 으로 비우고 반영했다 — **되돌리려면 id 9 를 먼저 비운 뒤 id 8 을 복구해야 한다.** 순서를 바꾸면 같은 제약에 다시 걸린다.

**id 7 `음머(테스트)` 는 공고 2 에서 `fennec925@gmail.com` 을 그대로 쓴다.** 서지호(공고 1)와 제약은 겹치지 않지만 **한 메일함에 두 지원자의 발송이 섞여 들어온다.** 위 "재배포 뒤에 한 것" 2번의 id 7·8 서술은 이름 기준이라 그대로 유효하다.

각 `UPDATE` 에 `AND name=` 가드를 붙였다 — id↔이름이 어긋나면 `UPDATE 0` 이 되어 **엉뚱한 지원자의 주소가 조용히 바뀌지 않는다.**

~~**메일은 아직 안 나갔다.**~~ **같은 날 밤 3건 실발송 완료** — 아래 "메일 시연 3건" 절. `email_logs.to_email` 은 발송 시점 스냅샷이라 과거 실패 로그는 그대로다. 실발송을 보려면 단계 이동이나 `POST /applications/{id}/emails` 로 새로 트리거해야 하고, **워커가 `MAIL_DRY_RUN=0` 이라 누르는 즉시 실제로 나간다** — 한도윤(부적합)은 불합격 메일이다.

### 같은 날 밤 — AI 요약 재생성 21건 + 메일 시연 3건 실발송

위 두 절이 남겨 둔 것을 닫았다. **코드 변경 없음 — 운영 데이터 작업이다.**

#### AI 요약 재생성

`6905c37`(프롬프트 축소)은 이미 저장된 요약을 바꾸지 않는다. 그래서 재생성이 따로 필요했다.

**화면에 재생성 버튼이 없다.** `POST /agent/applications/{id}/summarize` 는 API 에만 있고 `ApplicantPanel` 에 붙어 있지 않다. 관리자 화면에 로그인한 세션으로 그 엔드포인트를 id 목록만큼 반복 호출했다(동시 2). **21건 전부 성공 · 85초 · 실패 0.** 문해린(10)은 09/01 저녁에 이미 새 프롬프트로 재생성해 두어 대상에서 뺐다.

분량 검증 — 화면에 노출되는 것은 **요지 + 강점 + 확인 필요** 세 덩어리다.

| 지표 | 결과 |
|---|---|
| 강점 개수 | **21명 전원 2개** (기준: 2개 이하) ✅ — 나머지 1명(김데모)은 `insufficient` 라 강점 자체가 없다 |
| 합계 | 중앙값 **260자** · 평균 268자 · 범위 205~340자 |
| 항목당 50자 초과 | **7건 / 4명** — 최민서 4 · 배수아 1 · 구태윤 1 · 천유진 1 |

축소 전이 **919자**였으므로 약 1/3.5 다. 목표로 잡았던 230자보다는 조금 위인데, **총량을 밀어올리는 것은 강점·확인이 아니라 요지다** — 강점은 전원 2개로 잘 잡혔고 요지가 74~157자로 편차가 크다. 더 줄이려면 요지 쪽 프롬프트를 조인다.

⚠️ **`김데모`(id 8) 만 여전히 `insufficient` 로 화면에 "제출물 부족"이 뜬다.** 프로필이 비어 있는 테스트 행이라 모델 판단은 맞다. 다만 **이 행이 공고 1 의 `면접` 단계에 있어 대시보드·칸반에 그대로 보인다** — 시연 중에 열리면 눈에 띄는 자리다.

#### 메일 시연 3건

관리자 화면의 수동 발송 UI(`ApplicantPanel` 메일 프리셋 → 확인 모달 → 발송)로 보냈다. 수신자는 서버가 `applications.email` 로 고정하므로 화면이 주소를 정하지 않는다.

| id | 지원자 | 문구 | 받는 사람 | 상태 |
|---|---|---|---|---|
| 12 | 서지호 | 면접 안내 | `fennec925` (팀장) | **발송됨** |
| 20 | 유하람 | 면접 안내 | `hisoyeon04` (소연) | **발송됨** |
| 15 | 한도윤 | 불합격 | `minmom7898` (민아) | **발송됨** |

셋 다 `대기`(queued) → `발송됨`(sent) 전환까지 확인했다. **단계는 셋 다 `지원 접수` 그대로다** — 「불합격」 버튼이 단계 변경에도 하나, 메일 프리셋에도 하나 있어서 메일 쪽만 눌렀고 발송 뒤 단계를 다시 확인했다. 곽민재(9)·문해린(10)은 09/01 에 이미 받았으므로 대상이 아니었다.

**남은 것**: 접수 확인 메일 15건이 `failed`(`applied` · `example.com`)로 그대로다. `email_logs.to_email` 이 발송 시점 스냅샷이라 주소를 바꿔도 되살아나지 않는다. **지원자 상세를 열면 방금 보낸 「발송됨」 바로 아래에 「실패」가 같이 보인다.** 그냥 두기 / 로그 정리 / 새로 한 통 보내 덮기 중 어느 쪽인지는 팀에서 정할 일이다.

> ⚠️ **이 재생성은 `35ba4b5` 배포 전 기준이다 — 다음 배포 뒤에 한 번 더 돌려야 한다.** `35ba4b5`(같은 날 17:07, 에이전트 오너)가 요약 스키마에 상한을 넣었다: **gist 160자 · 리스트 항목 40자.** 위 재생성은 그 직전 배포본(`046cee9`)으로 돌아서 새 상한을 안 받았다. 실측하면 **gist 는 최대 157자로 전부 통과하는데, 리스트 항목은 40자 초과가 21명 중 18명·49건(최대 66자)** 이다. 지금 화면이 깨지는 것은 아니지만 **저장된 값이 곧 배포될 규격과 다르다.** 재생성은 21건에 85초라 배포 직후 다시 돌리면 된다.

## 2026-09-02 재배포 (팀장) — 백엔드 오너 요청분 + 검증 데이터 정리 + AWS 권한 이관

`f227673` 기준. 이번 PC 에는 SSH 키가 없어 **Instance Connect + 서버가 GitHub 타르볼을 직접 받는** 방식으로 갔다(위 "재배포" 절에 절차 추가). 들어간 백엔드 변경은 둘 — `35ba4b5`(요약 스키마 상한·단계 라벨 통합) · `b99a7b8`(alembic dev 의존). DB 이행 없음.

| 단계 | 결과 |
|---|---|
| `df -h /` | 60% (7.5G 여유) — 빌드 전에 봤다 |
| `build` (up 과 분리) | **성공 · 266초.** uv 0.5.11 이 `uv.lock revision = 3` 을 읽었다 — README 가 걱정하던 조합은 실측으로 문제없음 |
| `up -d` | api·worker 재생성, `/health` ok, 첫 로그 `APP_ENV=production — 보안 게이트 켜짐` |
| `DEPLOYED_COMMIT` | 서버 파일이 `58ae0ff` 로 낡아 있었다(실제 배포본은 09/01 `046cee9`). `f227673` 로 갱신 |

**검증 데이터 삭제** (백엔드 오너 부탁 — API 로는 지원자 삭제 경로가 없고 공고는 지원서가 있으면 409): 지원자 id 24(우정알렉스 · C7 검증) · 공고 id 3(`closed`). 이름·상태 가드를 건 트랜잭션 하나로 — 자식 행 `application_embeddings`·`email_logs`·`files`·`stage_history` 각 1건, 나머지 5종 0건, 본체 2건. S3 객체 `applications/bce2d52f-…/resume.pdf` 도 api 컨테이너의 boto3 로 지웠다. 기존 공고 2개·지원자 23명은 그대로.

**서버에만 있던 설정 회수**: `docker-compose.prod.yml`·`Caddyfile` → [infra/](../../infra/). 시크릿 리터럴 없음(`DB_PASSWORD` 는 `.env` 참조).

**AWS 권한 이관** (위 "주의" 절): IAM 유저 `woojeongalex`(운영 콘솔) · `arda-server`(서버 `.env` 키) 신설. `.env` 키 교체 후 `up -d --force-recreate api worker` 로 반영 — `sts get-caller-identity` 가 `user/arda-server` 를 반환하는 것까지 확인. 팀장 개인 액세스 키는 비활성화(삭제 아님 — 되돌릴 수 있게).

**남은 것**: AI 요약 재생성 22건 — 백엔드 오너가 돌리기로 함(85초). SES 재신청 결과는 여전히 미확인.
