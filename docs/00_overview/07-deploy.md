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

**운영 서버는 회원가입이 잠겨 있다** (`APP_ENV=production` — 공개 signup 차단, #117). 배포 URL로 로그인이 필요하면 **팀 채널에서 팀장에게 계정 생성을 요청**한다 (admin이 만들어준다). 로컬 개발은 기존처럼 자유 가입.

## 구성 (요약)

```
브라우저 ── https ──> Vercel (frontend/app, main 자동 배포)
브라우저/앱 ── https ──> Caddy(443, 인증서 자동) ──> FastAPI api:8000   ┐
                                                     PostgreSQL db      ├ EC2 (docker compose)
                                                     SQS 워커 worker    ┘
파일: 브라우저 ── presigned URL ──> S3 (서버 미경유)
메일: api → SQS 큐 → worker → SES (샌드박스 — 프로덕션 승인 대기 중)
```

- EC2: 서울, t3.micro + 스왑 2G, 고정 IP(Elastic IP). SSH는 팀장 PC에서만 열려 있다.
- 컨테이너 4개(db·api·worker·caddy) 전부 `restart: unless-stopped` — 재부팅 자동 복구.
- 서버 compose는 `docker-compose.prod.yml`(로컬 개발용 루트 compose와 별개 — --reload 없음, DB 포트 비공개).

## 재배포 (현재는 수동 — 팀장)

main 기준 `git archive` → scp → 서버에서 `docker compose -f docker-compose.prod.yml up -d --build`. **CI/CD(J4, main 머지 시 자동 배포)는 W3에 이 절차를 대체한다.** 그 전까지 "배포 서버에 반영해달라"는 팀 채널로.

## 도메인별로 달라진 것 (08/27)

| 도메인 | 달라진 것 |
|---|---|
| 프론트 | Vercel 자동 배포 연결 완료 — 머지하면 바로 URL에 뜬다. 수직 슬라이스(게이트 마지막 조건)는 지원 폼 화면 대기 중 |
| 앱 | 실 API 베이스 주소 확보 — W3 연동 때 위 주소 사용 |
| 에이전트 | ANTHROPIC_API_KEY 서버 주입·실호출 검증 완료 — 배포 URL 기준 E2E 데모 가능. AI 요약이 운영에서 실동작 |
| 백엔드 | 코어 API 전부 배포 Swagger에서 동작. 워커 SQS 대기 중 — 실발송 E2E는 수직 슬라이스 때. Dockerfile에 `scripts/` COPY 누락(이슈, create_admin 우회 실행 중) |

## 주의

- 시크릿(SSH 키·admin 비밀번호·API 키)은 이 문서에 없다 — 필요하면 팀장에게.
- SES는 아직 샌드박스(승인 대기) — 메일 실발송 테스트는 검증된 수신자(팀원 메일 등록)로만 가능.
