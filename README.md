# Arda — 채용 지원 관리 시스템

# (Applicant Tracking System(ATS))

Seuk의 팀 프로젝트입니다.

- 스택:
  FastAPI
  PostgreSQL
  React (Vite · TS)
  AWS (S3 · SES · SQS)
  Docker
  Vercel

- **메인 화면**: 지원자 칸반 보드 — 카드를 드래그해 단계 이동, 이동 시 지원자에게 메일 자동 발송

## 문서

| 문서                                             | 내용                                                              |
| ------------------------------------------------ | ----------------------------------------------------------------- |
| [docs/00-overview.md](docs/00-overview.md)       | 프로젝트 개요 · 범위 · 스택                                       |
| [docs/01-erd.md](docs/01-erd.md)                 | 테이블 정의서 (초안 — **UI 완성 후 확정, 이후 변경은 전원 합의**) |
| [docs/02-api.md](docs/02-api.md)                 | API 엔드포인트 목록                                               |
| [docs/03-conventions.md](docs/03-conventions.md) | 브랜치 · 커밋 · PR · 이슈 규칙                                    |
| [docs/04-team.md](docs/04-team.md)               | 역할 분배 · 담당 모듈                                             |
| [docs/05-design.md](docs/05-design.md)           | 디자인 규칙 (토큰 · 타이포 · 상태 · 작업 절차)                    |
| [docs/adr/](docs/adr/)                           | 기술 결정 기록 (왜 안 썼는가 포함)                                |
| [docs/tasks/](docs/tasks/)                       | 작업 지시서 (기능 번호 단위)                                      |
| [docs/planning/](docs/planning/)                 | 원본 기획 문서 · 동작 프로토타입                                  |

## 구조

```
backend/    FastAPI 서버
frontend/   React 앱 (Vercel 배포)
infra/      Docker · AWS · CI/CD
docs/       위 문서 전부
```

## 시작하기

작업 전에 [CLAUDE.md](CLAUDE.md)(작업 규칙)와 자기 담당 [docs/tasks/](docs/tasks/) 지시서를 먼저 읽는다.
기능은 번호로 부른다 (예: D3 = 드래그로 단계 이동) — 전체 목록은 [docs/planning/00_summary_ko.md](docs/planning/00_summary_ko.md) 6장.
