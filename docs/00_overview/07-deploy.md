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

## 재배포 (현재는 수동 — 팀장)

main 기준 `git archive` → scp → 서버에서 `docker compose -f docker-compose.prod.yml up -d --build`. **CI/CD(J4, main 머지 시 자동 배포)는 W3에 이 절차를 대체한다.** 그 전까지 "배포 서버에 반영해달라"는 팀 채널로.

## 1회성 DB 이행

스키마는 `create_all` 로 만들지만([db.py](../../backend/app/db.py)), **이미 데이터가 있는 DB** 는 값·제약을 바꿀 수단이 없다. 그런 변경은 `backend/scripts/` 에 SQL 파일로 두고 여기에 실행법을 적는다.

| 파일 | 언제 | 실행 |
|---|---|---|
| `migrate_roles_to_member.sql` | 역할 2종화 배포 시 1회 ([ADR-0017](../03_decision/0017-등급-이분화.md)) | `psql "$DATABASE_URL" -f backend/scripts/migrate_roles_to_member.sql` |

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
