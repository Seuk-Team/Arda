# infra/n8n — 알림·메일 자동화 워크플로 (ADR-0030)

> 결정·배경은 [ADR-0030](../../docs/03_decision/0030-n8n-알림-자동화-분리.md), 서버 설치·시크릿·백업·경보는 [07-deploy "n8n"](../../docs/00_overview/07-deploy.md) 절. 이 폴더는 **워크플로 JSON 의 진실**이다 — n8n 화면에서 고쳤으면 export 해서 여기 커밋한다.

## 파일

| 파일 | 뜻 | 상태 |
|---|---|---|
| `stage-changed.json` | 단계 변경 → 렌더링 조회 → **SMTP** 발송 → 결과 기록(sent/failed). ADR-0031 시연 경로 | **초안** — 백엔드 내부 경로 2개(우정 몫)가 생기면 import 후 실측, export 로 덮어쓴다 |

## 흐름 (워크플로 1개)

```
api: stage_service.publish_all (MAIL_DISPATCH=n8n)
  → POST http://n8n:5678/n8n/webhook/stage-changed   { email_log_id }
  → GET  /internal/email-logs/{id}/render            (X-Service-Token)  ← 우리 API 가 제목·본문·수신자
  → SMTP 발송 (재시도 3회 · 5초, ADR-0031)             ← 공급자 바꾸려면 이 노드의 자격 증명만 바꿈
  → POST /internal/email-logs/{id}/result            { status, provider_message_id | error }
```

- 템플릿·설정값·`email_logs` 는 계속 우리 쪽이다. n8n 은 본문을 만들지 않는다.
- 웹훅은 docker 네트워크 안에서 부른다 — Caddy 의 Basic Auth 를 안 거친다. 밖에서 `https://api…/n8n/webhook/...` 로 부르면 Basic Auth 에 막힌다(의도한 것).

## 편집 규칙 — 팀 전원

- 편집 화면 `https://api.seuk.suvisdev.cloud/n8n/`, Basic Auth 계정은 **팀 공유**(2026-09-07 결정: 누가 빠져도 나머지가 진행). 비밀번호는 팀 채널 고정 메시지, 저장소엔 없다.
- n8n 첫 접속 때 "owner 계정" 을 만들라고 한다 — 이것도 팀 공유 계정 하나로 만들고 같은 곳에 적는다.
- 화면에서 고친 뒤 **반드시** 워크플로 메뉴 → Download(export) → 이 폴더에 덮어쓰고 PR. export 안 한 변경은 n8n 볼륨 백업에만 남는다.
- 자격 증명(AWS 키 등)은 export 에 안 들어간다 — n8n 의 Credentials 화면에서 만들고, 어떤 이름으로 만들었는지 여기 표에 적는다.

| 자격 증명 이름 | 종류 | 권한 |
|---|---|---|
| `SMTP 발송` | SMTP | 발송 계정(host·port·user·password·secure). 지메일이면 `smtp.gmail.com:587` + 앱 비밀번호, 학원 도메인이면 학원 관리자 값. **자격 증명은 `n8n_data` 볼륨에 `N8N_ENCRYPTION_KEY` 로 암호화 저장 — 이 키 잃으면 백업 복원해도 못 푼다.** |
| ~~`arda-server (SES 발송만)`~~ | ~~AWS~~ | ~~SES 는 ADR-0031 리허설 통과 뒤 워커에서 삭제. 이 자격 증명도 그때 제거.~~ |

## 워크플로 안에서 쓰는 환경변수 (compose 가 넣는다)

| 이름 | 값 | 어디서 |
|---|---|---|
| `ARDA_INTERNAL_URL` | `http://api:8000` | compose 고정 |
| `ARDA_SERVICE_TOKEN` | 내부 API 서비스 토큰 | 서버 `~/arda/.env` — 백엔드가 정하면 채운다 |

## 로컬에서 띄우기 (2단계 준비)

SMTP 계정 값만 로컬용으로 갈아 끼우면 같은 워크플로가 로컬에서도 돈다 — "AWS 없이 돈다" 실증(ADR-0031 일정 W5 초). SMTP 계정 결정은 ADR-0031 "정하지 못한 것 1" — 2026-09-08 오늘 결정.
