# 에이전트 도구 스펙 초안

> **상태**: 초안 (2026-08-24) · 오너 suvisdev · W2 M1  
> **원칙**: [ADR-0003](../../docs/03_decision/0003-ai-추천만.md) — AI는 추천까지, 확정은 사람.  
> **UI 진입**: [ADR-0009](../../docs/03_decision/0009-에이전트-UI-위치.md) (제안 중).  
> **API 목록**: [02-api.md](../../docs/00_overview/02-api.md) — 도구는 **기존 REST/서비스 레이어를 재사용**한다. 권한 우회 경로를 만들지 않는다.

## 1. 분류

| 종류 | 확인 단계 | 예시 |
|---|---|---|
| **읽기** | 없음 — 바로 실행·결과 표시 | 검색·상세·평가 목록·이력 |
| **쓰기** | **필수** — 실행 전 사용자 확인 | 단계 변경 · 메일 초안 “확정 대기” |
| **제외** | — | 최종 합불 자동 확정 · SES 실발송 · 스키마/권한 변경 |

쓰기 확인 카피 예: `김도현을 서류 검토로 옮길까요? [취소] [확인]`  
메일은 **초안 생성까지**가 도구 범위. 발송 버튼은 사람만 (G 워커·기존 UI).

## 2. 도구 목록 ↔ API 매핑

접두사 `/api/v1`. 에이전트 런타임은 HTTP 클라이언트 또는 동일 프로세스 서비스 호출.  
`# TODO(A1)` 자리가 있는 API는 호출 시 **현재 요청의 JWT를 그대로 전달** — 에이전트가 별도 슈퍼유저 토큰을 갖지 않는다.

### 읽기 도구

| 도구명 | 하는 일 | 매핑 (02-api) | 비고 |
|---|---|---|---|
| `search_applications` | 이름·이메일·단계 등으로 지원자 찾기 | `GET /postings/{id}/applications?q=&stage=` | H1·H2. **전역 검색** `GET /applications`는 02-api에 추가 예정(팀장) — 생기면 이 도구가 우선 사용 |
| `get_application` | 지원자 상세 | `GET /applications/{id}` | D4. `ai_summary` 포함(있으면) |
| `list_evaluations` | 평가 목록·평균 | `GET /applications/{id}/evaluations` | E2 (전환기 suvisdev) |
| `list_history` | 단계 이력 | `GET /applications/{id}/history` | D5 |
| `list_notes` | 담당자 메모 | `GET /applications/{id}/notes` | |
| `get_posting` | 공고 요건 조회(요약 대비용) | `GET /postings/{id}` | B |

### 쓰기 도구 (확인 필수)

| 도구명 | 하는 일 | 매핑 (02-api) | 확인 후 동작 |
|---|---|---|---|
| `change_stage` | 단계 변경 | `PATCH /applications/{id}/stage` | D3·D5·메일 큐 트리거. **확인 없이 호출 금지** (테스트로 강제 — W5) |
| `draft_stage_email` | 단계 안내 메일 **초안** 생성 | *(HTTP 없음 — LLM + G1 템플릿 문구)* | 초안을 UI에 앰버로 표시. `email_logs`/SES 호출은 사람이 발송할 때만 |

### 에이전트 전용 HTTP (제안 — 아직 02-api 미등재)

| 메서드 | 경로 | 기능 |
|---|---|---|
| POST | `/agent/run` | 자연어 한 문장 → 도구 계획·실행 로그 반환 (읽기 즉시 / 쓰기는 pending_confirmation) |
| POST | `/agent/confirm` | 대기 중 쓰기 도구 실행 확정 |
| POST | `/agent/extract` | 이력서·자소서 파일 → 구조화 필드 + 요약 제안 (W3; 저장은 별도 확정) |

등재는 구현 PR에서 `02-api.md`에 한 줄 추가 + **팀장 승인**.

## 3. 데모 문장 → 도구 분해

> “Python 2년 이상이고 AWS 경험 있는 사람 서류 합격 처리하고 안내 메일 초안 써줘”

| 단계 | 도구 | 종류 |
|---|---|---|
| 1 | `search_applications` (skills≈Python,AWS · exp≥2 · stage=applied) | 읽기 |
| 2 | (결과 0명이면 중단·안내) | — |
| 3 | `change_stage` → **확인 카드** → 확인 시 서류 검토(`screen`) | 쓰기 |
| 4 | `draft_stage_email` → 초안 표시 | 쓰기(초안) |

실행 로그는 UI(⌘K 콘솔, ADR-0009 안 A)에 그대로 노출 — 면접 스토리용.

## 4. 가드

1. **환각**: 응답·요약은 도구 결과·추출 텍스트만 인용. 없는 지원자 id를 만들어내지 않음.
2. **권한**: interviewer는 배정 건만 (A3). 403이면 도구 실패로 로그하고 중단.
3. **비용**: 더미 10만 건 루프에 LLM 호출 금지 ([agent.md](../../docs/01_role/agent.md) §3).
4. **쓰기 테스트**: “확인 콜백 없이 `change_stage`가 나가면 실패” 단위 테스트 (W5).

## 5. 구현 순서 (이 스펙 기준)

| 주차 | 범위 |
|---|---|
| W2 | 이 문서 확정 협의 · 추출 PoC · (전환기) E2 API |
| W3 | 추출→`ai_summary` 저장 훅 · 검수 UI |
| W4 | 읽기 도구만 `/agent/run` |
| W5 | 쓰기 도구 + 확인 · 메일 초안 |

## 6. 열린 질문 (팀·백엔드)

- [ ] 전역 검색 경로 공식화 시점 (H2 / 02-api)
- [ ] `change_stage` body 필드명 확정 후 이 표 갱신 (D3 구현 시)
- [ ] 메일 초안을 저장할지(임시 테이블) vs UI 세션만인지
