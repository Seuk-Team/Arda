# 02. API 엔드포인트 목록

> **상태: 초안.** 필수 기능 기준 목록. 요청/응답 상세는 구현하면서 Swagger(`/docs`)가 진실이 된다 — 이 문서는 "무엇이 있는가"만 유지한다.

- 접두사: `/api/v1`
- 인증: JWT Bearer. **공개**로 표시된 것 외에는 전부 로그인 필요.
- **CORS (2026-09-01 추가)**: 브라우저가 API 를 **직접** 부른다. 허용 출처는 `CORS_ORIGINS` 환경변수(쉼표 구분, 기본 `https://arda.seuk.cloud,https://arda-nu.vercel.app,http://localhost:5173`). 쿠키를 안 쓰므로 `allow_credentials` 는 꺼져 있고 토큰은 `Authorization` 헤더로만 간다. **이 전까지는 CORS 가 없어서 `frontend/app/vercel.json` 의 rewrite 로 /api 를 우회시켰다** — 그 구조에서는 지원자 자소서를 포함한 모든 요청이 제3자(Vercel) 서버를 통과했다. rewrite 제거는 **이 미들웨어가 배포된 뒤에** 해야 한다(먼저 지우면 preflight 에서 막힌다).
- 권한: **`admin` · `member` 2종** ([ADR-0017](../03_decision/0017-등급-이분화.md)). 위계가 아니다 — 아래 넷을 뺀 모든 조회·조작에서 둘은 동일하다.
  - **조회는 로그인만 하면 전부 허용.** 옛 A3(면접관은 배정된 지원서만 조회)는 폐지됐다.
  - **admin 전용**: ① 면접관 배정/해제 ② 계정 생성 ③ 메일 템플릿 ④ **남의** 가용 시간 등록·삭제.
  - **member 제한**: 평가 **작성**은 자기에게 배정된 건만. 그 외 조작(공고 CRUD·단계 변경·일괄 변경·일정 제안·에이전트)은 admin 과 같다.
  - 비고 열이 비어 있으면 "로그인한 사람이면 누구나"라는 뜻이다.

## 인증 (A)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /auth/signup | 회원가입 | A1. **계정 생성은 admin만** (production). role 지정도 admin만 — 그 외에는 `member` 로 만들어진다. 로컬(dev)은 부트스트랩을 위해 열려 있다 |
| POST | /auth/login | 로그인 → JWT 발급 | A1 |
| GET | /auth/me | 내 정보·권한 조회 | A2 |
| PATCH | /auth/me | 내 정보 수정 | G4. 본문 `{name?, current_password?, new_password?}`. 비밀번호 변경은 `current_password` 필수 — 틀리면 401. **email·role 은 못 바꾼다.** 설정 화면에서 member 도 실제로 저장할 수 있는 유일한 항목 |

## 사용자 (A4)

계정 **생성**은 위 `/auth/signup` 이다 — 같은 일을 하는 경로를 둘로 만들지 않는다. **삭제는 없다**: `users.id` 가 `created_by`·`evaluator_id`·`assigned_by`·`changed_by` 로 도처에 박혀 있어 물리 삭제가 이력을 부순다. 비활성화가 그 자리를 대신한다.

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /users | 사용자 목록 | 로그인 전원 (조회 개방, ADR-0017). `{id, name, email, role, is_active, created_at}` |
| PATCH | /users/{id} | 역할·활성 변경 | **admin만.** 본문 `{role?, is_active?}`. **활성 admin 이 0 명이 되는 변경은 409** — 강등이든 비활성화든, 자기 자신이든 남이든 같다. 없는 사용자 404, 빈 본문·모르는 역할 422 |

비활성 계정은 로그인 401 이고 **이미 발급된 토큰도 401** 이다 — 로그인만 막으면 토큰 만료(12시간)까지 그대로 쓴다.

## 채용 공고 (B)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /postings | 공고 목록 (+ 지원자 수) | B1·B3 |
| POST | /postings | 공고 생성 | B1 |
| GET | /postings/{id} | 공고 상세 | |
| PATCH | /postings/{id} | 수정 · 상태 변경(draft/open/closed) · 마감일 | B1·B2·B4. `deadline`(date, null 허용) — 과거 날짜는 422 |
| DELETE | /postings/{id} | 삭제 | B1 |
| POST | /postings/{id}/public-link | 공개 지원 링크 토큰 발급·재발급 | B6. 재발급하면 이전 토큰 즉시 무효 |

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
| POST | /postings/{id}/applications | 담당자 직접 등록 | D6 |
| GET | /applications/{id} | 지원자 상세 | D4 |
| PATCH | /applications/{id}/stage | 단계 변경 | D3. 이력 기록(D5) + 메일 큐 발행(G1) 트리거. `reason`(선택) — **`to_stage="rejected"` 인데 없으면 422** (D8) |
| POST | /applications/bulk-stage | 여러 명 단계 일괄 변경 | D9. 본문 `{application_ids, to_stage, reason?}`. 한 번에 **200명**까지(넘으면 422) |
| GET | /applications/{id}/history | 단계 이력 | D5. 응답에 `reason` 포함 (D8) |

- **일괄 변경은 전부 성공하거나 전부 실패한다 (D9).** 한 건이라도 전환 규칙에 걸리거나 없는 id 가 섞이면 **전체 롤백 + 409**, 응답 `message` 에 `failed`·`not_found` id 목록이 담긴다. 30명만 바뀌고 끝나면 담당자가 무엇이 됐는지 알 수 없다.
- 이미 그 단계인 건은 실패가 아니라 `skipped` 로 분류하고 건너뛴다. 성공 응답은 `{changed, changed_ids, skipped, mail_queued}`.
- **메일은 건별로 큐에 넣는다** — 지원자마다 이름·공고가 다르므로 한 통으로 묶을 수 없다.

## 평가 (E)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /applications/{id}/evaluations | 평가 작성 (점수+코멘트) | E1. **admin 무제한, member 는 배정된 건만** (ADR-0017) — 미배정이면 403 |
| GET | /applications/{id}/evaluations | 평가 목록 + 평균 | E2 |
| PATCH | /evaluations/{id} | 평가 수정 | 본인 평가만 (A1 연결 후 강제). score·comment 부분 수정 허용. 08/25 검수에서 #50 구현을 계약에 반영(팀장 승인) |

## 면접관 배정 (E3)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /applications/{id}/interviewers | 면접관 배정 | E3, **admin만** ([ADR-0013](../03_decision/0013-면접관-배정-정책.md)). 중복 배정은 무시(멱등). **대상의 role 은 보지 않는다** — 누구나 면접관이 될 수 있다 |
| GET | /applications/{id}/interviewers | 배정된 면접관 목록 | |
| DELETE | /applications/{id}/interviewers/{user_id} | 배정 해제 | admin만 (ADR-0013) |
| GET | /interviewers/{user_id}/applications | 배정받은 지원자 목록 | 남의 것도 볼 수 있다 |

## 면접 일정 (S)

> [ADR-0016](../03_decision/0016-면접-일정-자동화.md) · ERD v1.2. **구현 완료 (2026-08-31)** — 배포 서버에서 E2E(가용 시간→배정→제안→공개 조회→확정→메일 렌더) 통과.

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /interviewers/{user_id}/availability | 가용 시간 등록 | **본인 또는 admin** — 남의 것은 admin 전용. 대상 role 검사 없음 |
| GET | /interviewers/{user_id}/availability | 가용 시간 목록 | 남의 것도 볼 수 있다 |
| DELETE | /availability/{id} | 가용 시간 삭제 | **본인 또는 admin**. 이미 나간 제안의 슬롯은 스냅샷이라 영향 없음 |
| POST | /applications/{id}/schedule-proposals | 일정 제안 생성 | 배정 면접관(E3) 가용 시간에서 후보 슬롯 생성 + 제안 메일 큐 발행 |
| GET | /schedules | 확정 면접 목록 | 면접 일정 화면. 쿼리 `from`·`to`·`mine`. 역할 분기 없음 — 전원이 전체를 보고, `mine=true` 로 자기가 면접관인 건만 좁힌다 (필터이지 권한이 아니다) |
| GET | /applications/{id}/schedule-proposals | 최신 제안 상태 | 대시보드·상세 패널 칩 용도. 제안 없으면 404 |
| GET | /public/schedule/{token} | 지원자용 일정·전형 현황 조회 | **공개**. 만료된 제안은 조회 시점에 `expired` 판정(B4 방식). 없는 토큰 404 |
| POST | /public/schedule/{token}/confirm | 슬롯 선택 → 확정 | **공개**. 본문 `{slot_id}`. 이미 확정·만료·취소면 409. 확정 시 통보 메일 큐 발행 |

## AI 면접 (ADR-0026)

지원자가 링크로 들어와 아르와 면접을 본다. 토큰 공개 접근은 일정 제안(B6)과 같은 패턴이다.
설계는 [AI면접-설계](../02_tasks/AI면접-설계.md).

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /applications/{id}/interview-sessions | 면접 세션 생성 + 공개 링크 발급 | 본문 `{expires_in_days?}` (1~30, 기본 7). **재발급이 아니라 새 행**이라 이전 링크가 죽지 않는다 — 공고 public-link 와 다르다 |
| GET | /applications/{id}/interview-sessions | 이 지원자의 세션 목록 | 최신순 |
| GET | /interview-sessions/{id} | 세션 상세 | 전사(`turns`)와 서류↔발언 대조(`findings`) 포함 |
| GET | /public/interview/{token} | 지원자용 조회 | **공개**. 만료는 조회 시점 판정(B4 방식). **담당자 이름·평가·다른 지원자를 내려주지 않는다** |
| POST | /public/interview/{token}/consent | 녹음·전사 동의 | **공개**. 본문 `{agreed}`. **지원 폼의 개인정보 동의와 별개다** — 거절하면 422, 기록도 안 남는다 |
| POST | /public/interview/{token}/start | 면접 시작 | **공개**. 동의 없으면 422 · 만료면 410 · 준비된 질문이 없으면 422 |
| PUT | /interview-sessions/{id}/questions | 질문 목록 설정 | 본문 `{questions: [...]}` (1~20개). **시작 전에만** — 진행 중 변경은 409 |
| POST | /public/interview/{token}/answer | 현재 질문에 답변 | **공개**. 본문 `{transcript}`. **답 안 한 가장 앞 질문**에 붙는다 — 순번을 지원자가 보내지 않는다. 남은 질문이 없으면 409 |
| POST | /public/interview/{token}/finish | 면접 종료 | **공개**. **다 답하지 않아도 끝낼 수 있다.** 두 번 눌러도 200 |

- **동의가 시작의 선행 조건이다.** `consented_at` 이 비어 있으면 `/start` 가 422 로 거절한다
- `findings` 에 **점수가 없다** — `consistent` / `inconsistent` / `unverified` 셋뿐이고 판단은 사람이 한다 ([ADR-0003](../03_decision/0003-ai-추천만.md))
- 답변 음성 업로드는 **기존 `POST /public/files/presign-upload` 를 그대로 쓴다** — 새 경로를 만들지 않았다
- 아직 없는 것: 답변 제출·전사(`/turns`) · 종료(`/finish`). 설계 §5 의 4번부터다

## 인적성(사전 성향) 설문 (ADR-0027)

접수 후·서류검토 전에 링크를 보내고, 응답 통계와 AI 관찰 요약(재서술만)이 서류검토 참고자료가 된다. 토큰 공개 접근은 AI 면접과 같은 패턴이다. ([ADR-0027](../03_decision/0027-인적성-검사.md))

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| POST | /postings/{id}/aptitude/send | 공고 단위 일괄 발송 | "아직 안 받은 전원에게". 이미 발송·지난 단계는 건너뛰고 **몇 건이 왜 빠졌는지 숫자로** 돌려준다 `{sent, skipped_already_sent, skipped_stage}` |
| POST | /applications/{id}/aptitude/send | 개별 발송·재발송 | **매번 새 행** — 옛 링크가 죽지 않는다 (AI 면접과 같은 철학). 접수·서류검토 단계에서만 (아니면 422) |
| GET | /applications/{id}/aptitude | 담당자 조회 | 최신 세션의 응답 원문·카테고리 통계·AI 요약. 세션 없으면 `status:"none"` |
| GET | /public/aptitude/{token} | 지원자용 조회 | **공개**. 만료는 조회 시점 판정. pending 일 때만 문항을 내려준다. 담당자 정보 없음 |
| POST | /public/aptitude/{token}/submit | 응답 제출 | **공개**. 전 문항 필수(부분 제출 422) · 재제출 409 · 만료 410. 제출되면 백그라운드로 관찰 요약 생성 |

- 문항은 코드 상수 10개, 리커트 5점 (`backend/app/aptitude_questions.py`)
- **AI 는 요약만** — 응답 통계는 코드가 계산하고 LLM 은 재서술 한 문단만 쓴다. 유형 판정·점수·합불 의견을 만들지 않는다 ([ADR-0027](../03_decision/0027-인적성-검사.md) · [ADR-0003](../03_decision/0003-ai-추천만.md))
- **미응답은 아무것도 막지 않는다** — 서류검토·단계 이동 어디에도 응답 여부가 끼지 않는다
- 발송 메일은 `email_logs` 의 custom 경로(create_custom_log)로 남는다 — 보낸 그대로가 감사 기록

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
| POST | /agent/applications/{id}/summarize | AI 요약 재생성 | M2. 기존 요약을 덮어쓴다 |
| POST | /agent/chat | 에이전트 채팅 (검색·조회) | M3. 읽기 도구로 지원자 검색·조회, 쓰기 도구는 pending_action으로 반환. 응답에 사용량(`input_tokens`·`output_tokens`·`cache_write_tokens`·`cache_read_tokens`·`cost_usd`) 포함 ([ADR-0011](../03_decision/0011-에이전트-모델-비용.md)). **2026-09-01 변경**: `model` 이 모델명이 아니라 **`backend:model` 태그**다 (`anthropic:claude-haiku-4-5-20251001` · `ollama:qwen3:4b`) — 토크나이저가 달라 백엔드 간 토큰 수 비교가 불가능하므로 어느 엔진이 낸 값인지 함께 남긴다. **`backend` 필드가 추가**됐다(`anthropic` · `ollama`). 로컬 백엔드는 프롬프트 캐싱 개념이 없어 캐시 토큰이 **항상 0**이다 — `backend` 를 봐야 '캐시 미적중'과 '캐시 개념 없음'이 구분된다. 백엔드 선택은 `AGENT_CHAT_BACKEND`(기본 `anthropic`, [ADR-0024](../03_decision/0024-sLLM-로컬-모델-전략.md)) |
| POST | /agent/confirm | 쓰기 도구 확인 실행 | M4, 로그인 필요. 사용자가 확인 카드를 승인한 뒤 호출. **메일 발송(`send_email`)도 이 경로를 탄다** — 되돌릴 수 없는 조작이라 승인 없이는 실행되지 않는다 (G4) |

## 메일 (G4)

문구는 **코드 기본값 + DB 오버라이드**다. 오버라이드가 없으면 [email-templates.md](email-templates.md) 의 기본 문구가 나간다. 발송은 어느 경로든 `email_logs` 행 생성 → 커밋 → SQS → 워커 → SES 순서를 그대로 탄다.

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /email-templates | 문구 4종 조회 | 로그인 전원. 항목마다 `source: "default" \| "custom"` — 지금 나가는 것이 기본값인지 수정본인지 |
| PUT | /email-templates/{stage} | 오버라이드 저장 | **admin만** (ADR-0017). 본문 `{subject, body}`. 허용 외 `{...}` 변수 **422**, 4종(`applied`·`interview`·`accepted`·`rejected`) 외 stage **404**. `{서명}` 이 없으면 본문 끝에 자동으로 붙는다 |
| DELETE | /email-templates/{stage} | 오버라이드 삭제 = 기본값 복귀 | **admin만.** 수정본이 없으면 404. 204 가 아니라 복귀한 기본 문구를 돌려준다 |
| GET | /applications/{id}/emails/preview | 수동 발송 프리필 | 로그인 전원. `?stage=` 문구에 이 지원자 값을 채워 돌려준다 — 치환을 화면이 하면 미리보기와 실제 발송이 갈린다 |
| POST | /applications/{id}/emails | 수동 발송 | 로그인 전원. 본문 `{subject, body}` — **수신자를 받지 않는다.** 서버가 지원자 주소로 고정한다. `email_logs(stage=custom, actor_kind=human)` 생성 |
| GET | /applications/{id}/emails | 발송 이력 | 로그인 전원. 자동·수동 통합, 최신순 |

발송 주체(`email_logs.actor_kind`)가 **From 표시 이름 · 본문 서명 · 회신 주소** 셋을 함께 정한다. 셋이 어긋나면 지원자가 누구에게 연락할지 헷갈린다.

| 주체 | From 표시 이름 / 서명 | Reply-To |
|---|---|---|
| `human` | `Arda 채용 담당자 {이름}` | 그 사람의 `users.email` |
| `agent` | `Arda 채용 에이전트 아르` | `MAIL_REPLY_TO` |
| `system` | `Arda 채용팀` | `MAIL_REPLY_TO` |

**합격·불합격은 주체와 무관하게 사람 이름**이다. 발신 **주소**는 언제나 `SES_FROM_EMAIL` 하나다 — 담당자 개인 주소를 From 에 넣으면 외부 메일(gmail 등)에서 DMARC 정렬이 깨져 스팸함으로 간다. 개인 연락처 역할은 Reply-To 가 맡는다.

## 시스템 (J)

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /health | 헬스체크 | 배포·모니터링용 |
| GET | /docs | Swagger UI | J3, FastAPI 자동 |

## 백그라운드 (HTTP 아님)

- **메일 워커** (G2·G3): SQS 폴링 → SES 발송 → `email_logs.status` 갱신, 실패 시 재시도
