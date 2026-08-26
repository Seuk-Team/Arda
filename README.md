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
| [docs/00_overview/](docs/00_overview)            | 핵심 공용 문서 — 개요 `00` · ERD `01` · API `02` · 협업 규칙 `03` · 팀 `04` · 디자인 `05` · 주차별 계획 `06` |
| [docs/01_role/](docs/01_role)                    | **도메인별 로드맵 — 각자 자기 것부터 읽는다** (범위·마일스톤·작업 큐) |
| [docs/02_tasks/](docs/02_tasks)                  | 작업 지시서 (기능 번호 단위)                                      |
| [docs/03_decision/](docs/03_decision)                      | 기술 결정 기록 (왜 안 썼는가 포함)                                |
| [docs/04_planning/](docs/04_planning)            | 원본 기획 문서 · 동작 프로토타입                                  |

## 구조

```
backend/    FastAPI 서버 (backend/app/agent/ 는 에이전트 도메인)
frontend/   React 앱 (Vercel 배포)
mobile/     모바일 앱 (Flutter · Android — 예정)
infra/      Docker · AWS · CI/CD
docs/       위 문서 전부
```

## 시작하기

작업 전에 [CLAUDE.md](CLAUDE.md)(작업 규칙)와 **자기 도메인의 [docs/01_role/](docs/01_role) 로드맵**을 먼저 읽는다. 도메인·오너는 [docs/00_overview/04-team.md](docs/00_overview/04-team.md).
기능은 번호로 부른다 (예: D3 = 드래그로 단계 이동) — 전체 목록은 [docs/04_planning/00_summary_ko.md](docs/04_planning/00_summary_ko.md) 6장.
