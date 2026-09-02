# AI 면접 — 설계와 작업 분해

> **담당: woojeongalex** · 작성 2026-09-02 · 상태: **설계 (미착수)**
> 결정 근거: [ADR-0026 AI 면접은 한다 — 음성으로 긴장도·거짓말을 판별하지 않는다](../03_decision/0026-AI-면접-음성분석-제외.md)
> 선행 결정: [ADR-0003 AI는 추천까지만](../03_decision/0003-ai-추천만.md) · [ADR-0004 음성은 STT만](../03_decision/0004-음성-stt만.md) · [ADR-0023 평가 프레임워크](../03_decision/0023-평가-프레임워크.md)

## 한 줄

**지원자가 링크로 들어와 아르와 면접을 보고, 끝나면 전사·근거 대조·평가 초안이 담당자에게 남는다.**

## 담당 — 읽는 사람이 먼저 알아야 할 것

**이 기능은 woojeongalex 가 맡는다.** 에이전트 도메인 오너(suvisdev)의 폴더를 일부 건드리므로 **착수 전 채널 공지 대상**이다. 도메인 경계는 아래 §4 에 표로 갈라 뒀다 — 남의 폴더에 들어가는 것은 그 표에 적힌 두 파일뿐이다.

**게이트(09/04) 범위 밖이다.** 발표에서는 "다음 단계"로 말한다.

---

## 1. 흐름

| # | 누가 | 무엇 | 재사용 |
|---|---|---|---|
| 1 | 담당자 | 지원자 상세에서 **AI 면접 생성** → 토큰 링크 발급 | B6 공개 토큰 패턴 (`schedule_proposals.token` 과 동일) |
| 2 | 시스템 | 링크를 메일로 발송 | SES·SQS 메일 큐 (G2) |
| 3 | 지원자 | 링크 입장 (로그인 없음) → 마이크 권한 | 공개 페이지 패턴 (`/schedule/:token`) |
| 4 | 아르 | **첫 질문 제시** | AI 요약의 「확인 필요」 항목에서 생성 |
| 5 | 지원자 | 답변 녹음 → S3 직행 업로드 | **F1 presigned** 그대로 |
| 6 | 시스템 | **STT 전사** | `agent/stt.py` (`STT_BACKEND`, ADR-0004) |
| 7 | 아르 | 전사 보고 **꼬리 질문** 결정 → 4로 | 기존 텍스트 에이전트 |
| 8 | 시스템 | 종료 시 **전사 + 대조 결과 + 평가 초안** 생성 | 요약 파이프라인(프롬프트 체이닝, ADR-0022) |
| 9 | 담당자 | 결과 확인 후 **평가 확정** | `evaluations` |

**8번의 대조가 이 기능의 핵심이다** ([ADR-0026](../03_decision/0026-AI-면접-음성분석-제외.md) 결정 3). 이력서·자기소개서의 주장과 면접 발언을 맞춰 보고, 어긋나면 **양쪽 원문을 인용해** 표시한다. 목소리에서 심리 상태를 추론하지 않는다.

---

## 2. 데이터 (ERD 초안 — 구현 시 [01-erd.md](../00_overview/01-erd.md) 갱신 필수)

### `interview_sessions`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | bigint PK | |
| `application_id` | bigint FK | |
| `token` | varchar(64) unique | 공개 링크. `schedule_proposals.token` 과 같은 방식 |
| `status` | varchar | `pending` / `in_progress` / `done` / `expired` |
| `expires_at` | timestamptz | 링크 만료 |
| `started_at` · `ended_at` | timestamptz null | |
| `created_by` | bigint FK users | 만든 담당자 |

### `interview_turns`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | bigint PK | |
| `session_id` | bigint FK | |
| `seq` | smallint | 순서 |
| `question` | text | 아르가 낸 질문 |
| `audio_s3_key` | text null | 답변 녹음 |
| `transcript` | text null | STT 결과 |
| `stt_cost_usd` · `audio_duration_sec` | numeric null | 원가 관측 (기존 규약) |

### `interview_findings` — 대조 결과

| 컬럼 | 타입 | 비고 |
|---|---|---|
| `id` | bigint PK | |
| `session_id` | bigint FK | |
| `claim_source` | varchar | `resume` / `self_intro` |
| `claim_text` | text | **원문 인용** |
| `answer_text` | text | **원문 인용** |
| `verdict` | varchar | `consistent` / `inconsistent` / `unverified` |

> **`verdict` 에 점수를 두지 않는다.** 합불에 곱해지는 수치를 만들면 [ADR-0003](../03_decision/0003-ai-추천만.md) 이 무너진다. 표시는 세 갈래뿐이고 판단은 사람이 한다.

**영상은 저장하지 않는다.** 대리 응시 확인이 필요하면 실시간 표시만 하고 파일을 남기지 않는다 — 저장하는 순간 민감정보 보관 의무가 붙는데 얻는 것에 비해 부담이 크다([ADR-0026](../03_decision/0026-AI-면접-음성분석-제외.md)).

---

## 3. API 초안 (구현 시 [02-api.md](../00_overview/02-api.md) 갱신 필수)

| 메서드 | 경로 | 인증 | 무엇 |
|---|---|---|---|
| POST | `/applications/{id}/interview-sessions` | 로그인 | 세션 생성 + 토큰 발급 |
| GET | `/public/interview/{token}` | **공개** | 세션 상태·현재 질문 |
| POST | `/public/interview/{token}/start` | **공개** | 시작 (상태 전이) |
| POST | `/public/files/presign-upload` | **공개** | 음성 업로드 — **기존 것 재사용** |
| POST | `/public/interview/{token}/turns` | **공개** | 답변 제출(`s3_key`) → 전사 → 다음 질문 |
| POST | `/public/interview/{token}/finish` | **공개** | 종료 → 대조·평가 초안 생성 |
| GET | `/interview-sessions/{id}` | 로그인 | 전사·대조·초안 조회 |

**공개 경로가 늘어난다 — `check_public_contract.py` 대조 대상이다.** 그 스크립트는 `/openapi.json` 에서 GET 을 자동으로 뽑으므로 새 경로가 자동 포함된다. 구현 후 한 번 돌린다.

---

## 4. 도메인 경계

| 부분 | 폴더 | 원 오너 | 이 작업에서 |
|---|---|---|---|
| 테이블·마이그레이션·세션 API·토큰·전사 저장·대조 저장 | `backend/app/` (agent 제외) | woojeongalex | **내 것** |
| 음성 업로드(F1 재사용)·메일 발송(G2 재사용) | `backend/app/` | woojeongalex | **내 것** |
| STT 호출 | `backend/app/agent/stt.py` | suvisdev | **호출만 한다 — 파일 수정 없음** |
| 질문 생성·꼬리 질문 프롬프트 | `backend/app/agent/prompts/` | suvisdev | ⚠️ **새 프롬프트 파일 추가** — 공지 대상 |
| 대조 판정 프롬프트 | `backend/app/agent/prompts/` | suvisdev | ⚠️ **새 프롬프트 파일 추가** — 공지 대상 |
| 지원자 면접 화면 · 담당자 결과 화면 | `frontend/` | cloverky | ⚠️ **넘기거나 협의** |

**남의 폴더에 실제로 들어가는 것은 프롬프트 파일 2개뿐이다.** 기존 파일을 고치는 게 아니라 새로 더한다. 그래도 [03-conventions](../00_overview/03-conventions.md) 대로 커밋에 명시하고 채널에 공지한다.

---

## 5. 작업 순서

**게이트(09/04) 이후 착수.** 앞 단계가 뒷 단계의 선행이라 순서를 지킨다.

| # | 무엇 | 선행 | 크기 |
|---|---|---|---|
| 1 | 테이블 3종 + alembic 리비전 + `01-erd.md` 갱신 | — | 반나절 |
| 2 | 세션 생성·토큰 링크 + `02-api.md` 갱신 | 1 | 반나절 |
| 3 | 공개 조회·시작·종료 API (질문은 고정 목록으로 먼저) | 2 | 반나절 |
| 4 | 음성 업로드 → STT → 전사 저장 | 3 | 하루 |
| 5 | **질문 자동 생성** (요약 「확인 필요」 → 질문) | 4 | 하루 · ⚠️ 에이전트 폴더 |
| 6 | **대조 판정** (주장 ↔ 답변, 원문 인용) | 5 | 하루 · ⚠️ 에이전트 폴더 |
| 7 | 평가 초안 생성 | 6 | 반나절 |
| 8 | 프론트 두 화면 | 3~7 | 프론트 오너 |

**3번까지 하면 사람이 손으로 질문을 넣어도 면접이 돈다.** 거기까지가 뼈대고 5·6이 이 기능의 값이다.

## 6. 먼저 정해야 하는 것

- **면접 시간·질문 수 상한** — 무제한이면 STT 비용이 열려 있다. 질문 5~7개 · 답변당 3분 정도로 시작
- **재응시 허용 여부** — 네트워크가 끊기면? 세션 재개 vs 새 세션
- **동시 접속** — t3.micro 에서 STT 를 몇 개까지 돌릴 수 있나. 큐로 빼는 게 맞을 수 있다
- **지원자 동의** — 녹음·전사·보관에 대한 별도 동의 화면이 필요하다. 지원 폼의 개인정보 동의와 별개다
