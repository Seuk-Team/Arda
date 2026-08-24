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
| PATCH | /postings/{id} | 수정 · 상태 변경(draft/open/closed) | B1·B2 |
| DELETE | /postings/{id} | 삭제 | B1 |

## 지원 — 공개 (C)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /public/postings/{id} | 지원 폼용 공고 정보 | **공개** |
| POST | /public/postings/{id}/applications | 지원서 제출 | **공개**, C1·C3. 중복 지원 409 (C6) |
| POST | /public/files/presign-upload | 이력서 업로드용 presigned URL 발급 | **공개**, F1. 확장자·용량 검증(F3) |

## 지원자 관리 (D·H)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /applications | 전 공고 통합 검색 | H1. **공고를 가로지르는** 지원자 검색 — [H1 통합검색 화면](../02_tasks/H1-지원자-통합검색-화면.md)의 데이터 소스. 쿼리는 아래 공고별 목록과 동일 + `posting_id`(선택) |
| GET | /postings/{id}/applications | 지원자 목록 | D1. 쿼리: `q`(이름/이메일 검색, H1) · `stage`(H2) · 페이지네이션 |

- **검색 범위 = 이름·이메일 확정.** 자소서 본문·메모 전문 검색은 H 복합 필터 튜닝 완료 후 여유가 있을 때만 `pg_trgm` GIN 인덱스로 확장한다. 스키마 변경이 아니라 인덱스+쿼리 추가라 미루는 비용이 없다. (한국어는 Postgres 기본 FTS로 형태소 분석이 안 되고, 자소서 5천 자 × 10만 건이면 인덱스 용량·쓰기 비용이 커진다)
| POST | /postings/{id}/applications | 담당자 직접 등록 | D6, recruiter+ |
| GET | /applications/{id} | 지원자 상세 | D4 |
| PATCH | /applications/{id}/stage | 단계 변경 | D3. 이력 기록(D5) + 메일 큐 발행(G1) 트리거 |
| GET | /applications/{id}/history | 단계 이력 | D5 |

## 평가 (E)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /applications/{id}/evaluations | 평가 작성 (점수+코멘트) | E1 |
| GET | /applications/{id}/evaluations | 평가 목록 + 평균 | E2 |

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

## 시스템 (J)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /health | 헬스체크 | 배포·모니터링용 |
| GET | /docs | Swagger UI | J3, FastAPI 자동 |

## 백그라운드 (HTTP 아님)

- **메일 워커** (G2·G3): SQS 폴링 → SES 발송 → `email_logs.status` 갱신, 실패 시 재시도
