# 인프라·총괄 로드맵

> 이 문서는 작성 시점의 설계·계획이다. 확장·개정은 도메인 오너가 한다([03-conventions](../00_overview/03-conventions.md) "결정 문서 개정").

> **오너**: ~~bestcow (팀장)~~ **공석 (2026-09-02 이탈) — AWS·GitHub 권한은 woojeongalex 가 쥐고 있다. 이 로드맵을 이어갈 사람은 팀이 정한다.** [ADR-0025](../03_decision/0025-운영-권한-이관.md) · [09-handover](../00_overview/09-handover.md) · **폴더**: `infra/` · `.github/` · `docker-compose.yml` · AWS 리소스 전부 · **상태**: 확정 v1.0 (2026-08-24, #16·#18 머지)
> 공통 규칙은 [04-team.md](../00_overview/04-team.md).

## 일정 · 운영 (전 도메인 공통)

- **초기 버전: 09/04(금) · 1차 완성: 09/30(수).** 초기 버전의 정의는 [00-overview.md](../00_overview/00-overview.md) 진행 순서 절 — 배포가 정의에 들어가므로 **초기 버전 게이트의 집행자는 이 도메인이다.** 주차 기준: W1 08/24~28 · W2 08/31~09/04 · W3 09/07~11 · W4 09/14~18 · W5 09/21~25 · 09/28~30 통합 버퍼.
- **주 단위로 스스로 계획하고 진행한다.** 각 오너의 주간 계획이 기본값이고, 도메인 간에 걸리는 변경만 [06-weekly.md](../00_overview/06-weekly.md)에서 맞춘다. 주 시작 시 각 오너는 [주간 계획 프롬프트](../00_overview/06-weekly.md#주간-계획-프롬프트--오너용)로 자기 계획을 갱신한다.
- ~~팀장 머지·검수·뒷처리 사이클~~ — 2026-08-28 개정으로 리뷰 게이트가 없어졌고([03-conventions](../00_overview/03-conventions.md)), 2026-09-02 부터 팀장도 없다. **게이트 판정(09/04·09/30)의 집행자는 미정.**

## 1. 미션

전원이 딛는 바닥. AWS·배포·CI/CD를 책임지고, **총괄로서 스키마·아키텍처·인터페이스 리뷰·통합·발표를 잡는다.** 이 도메인의 지연은 곧 다른 네 도메인의 대기다 — 큐의 우선순위가 곧 팀 전체의 임계경로다.

## 2. 범위

**포함**

- AWS: 계정·IAM 최소 권한·S3 버킷·SES 발신 도메인(샌드박스 해제)·SQS 큐·EC2 배포
- 로컬 실행 환경: Docker compose J1 (api·db·워커) — *suvisdev 큐에서 인수*
- CI/CD J4: GitHub Actions (pytest·프론트 빌드 → EC2 배포)
- GitHub 설정: 브랜치 보호·CODEOWNERS·리포 권한
- Vercel 프로젝트 연결 (빌드 설정은 프론트 오너와 협업)
- 공용 문서·스키마([01-erd.md](../00_overview/01-erd.md)) 관리 — 확정·변경 절차 집행

**총괄 (도메인 밖 상시 업무)**

- 인터페이스 PR 리뷰·머지 — **기본 금요일 주 1회 일괄, 필요시 주 2~3회.** 단 **다른 도메인이 대기 중인 선행 PR은 팀 채널 요청으로 수시 처리** — 이게 밀리면 받는 쪽이 일주일을 논다
- 주간 계획서(`docs/00_overview/06-weekly.md`) — 주 마감 게이트·팀장 트랙·충돌 방지만 다루고, **사람별 작업 큐는 각 로드맵으로 이관** ([W1-3](../00_overview/06-weekly.md))
- 도메인 간 조정 · B2 실측 판정 집행([W1-2 §8](../00_overview/06-weekly.md)) · 통합 리허설 · 발표 총괄

## 3. 인터페이스 계약

**제공** — `DATABASE_URL`·AWS 자격과 리소스명은 전부 `.env`(git 제외) + `.env.example`(키 이름만)로 전달. 리소스가 준비되면 `.env.example` 갱신 PR이 곧 공지다. **의존** — 없음 (그래서 전부 선행조건이 된다).

## 4. 주간 계획

| 주차 | 단계 | 내용 | 완료 기준 |
|---|---|---|---|
| **W1** (~08/28) | **M1 선행조건 풀기** | **오늘: AWS 계정·S3·SES 발신 도메인 신청** (SES 리드타임) · [J0](../02_tasks/J0-앱-뼈대.md) 머지 ✅ · E1 목업 머지 ✅ → **ERD 확정** · 스키마 합의 2건 결정(`deadline`·`public_token` / `reason`) · [02-api.md](../00_overview/02-api.md)에 전역 검색 `GET /api/v1/applications` 추가 · [J1 Docker compose](../02_tasks/J1-docker-compose.md) · GitHub 브랜치 보호+CODEOWNERS 갱신 · `mockup.html` 색 리터럴 정리(금요일, [W1-2 별건](../00_overview/06-weekly.md)) | 01-erd 상단이 "확정 vX.X · 날짜". `docker compose up` 한 줄 기동. 백엔드 큐의 "ERD·J0 선행"이 전부 해소됨 |
| **W2** (~09/04) | **M2 실배포 1차** — 🚩초기 버전 | IAM 최소 권한 정리 · SQS 큐 생성 · SES 샌드박스 해제 확인 · EC2에 api+워커 수동 배포 · Vercel 연결 · `.env.example` 체계 확정 · **금요일(09/04) 초기 버전 게이트 판정** | 외부 URL에서 `/health` 200. 프론트 프리뷰가 실 API를 바라봄. **[00-overview](../00_overview/00-overview.md) 초기 버전 정의 4항목 전부 충족 판정** |
| **W3** (~09/11) | **M3 CI/CD** ✅ → **운영 안정화** | ~~GitHub Actions CI + 자동 CD~~ **09/04 완료**(systemd 2분 폴링). 09/07: 배포에 alembic·prune 추가 · DB 백업 · 로그 상한 · CloudWatch 경보 · 상태 스크립트 · t3.medium · 앵커 체인 Sepolia 전환 · secret 6개. 남은 것: Discord 웹후크 재연결 · AWS Budgets 알림 · 배포 스크립트 저장소 회수 | push → 테스트 → 배포가 사람 손 없이 돈다 ✅. 서버가 죽거나 디스크가 차거나 백업이 빠지면 **메일이 온다** ✅ |
| **W4** (~09/18) | 중간 통합 점검 | QA 시나리오로 1차 통합 점검(전 도메인 가로질러) · 막힌 도메인 식별·조정 · 모니터링·로그 경로 정리 | 중간 점검 결과가 06-weekly에 기록되고, W5 계획에 반영됨 |
| **W5** (~09/25) | **M4 통합·리허설** | 통합 리허설(QA 시나리오 전 항목) · 데모 환경 동결 · 발표용 역할표 최종 확정 | 데모 시나리오가 프로덕션 URL·실 기기에서 끊김 없이 돈다. 리허설 2회 |
| 09/28~30 | 1차 완성 판정 | 잔여 버그 뒷처리 · 발표 자료 총괄 착수 | **09/30 1차 완성 선언** — 필수 기능 전부 프로덕션에서 동작 |

## 5. 작업 큐 — 위에서부터 순서대로

| # | 작업 | 비고 |
|---|---|---|
| 1 | ~~AWS 계정 · S3 · SES 신청~~ ✅ | 완료 — SES는 샌드박스 해제 승인 대기 (07-deploy) |
| 2 | ~~J0 리뷰·머지~~ ✅ | [PR #11](https://github.com/Team-Seuk/Arda/pull/11) 머지 |
| 3 | ~~E1·A2·QA 등 리뷰·머지 → ERD 확정~~ ✅ | v1.0 확정 (08/24, #20) |
| 4 | ~~스키마 합의 2건 + 02-api 전역 검색 경로~~ ✅ | |
| 5 | ~~도메인 오너제 전환 PR~~ ✅ | [ADR-0007](../03_decision/0007-도메인-오너제-전환.md) |
| 6 | ~~GitHub 브랜치 보호 + CODEOWNERS~~ ✅ | |
| 7 | ~~J1 Docker compose~~ ✅ | [#27](https://github.com/Team-Seuk/Arda/pull/27) |
| 8 | ~~mockup.html 색 리터럴 정리~~ ✅ | |
| 9 | ~~M2 실배포 1차~~ ✅ (08/27 — [07-deploy](../00_overview/07-deploy.md) 신설) | ~~SES 재신청 결과 확인~~ **09/01 프로덕션 승인**(50,000통/일 — 팀원 메일 검증도 이제 불필요) · **초기 버전 게이트 판정(09/04 금)** |
| 10 | 운영 계정 정비 ✅ (08/28) | admin 리셋 + 전 팀원 admin 발급 (07-deploy 계정 절) |
| 11 | ~~M3 CI/CD (J4)~~ ✅ (09/04 CI + 자동 CD, 09/07 alembic·prune 단계) | 절차는 [07-deploy](../00_overview/07-deploy.md) "재배포 — 자동" 절. **[ADR-0024 §13](../03_decision/0024-sLLM-로컬-모델-전략.md) 의 "두 타깃 빌드"(SaaS 판 + 온프레미스 판)는 12~15 로 분리** |
| 11a | ~~운영 안정화 묶음~~ ✅ (09/07) | DB 매일 S3 백업(`infra/backup-arda-db.sh`) · 컨테이너 로그 상한 · 배포마다 이미지·빌드 캐시 prune(디스크 76→45%) · CloudWatch 경보 3개 + SNS(`infra/push-metrics.sh`, `infra/cloudwatch-alarms.yml`) · `infra/server-status.sh` · t3.small→t3.medium |
| 11b | ~~앵커 게시 자동화~~ ✅ (09/07) | Amoy faucet 전멸 → Sepolia 전환(PR #29) · Actions secret 6개 · 봇 admin 계정 · 첫 거래 [Etherscan](https://sepolia.etherscan.io/tx/0xf3e19e5a8de49c1398f6d8b2dc5be4f8b58724c59518c0f60cb90f88fbe6c0c0) · 매일 09:10 자동 |
| 11c | Discord `#github` 웹후크 재등록 | 저장소 이관 때 끊김. 서버 소유자(woojeongalex) 권한 필요 — 요청 중 |
| 11d | AWS Budgets 알림 (월 $150, 85%) · 서버 `deploy-arda.sh` 를 `infra/` 로 회수 | 예산 $400·10/27 안에서 GPU 켜고 끄기. 스크립트는 서버에만 있어 저장소에 사본이 없다 |
| 12 | 온프레미스 판 — 프론트 서빙 | ~~W3~~ **일정 재조정(09/07): W4 중간 점검에서 발표 전 착수 여부 결정** — W3 는 운영 안정화에 썼다. Vercel 대신 FastAPI `StaticFiles` 또는 nginx. **덤: 같은 출처가 되어 CORS 가 필요 없어진다.** ~1시간 |
| 13 | **[ADR-0031] 메일 SMTP 전환** — n8n + SMTP 시연 경로 확정(09-08) · 워커는 SMTP 20줄 비상 폴백 | W3~W4. `mail.py` 의 SES 는 리허설 통과 뒤 삭제. **정상 흐름은 n8n → SMTP 로만** — 워커 안 지남. 반나절 |
| 14 | **[ADR-0031] 큐 스위치** — SQS → Redis 또는 Postgres LISTEN/NOTIFY (`QUEUE_BACKEND=sqs\|redis\|pg`) | W4 초. `create_log`/`publish` 분리(08/31)로 교체 지점이 이미 좁다. 우정님 판단 |
| 15 | `docker-compose.onprem.yml` + 한 번 실제로 띄우기 | W3. 12~14 뒤. **띄워 봐야 "AWS 없이 돈다"가 주장이 아니라 사실이 된다** |
| 17 | **n8n 컨테이너 (ADR-0030 1단계)** — 09/07 PR | compose `n8n` + Caddy `/n8n/*` Basic Auth(**팀 전원 공유**, 09/07 팀장 결정) + 볼륨 백업·`N8nHealthy` 지표·알람 + 워크플로 초안 `infra/n8n/stage-changed.json`. 서버 설치 절차는 [07-deploy "n8n"](../00_overview/07-deploy.md). **실발송 검증은 백엔드 내부 API 2개·`MAIL_DISPATCH` 스위치 뒤** — 그때까지 메일은 워커. 13·14(SMTP·DB 폴링)는 n8n 이 실패하면 돌아올 길로 남긴다 |
| 18 | **[ADR-0031] 관측 self-host** — `push-metrics.sh` 를 CloudWatch put-metric-data 대신 `~/metrics.log` append + 임계 넘으면 SMTP send (또는 Discord). CloudFormation 스택 폐기 준비 | W4 초. 관측 지표 축적은 로그 파일이면 충분(주 1회 훑는 용도) |
| 19 | **[ADR-0031] AWS 콘솔 폐기 대상 5종** — SQS 큐 · CloudWatch 지표·알람 · SNS 토픽·구독 · CloudFormation 스택 `arda-alarms` · IAM `arda-metrics-write` 정책 | 2026-10-27 이후, 대체 경로 리허설 2회 통과 뒤. 콘솔 작업 (사용자 몫) |
| 20 | **[ADR-0031] S3 → MinIO 로컬 실측** — compose 로 MinIO 컨테이너 띄우고 `S3_ENDPOINT_URL` 만 갈아 끼워 이력서 업로드·조회 1회 | W5 초. 코드 변경 0. "AWS 없이도 돈다" 마지막 조각 |
| 16 | GPU 서버 (g4dn.xlarge, 켜고 끄기) | **상시 아님.** 예산 $400·10/27 이라 24시간(월 ≈$470) 불가, 8h×20일 ≈$105. 로컬 STT·qwen 시연 때만. 쿼터 승인 대기. 거짓말 탐지는 CPU 라 여기 안 올린다(t3.medium 으로 해결). 운영 에이전트는 Anthropic Haiku 유지 |

## 6. 리스크

- **예산 $400 · 2026-10-27 까지** (2026-09-07 확인). 고정분 월 ≈$20. GPU 는 켜고 끄기 전제. AWS Budgets 알림으로 감시.
- **개인 결제 키 두 개** — Anthropic(에이전트)·OpenAI(STT) 모두 수택 개인 계정. 인계·만료(Anthropic 10/27) 때 교체 절차 필요. 서버 `.env` 에만 있다.
- **옛 도메인 `seuk.cloud`·`arda.seuk.cloud`** 는 이탈한 전 팀장 명의 — 저장소 기본값은 09/07 에 전부 새 주소로 맞췄지만, 팀원 북마크·앱 구버전이 옛 주소를 보면 어느 날 멈춘다.
- **한 대짜리 서버** — 백업·경보로 "모르게 죽는 것" 은 막았지만 복구는 여전히 사람 손(복원 리허설 W4).
- **팀장 병목의 재생산.** 오너제의 목적이 이것을 없애는 거다 — 금요일 사이클에 인터페이스 PR이 몰리면 의존 작업이 최대 1주 대기한다. 팀원은 목요일까지 올리고, 다른 도메인을 대기시키는 PR은 수시 검수를 요청한다. 그래도 밀리면 그 주 06-weekly에 원인을 적는다.
- **SES 샌드박스 해제 거절(08/27)** → 데모·E2E는 검증된 수신자(팀원 메일 등록)로 진행 — 1차 완성 범위엔 지장 없음. 재신청 시 트랜잭션 전용·저볼륨·바운스 처리를 구체화해 제출.
- **ERD 확정이 늦으면 전 도메인 대기** → E1 머지 직후 확정 (W1-2 §3의 앞당김 결정 유지).

## 7. 면접 스토리

- 배포 파이프라인 — main 머지가 곧 배포(2분 폴링) + alembic 을 배포에 넣기까지의 사고 두 번(컬럼 누락 500, 디스크 고갈)
- **서명 개인키를 서버 밖(GitHub Actions)으로 뺀 결정** ([ADR-0028](../03_decision/0028-제출물-무결성-앵커.md) Q2·Q3) — 서버 셸 접근 ≠ 서명 권한
- 테스트넷 faucet 생태계가 봇 방지로 닫힌 현실에 어떻게 대응했나 (Amoy → Sepolia, 코드는 체인 독립)
- 한 대짜리 서버를 "모르게 죽지 않게" 만든 것 — 백업(서버는 쓰기만)·CloudWatch 경보·비용 0
- 권한 모델 — IAM 최소 권한(`arda-server` 는 버킷 쓰기만, 지표 전송만)과 앱 역할을 어떻게 나눴는가
- 5인 팀의 **리뷰 병목을 어떻게 구조로 풀었는가** (도메인 오너제 — 조직 설계도 아키텍처다)
