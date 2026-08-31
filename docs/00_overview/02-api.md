# 02. API 엔드포인트 목록

> **상태: 초안.** 필수 기능 기준 목록. 요청/응답 상세는 구현하면서 Swagger(`/docs`)가 진실이 된다 — 이 문서는 "무엇이 있는가"만 유지한다.

- 접두사: `/api/v1`
- 인증: JWT Bearer. **공개**로 표시된 것 외에는 전부 로그인 필요.
- 권한: `admin` > `recruiter` > `interviewer`. interviewer는 본인 배정 지원서만 조회 가능(A3).

## 인증 (A)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /auth/signup | 회원가입 | A1. 가입 시 role 지정은 admin만 |
| POST | /auth/login | 로그인 → JWT 발급 | A1 |
| GET | /auth/me | 내 정보·권한 조회 | A2 |

## 채용 공고 (B)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /postings | 공고 목록 (+ 지원자 수) | B1·B3 |
| POST | /postings | 공고 생성 | B1, recruiter+ |
| GET | /postings/{id} | 공고 상세 | |
| PATCH | /postings/{id} | 수정 · 상태 변경(draft/open/closed) · 마감일 | B1·B2·B4, recruiter+ (#59, 팀장 승인). `deadline`(date, null 허용) — 과거 날짜는 422 |
| DELETE | /postings/{id} | 삭제 | B1, recruiter+ (#59, 팀장 승인) |
| POST | /postings/{id}/public-link | 공개 지원 링크 토큰 발급·재발급 | B6, recruiter+. 재발급하면 이전 토큰 즉시 무효 |

- **마감일 자동 마감(B4)**: 별도 스케줄러가 없다. 공고를 **조회하는 시점**에 `deadline < 오늘` 이고 `status="open"` 이면 `closed` 로 바꿔 저장한다. 목록·상세·공개 조회·지원 제출이 모두 그 지점이다.
- 공고 응답에는 `deadline` 과 계산값 `d_day`(남은 일수, 마감일 없으면 `null`)가 포함된다. 화면이 `D-12` 로 표시한다.

## 지원 — 공개 (C)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /public/postings/{id} | 지원 폼용 공고 정보 | **공개**. 마감된 공고는 **410 Gone** (B4) |
| GET | /public/postings/by-token/{token} | 공개 링크 토큰으로 공고 조회 | **공개**, B6. 마감은 410, 없는 토큰·미공개는 404 |
| POST | /public/postings/{id}/applications | 지원서 제출 | **공개**, C1·C3. 중복 지원 409 (C6). 마감된 공고는 **410** (B4). 본문에 `files[]`(presign 으로 받은 `s3_key`·`filename`·`size_bytes`·`content_type`·`kind`)를 함께 보내면 그때 `files` 행이 생긴다 — presign 시점에는 지원서가 없어 만들 수 없다 (F1 → C2) |
| POST | /public/files/presign-upload | 이력서 업로드용 presigned URL 발급 | **공개**, F1. 확장자·용량 검증(F3) |

## 지원자 관리 (D·H)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /applications | 전 공고 통합 검색 | H1. **공고를 가로지르는** 지원자 검색 — [H1 통합검색 화면](../02_tasks/H1-지원자-통합검색-화면.md)의 데이터 소스. 쿼리는 아래 공고별 목록과 동일 + `posting_id`(선택) · `sort`(`created_at`·`score`) · `order`(`desc`·`asc`) · `limit`(≤200) · `cursor`(커서 페이지네이션, H4 — 당분간 `offset`도 허용) · `with_total`(기본 `true`. `false` 면 응답의 `total` 이 `null` 이고 검색이 크게 빨라진다 — H5, 커서로 넘기는 화면 권장) |
| GET | /postings/{id}/applications | 지원자 목록 | D1. 쿼리: `q`(이름/이메일 검색, H1) · `stage`(H2) · 페이지네이션 |

- **검색 범위 = 이름·이메일 확정.** 자소서 본문·메모 전문 검색은 H 복합 필터 튜닝 완료 후 여유가 있을 때만 `pg_trgm` GIN 인덱스로 확장한다. 스키마 변경이 아니라 인덱스+쿼리 추가라 미루는 비용이 없다. (한국어는 Postgres 기본 FTS로 형태소 분석이 안 되고, 자소서 5천 자 × 10만 건이면 인덱스 용량·쓰기 비용이 커진다)
| POST | /postings/{id}/applications | 담당자 직접 등록 | D6, recruiter+ |
| GET | /applications/{id} | 지원자 상세 | D4 |
| PATCH | /applications/{id}/stage | 단계 변경 | D3, recruiter+. 이력 기록(D5) + 메일 큐 발행(G1) 트리거. `reason`(선택) — **`to_stage="rejected"` 인데 없으면 422** (D8) |
| POST | /applications/bulk-stage | 여러 명 단계 일괄 변경 | D9, recruiter+. 본문 `{application_ids, to_stage, reason?}`. 한 번에 **200명**까지(넘으면 422) |
| GET | /applications/{id}/history | 단계 이력 | D5. 응답에 `reason` 포함 (D8) |

- **일괄 변경은 전부 성공하거나 전부 실패한다 (D9).** 한 건이라도 전환 규칙에 걸리거나 없는 id 가 섞이면 **전체 롤백 + 409**, 응답 `message` 에 `failed`·`not_found` id 목록이 담긴다. 30명만 바뀌고 끝나면 담당자가 무엇이 됐는지 알 수 없다.
- 이미 그 단계인 건은 실패가 아니라 `skipped` 로 분류하고 건너뛴다. 성공 응답은 `{changed, changed_ids, skipped, mail_queued}`.
- **메일은 건별로 큐에 넣는다** — 지원자마다 이름·공고가 다르므로 한 통으로 묶을 수 없다.

## 평가 (E)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /applications/{id}/evaluations | 평가 작성 (점수+코멘트) | E1 |
| GET | /applications/{id}/evaluations | 평가 목록 + 평균 | E2 |
| PATCH | /evaluations/{id} | 평가 수정 | 본인 평가만 (A1 연결 후 강제). score·comment 부분 수정 허용. 08/25 검수에서 #50 구현을 계약에 반영(팀장 승인) |

## 면접관 배정 (E3)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /applications/{id}/interviewers | 면접관 배정 | E3, **admin만** ([ADR-0013](../03_decision/0013-면접관-배정-정책.md)). 중복 배정은 무시(멱등) |
| GET | /applications/{id}/interviewers | 배정된 면접관 목록 | 그 지원자를 볼 수 있는 사람만 (A3) |
| DELETE | /applications/{id}/interviewers/{user_id} | 배정 해제 | admin만 (ADR-0013) |
| GET | /interviewers/{user_id}/applications | 배정받은 지원자 목록 | 본인 또는 recruiter+ |

## 면접 일정 (S)

> [ADR-0016](../03_decision/0016-면접-일정-자동화.md) · ERD v1.2. **구현 완료 (2026-08-31)** — 배포 서버에서 E2E(가용 시간→배정→제안→공개 조회→확정→메일 렌더) 통과.

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /interviewers/{user_id}/availability | 가용 시간 등록 | 본인 또는 admin |
| GET | /interviewers/{user_id}/availability | 가용 시간 목록 | 본인 또는 recruiter+ |
| DELETE | /availability/{id} | 가용 시간 삭제 | 본인 또는 admin. 이미 나간 제안의 슬롯은 스냅샷이라 영향 없음 |
| POST | /applications/{id}/schedule-proposals | 일정 제안 생성 | recruiter+. 배정 면접관(E3) 가용 시간에서 후보 슬롯 생성 + 제안 메일 큐 발행 |
| GET | /schedules | 확정 면접 목록 | 면접 일정 화면. 쿼리 `from`·`to`·`mine`. **면접관 계정은 `mine` 과 무관하게 본인 건만** (A3 — 남의 일정에 배정 안 된 지원자 이름이 실린다) |
| GET | /applications/{id}/schedule-proposals | 최신 제안 상태 | A3 조회 규칙(배정 면접관도 가능). 대시보드·상세 패널 칩 용도. 제안 없으면 404 |
| GET | /public/schedule/{token} | 지원자용 일정·전형 현황 조회 | **공개**. 만료된 제안은 조회 시점에 `expired` 판정(B4 방식). 없는 토큰 404 |
| POST | /public/schedule/{token}/confirm | 슬롯 선택 → 확정 | **공개**. 본문 `{slot_id}`. 이미 확정·만료·취소면 409. 확정 시 통보 메일 큐 발행 |

## 메모 (담당자 서술형 — 기능 번호 미지정)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /applications/{id}/notes | 메모 목록 | 최신순. 작성자 이름·시각 포함 |
| POST | /applications/{id}/notes | 메모 작성 | 작성자 = 토큰의 사용자 |
| PATCH | /notes/{id} | 메모 수정 | 작성자 본인만(403). `If-Unmodified-Since` 또는 본문 `updated_at`으로 덮어쓰기 감지 → 409 ([ADR-0005](../03_decision/0005-실시간-공동편집-제외.md)) |
| DELETE | /notes/{id} | 메모 삭제 | 작성자 본인만(403) |

- 평가(E)와 별도 엔드포인트다. 메모는 점수가 없고, 지원자당 여러 사람이 각자 행을 쌓는다.

## 파일 (F)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /files/{id}/presign-download | 다운로드용 presigned URL | F2 |

## 에이전트 (M)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /agent/applications/{id}/summarize | AI 요약 재생성 | M2, recruiter+. 기존 요약을 덮어쓴다 |
| POST | /agent/chat | 에이전트 채팅 (검색·조회) | M3, recruiter+. 읽기 도구로 지원자 검색·조회, 쓰기 도구는 pending_action으로 반환 |
| POST | /agent/confirm | 쓰기 도구 확인 실행 | M4, 로그인 필요. 사용자가 확인 카드를 승인한 뒤 호출 |

## 시스템 (J)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /health | 헬스체크 | 배포·모니터링용 |
| GET | /docs | Swagger UI | J3, FastAPI 자동 |

## 백그라운드 (HTTP 아님)

- **메일 워커** (G2·G3): SQS 폴링 → SES 발송 → `email_logs.status` 갱신, 실패 시 재시도
