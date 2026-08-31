# 프로젝트 진단 보고서

> 작성: 2026-08-25 · 기준 커밋 `3b27a94` (main) · 작성 경위: 팀장 요청으로 전체 코드를 읽고 진단
> 읽는 대상: 팀원 전원. 전문 용어는 처음 나올 때 한 줄로 풀었다.

---

## 진단 1 — 팀장에게 안 물어보고 작업할 수 있는 구조인가

결론부터: **대체로 그렇다.** 계약 문서(ERD·API 명세)와 코드가 잘 맞물려 있고, 도메인 오너제 + domain-guard로 경계가 물리적으로 강제된다. 다만 아래 공백들이 "결국 팀장에게 물어봐야 하는 순간"을 만든다.

### 1-1. API 계약 — 있음, 공백 3개

API 명세는 [docs/00_overview/02-api.md](00_overview/02-api.md)에 표로 고정돼 있고, 서버를 띄우면 Swagger(`/docs` — 코드에서 자동 생성되는 API 설명 화면)로도 확인된다. 프론트 담당이 백엔드 코드를 열지 않고 작업할 수 있는 수준이다. 공백은:

1. **일부 엔드포인트의 권한(role)이 명세에 없다.** 예: 공고 수정·삭제 API는 "누가 할 수 있는지"가 문서에 없어서, 구현자가 주석으로 보류를 남겨뒀다 — [backend/app/api/postings.py:60-62](../backend/app/api/postings.py). 이미 이슈 #59로 열려 있고 팀장 소관이다. **명세에 role이 비면 팀원은 결국 물어봐야 한다.**
2. **에러 코드 계약이 실제 응답과 어긋난다.** 프론트는 에러 응답의 `code` 값으로 분기하기로 돼 있는데([backend/app/errors.py:5-11](../backend/app/errors.py)), 로그인 안 됨(401)이 권한 없음(403)과 같은 `FORBIDDEN` 코드로 나간다 — [backend/app/main.py:80-81](../backend/app/main.py). 프론트가 "재로그인 시켜야 할지"를 구분 못 한다. 이슈 #60.
3. **에이전트 API 4종이 명세에 없다.** `/api/v1/agent/*` (요약 재생성·채팅·확인 실행)가 코드에는 있는데([backend/app/api/agent.py:65-141](../backend/app/api/agent.py)) 02-api.md에는 한 줄도 없다. 에이전트 UI를 붙일 프론트 담당은 지금 suvisdev에게 직접 물어봐야 한다.

### 1-2. DB 계약 — 있음, 단 마이그레이션 없음은 시한부

테이블 정의는 [backend/app/models.py](../backend/app/models.py)가 ERD 문서([docs/00_overview/01-erd.md](00_overview/01-erd.md))를 그대로 옮긴 구조고, "어긋나면 문서가 기준"이 파일 첫 줄에 박혀 있다([models.py:1-4](../backend/app/models.py)). 체크 제약·유니크 제약까지 코드에 있어 계약으로 충분하다.

**마이그레이션 도구(스키마 변경 이력을 코드로 쌓아 DB를 단계적으로 바꿔주는 도구, 예: Alembic)는 의도적으로 없다.** 현재 정책은 "스키마가 굳기 전까지 `create_all`(서버 시작 시 테이블 일괄 생성)로 만들고, 바뀌면 DB를 지우고 다시 만든다" — [backend/app/db.py:3-5](../backend/app/db.py). 지금까지는 합리적 선택이다. 리스크는 두 가지:

- **이미 문서가 코드보다 앞서 있다.** ERD가 오늘 v1.1로 올라가 `deadline`·`public_token`·`reason` 컬럼이 추가됐는데([01-erd.md:3](00_overview/01-erd.md)) models.py에는 아직 없다. 반영하는 순간 각자 로컬 DB 리셋 1회가 필요하다 — **전원에게 공지가 필요한 변경**이다.
- **배포 후에는 이 정책이 성립하지 않는다.** EC2에 올라간 DB는 "지우고 다시"가 곧 데이터 손실이다. 더미 10만 건 재시드도 매번 몇 분씩 든다. **배포 시점(W2)이 Alembic 도입 여부를 결정할 마감**이고, 이 결정은 팀장 몫이다.

### 1-3. 로컬 실행 — README만으로는 못 띄운다

새 팀원이 README만 보고 백엔드를 띄우는 시나리오는 **실패한다.** 빠진 단계:

- **README가 낡았다.** [backend/README.md:3](../backend/README.md)은 "라우터·서비스는 아직 없다"인데 실제로는 라우터 10개가 돌아간다. 실행 명령 자체(`docker compose up` 또는 `uv run uvicorn app.main:app --reload`)가 어디에도 안 적혀 있다. docker-compose로 DB+API가 한 번에 뜨는데([docker-compose.yml:2-29](../docker-compose.yml)) README는 이를 언급하지 않는다.
- **`.env` 키 목록이 불완전하다.** [backend/.env.example](../backend/.env.example)에는 DB·JWT·AWS 6종뿐인데, 코드는 `ANTHROPIC_API_KEY`([summarizer.py:77](../backend/app/agent/summarizer.py))·`AGENT_CHAT_MODEL`([runtime.py:26](../backend/app/agent/runtime.py))·`AGENT_SUMMARY_MODEL`([summarizer.py:21](../backend/app/agent/summarizer.py))도 읽는다. 예시 파일에 없는 키는 새 팀원에게는 존재하지 않는 것과 같다.
- **시드 데이터(테스트용 더미 데이터) 안내가 없다.** `backend/scripts/seed_dummy.py`(공고 10개 + 지원서 10만 건 생성기)가 있지만 README 어디에도 실행법이 없다.
- **에이전트 기능은 의존성 자체가 빠져 있다** — 진단 2의 R2 참고. 새로 `uv sync` 한 환경에서는 설치조차 안 된다.
- 프론트는 아직 React 코드가 없어 "띄울 것"이 목업 HTML뿐이다(브라우저로 열면 됨). [frontend/README.md](../frontend/README.md)는 이 상태 기준으로는 정확하다.

### 1-4. 컨벤션 — 일관성 좋음, 사소한 어긋남 3개

구조는 비전공자가 따라 하기 좋은 편이다: 라우터는 `app/api/`에 파일 하나씩, 요청·응답 형태는 `app/schemas/`에, 에러 응답은 전역 핸들러로 한 형식 통일([main.py:72-151](../backend/app/main.py)), 새 라우터 추가 위치까지 주석으로 명시([main.py:154](../backend/app/main.py)). 파일마다 "왜 이렇게 했는지" 주석이 충실해서 모방 가능하다. 어긋남은:

- [evaluations.py:22-29](../backend/app/api/evaluations.py)만 응답 모델을 `schemas/`가 아닌 라우터 파일 안에 정의한다.
- HTTP 상태 코드 임포트가 두 방식 혼용이다 — `from http import HTTPStatus`([evaluations.py:2](../backend/app/api/evaluations.py)) vs `from fastapi import status as http`([postings.py:1](../backend/app/api/postings.py)).
- `require_recruiter` 의존성이 세 파일에 각각 재정의돼 있다([applications.py:28](../backend/app/api/applications.py), [postings.py:13](../backend/app/api/postings.py), [agent.py:22](../backend/app/api/agent.py)). `deps.py`로 모으면 한 곳이 된다.

### 1-5. 병목 — 반드시 팀장을 거치는 작업

| 병목 | 성격 |
|---|---|
| 스키마(01-erd.md) 변경 | **의도된 병목** (CLAUDE.md 규칙). 단, 변경 후 models.py 반영 + 전원 DB 리셋 공지까지가 한 세트인데 그 절차가 문서화 안 돼 있다 |
| 02-api.md·공용 문서 갱신 | 의도된 병목. **명세 공백(1-1)이 클수록 이 병목이 자주 발동한다** — 공백을 메우는 게 병목을 줄이는 가장 싼 방법 |
| AWS 콘솔 (S3·SES·SQS·EC2·IAM) | 팀장 계정 소유. 키는 `.env`로 woojeongalex에게 전달됐지만, 리소스 생성·권한 변경은 팀장뿐 |
| 배포 (EC2·Vercel) | 미착수 상태라 "실서버에서 확인"이 필요한 모든 검증이 팀장 대기열이다. W2에 풀림 |
| 에이전트 ↔ 백엔드 로직 중복 (진단 2 R1) | 숨은 병목. 단계 전환 규칙이 바뀔 때마다 두 도메인 오너가 서로 알려줘야 한다 |

---

## 진단 2 — 코드 리뷰

전체 소감 한 줄: 초기 단계치고 이례적으로 깨끗하다. SQL 인젝션(입력값으로 DB 명령을 조작하는 공격)은 전 구간 ORM 파라미터 바인딩이라 해당 없음, 시크릿 커밋 없음, 파일 업로드 검증([files.py:47-92](../backend/app/api/files.py))과 presigned URL(서버가 서명해준 임시 업로드/다운로드 링크) 설계는 공격 시나리오까지 주석으로 막아뒀다. 이하는 고칠 것.

### 잘못 만든 것 — 지금 고치지 않으면 비싸지는 순서

**S1 · 회원가입이 완전 공개다 (보안 · 배포 전 필수)**
[auth.py:14-34](../backend/app/api/auth.py) — `/auth/signup`은 인증 없이 호출 가능하고, 기본 역할이 `recruiter`다. recruiter는 전체 지원자의 이름·이메일·전화번호·자소서를 볼 수 있다. 로컬에서는 문제가 아니지만 **W2에 외부 URL로 배포되는 순간, 인터넷의 누구나 계정을 만들어 지원자 개인정보 전체를 열람할 수 있다.** "role 지정은 admin만"(02-api.md)은 지켜졌으나 가입 자체가 열려 있는 게 구멍이다. 배포 전에 가입을 admin 전용으로 잠그거나(초대 방식), 환경변수로 끄는 스위치를 달아야 한다.

**S2 · JWT 비밀키에 기본값이 있다 (보안 · 배포 전 필수)**
[security.py:9](../backend/app/security.py) — JWT(로그인 토큰)를 서명하는 비밀키가 환경변수에 없으면 `"dev-secret-change-me"`로 대체된다. 배포 서버에서 `JWT_SECRET` 설정을 깜빡하면, 이 문자열을 아는 누구나 **admin 토큰을 위조**할 수 있다. 실수 가능성이 아니라 실수했을 때의 피해가 문제다. 운영 환경에서는 미설정 시 서버가 아예 안 뜨게(기동 실패) 바꿔야 한다.

**R1 · 단계 변경 로직이 두 곳에 복제돼 있다 (설계 · 갈수록 비싸짐)**
단계 변경(검증→변경→이력→메일 큐 트랜잭션)이 [api/applications.py:108-170](../backend/app/api/applications.py)과 [agent/tools/write.py:28-80](../backend/app/agent/tools/write.py)에 거의 같은 코드로 두 벌 있다. 검색도 마찬가지 — [api/search.py](../backend/app/api/search.py)의 필터 로직이 [agent/tools/read.py:16-78](../backend/app/agent/tools/read.py)에 다시 구현돼 있고, read.py 쪽은 점수 정렬 시 필터를 수동으로 재적용하는 취약한 구조다. 규칙이 바뀌면 두 도메인(백엔드·에이전트)이 각자 고쳐야 하고, 한쪽만 고치면 **API와 에이전트가 조용히 다른 규칙으로 동작**한다. 공용 서비스 함수로 추출해 양쪽이 호출하는 구조로 바꿔야 하며, 미룰수록 복제본이 늘어난다.

**R2 · anthropic 패키지가 의존성 목록에 없다 (버그)**
[pyproject.toml:6-14](../backend/pyproject.toml)에 `anthropic`이 없고 `uv.lock`에도 없다. 에이전트 코드는 설치를 가정한다([runtime.py:68-71](../backend/app/agent/runtime.py), [summarizer.py:72-75](../backend/app/agent/summarizer.py)). 즉 지금 에이전트가 도는 건 **누군가의 로컬에 수동 설치돼 있기 때문**이고, 새로 `uv sync` 한 환경·Docker 이미지·배포 서버에서는 AI 요약과 채팅이 전부 조용히 실패한다. `uv add anthropic` 한 줄이면 끝난다.

**R3 · 에이전트 이메일 초안 도구에 접근 제어가 빠졌다 (보안 · 소)**
`/agent/confirm`은 로그인만 요구하는데([api/agent.py:124-128](../backend/app/api/agent.py)), 그 안에서 실행되는 `draft_email`은 역할·배정 확인 없이 지원자 이름·이메일을 반환한다([write.py:125-132](../backend/app/agent/tools/write.py)). 면접관이 **본인에게 배정되지 않은** 지원자의 연락처를 이 경로로 얻을 수 있다 — 다른 모든 경로가 지키는 A3 규칙(면접관은 배정된 지원자만)의 우회로다. `assert_can_view_application` 호출 한 줄로 막힌다. (`change_stage`·`assign_interviewer`는 자체 역할 검사가 있어 해당 없음 — [write.py:30-31, 85-86](../backend/app/agent/tools/write.py))

**R4 · Dockerfile이 운영 이미지에서 --reload로 뜬다 (소)**
[Dockerfile:16](../backend/Dockerfile) — `--reload`는 코드 변경 감지용 개발 옵션이다. EC2 배포 이미지에서는 파일 감시 오버헤드에 워커 재시작 불안정까지 얹는다. 배포용 CMD에서 빼면 된다.

### 아직 안 만든 것 — 잘못이 아니라 예정대로 비어 있는 것

혼동을 막기 위해 명시한다. 아래는 리뷰 지적이 아니다.

| 항목 | 상태 |
|---|---|
| 테스트 (`backend/tests/`) | 폴더 자체가 아직 없음 — J8, 백엔드 큐에 있음 |
| SQS 메일 발송 워커 (G2·G3) | [docker-compose.yml:31-36](../docker-compose.yml)에 주석으로 예약됨 — W3 |
| CI/CD (J4) | 인프라 W3 |
| 프론트 React 전체 | 목업 11장까지 완료, React는 W1~W2 몫 |
| ERD v1.1 컬럼 3개의 코드 반영 | 문서 먼저 확정된 상태 (1-2 참고) |
| 이력서 파일(S3) 텍스트 추출 → AI 요약 연결 | [summarizer.py:36-37](../backend/app/agent/summarizer.py)에 예정 주석 |

---

## 이번 주에 할 일 (우선순위순, 5개)

| # | 할 일 | 담당 | 예상 |
|---|---|---|---|
| 1 | **배포 전 보안 3종**: signup 잠금(S1) + JWT_SECRET 기동 실패(S2) + 에이전트 A3 한 줄(R3) | 백엔드 (+에이전트 R3) | 반나절 |
| 2 | **EC2 + Vercel 실배포** — 초기 버전(09/04) 게이트의 전제. 1번이 먼저 머지돼야 안전하다 | 인프라 (팀장) | 1~2일 |
| 3 | **React 뼈대 착수** — 라우팅·토큰·공통 컴포넌트. 09/04까지 전 화면 정적이 목표라 이번 주가 마지노선 | 프론트 | 2~3일 |
| 4 | **`uv add anthropic`(R2) + `.env.example`에 에이전트 키 3종 추가** | 에이전트 | 30분 |
| 5 | **backend README 현행화** — 실행 명령(docker compose / uvicorn)·시드 실행법·env 키 목록 | 백엔드 | 1시간 |

R1(로직 중복 해소)은 이번 주 항목에서 뺐다 — 배포·프론트가 임계경로인 주에 리팩터링을 끼우면 둘 다 늦는다. **W3 초에 백엔드+에이전트 오너가 같이 잡는 것을 권한다.**
