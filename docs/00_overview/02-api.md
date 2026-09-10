# 02. API 엔드포인트 목록

> **상태: 초안.** 필수 기능 기준 목록. 요청/응답 상세는 구현하면서 Swagger(`/docs`)가 진실이 된다 — 이 문서는 "무엇이 있는가"만 유지한다.

- 접두사: `/api/v1`
- 인증: JWT Bearer. **공개**로 표시된 것 외에는 전부 로그인 필요.
- **CORS (2026-09-01 추가)**: 브라우저가 API 를 **직접** 부른다. 허용 출처는 `CORS_ORIGINS` 환경변수(쉼표 구분, 기본 `https://seuk.suvisdev.cloud,https://arda-teal.vercel.app,http://localhost:5173`). 쿠키를 안 쓰므로 `allow_credentials` 는 꺼져 있고 토큰은 `Authorization` 헤더로만 간다. **이 전까지는 CORS 가 없어서 `frontend/app/vercel.json` 의 rewrite 로 /api 를 우회시켰다** — 그 구조에서는 지원자 자소서를 포함한 모든 요청이 제3자(Vercel) 서버를 통과했다. rewrite 제거는 **이 미들웨어가 배포된 뒤에** 해야 한다(먼저 지우면 preflight 에서 막힌다).
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
| POST | /public/postings/{id}/applications | 지원서 제출 | **공개**, C1·C3. 중복 지원 409 (C6). 마감된 공고는 **410** (B4). 본문에 `files[]`(presign 으로 받은 `s3_key`·`filename`·`size_bytes`·`content_type`·`kind`)를 함께 보내면 그때 `files` 행이 생긴다 — presign 시점에는 지원서가 없어 만들 수 없다 (F1 → C2). **`birth_date` 를 함께 받는다**(선택, `YYYYMMDD` 또는 `YYYY-MM-DD`) — 앱 로그인의 비밀번호가 되고, **없으면 접수는 되지만 그 사람은 앱에 로그인할 수 없다** ([ADR-0033](../03_decision/0033-지원자-앱-로그인.md)) |
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
| GET | /interview-sessions/active | **지금 진행 중인 면접들** | 2026-09-09 신설. `in_progress` 만 낸다 — 안 시작한 것은 볼 게 없고 끝난 것은 방이 안 열린다. 지원자 이름·공고 제목을 같이 내려 **대시보드가 한 번에 들어간다** (없으면 지원자 목록 → 상세 → 세션 → 링크 넷을 거쳐야 실시간 분석 화면에 닿는다). **경로 순서 주의** — `{id}` 위에 둔다. 아래 두면 `active` 가 id 로 읽혀 422 |
| GET | /interview-sessions/{id} | 세션 상세 | 전사(`turns`)와 서류↔발언 대조(`findings`) 포함 |
| GET | /public/interview/{token} | 지원자용 조회 | **공개**. 만료는 조회 시점 판정(B4 방식). **담당자 이름·평가·다른 지원자를 내려주지 않는다** |
| POST | /public/interview/{token}/consent | 녹음·전사 동의 | **공개**. 본문 `{agreed}`. **지원 폼의 개인정보 동의와 별개다** — 거절하면 422, 기록도 안 남는다 |
| POST | /public/interview/{token}/start | 면접 시작 | **공개**. 동의 없으면 422 · 만료면 410 · 준비된 질문이 없으면 422 |
| PUT | /interview-sessions/{id}/questions | 질문 목록 설정 | 본문 `{questions: [...]}` (1~20개). **시작 전에만** — 진행 중 변경은 409 |
| POST | /public/interview/{token}/audio-upload-url | 답변 녹화 업로드 URL 발급 | **공개**. 본문 `{filename, content_type, size_bytes}`. **진행 중인 면접만** — 아니면 409·만료 410. 허용 `webm`·`m4a`·`mp3`·`wav`·`mp4`, **50MB 이하**(카메라를 켜면 같은 길이가 훨씬 커진다 — 이력서 상한 10MB 와 따로 둔다). 키는 서버가 만든다(`interviews/<uuid>/answer.<ext>`) |
| POST | /interview-turns/{id}/analyze | 녹화 진위 분석 (ADR-0029) | 담당자용. **`LIE_SERVICE_URL` 이 없으면 503** — 설정을 안 넣으면 꺼져 있다. 녹화 없는 회차 409 · 서비스 실패 502. **결과를 저장하지 않는다** |
| POST | /public/interview/{token}/answer | 현재 질문에 답변 | **공개**. 본문 `{transcript}` **또는** `{audio_s3_key}` — **둘 다 보내면 422**. 음성이면 서버가 읽어 전사하고 길이·비용까지 적는다. **`seq` 를 주면 그 칸**, 안 주면 **답 안 한 가장 앞 질문**에 붙는다(2026-09-09). 남은 질문이 없으면 409 — `seq` 를 짚었는데 이미 답이 들어간 칸이어도 409라 같은 답을 두 번 보내도 덮어쓰지 않는다. 응답에 **`pacing`** 이 붙을 수 있다(아래) |
| POST | /public/interview/{token}/finish | 면접 종료 → **대조 생성** | **공개**. **다 답하지 않아도 끝낼 수 있다.** 두 번 눌러도 200. 대조(`findings`)는 **뒤에서** 만든다(아래) |
| POST | /interview-sessions/{id}/rtc-ticket | 실시간 면접 입장권 (채용자) | 로그인 필요. **60초·1회용.** 응답 `{ticket, token, expires_in, ice_servers}` — 접속 직전에 받는다 |
| WS | /ws/interview/{token}/rtc | 실시간 면접 시그널링 | 지원자는 토큰만, **채용자는 `?ticket=` 까지** 있어야 한다. 프로토콜은 [실시간-면접-시그널링](../02_tasks/실시간-면접-시그널링.md) |

- **실시간 면접(사람 ↔ 사람)은 위 REST 흐름과 별개다** (2026-09-08). 지원자는 폰, 채용자는 PC 로 붙어 **WebRTC 로 직접** 영상·음성을 주고받고, 서버는 연결을 맺는 쪽지(SDP·ICE)만 나른다 — **영상이 API 를 지나가지 않는다.** 1:1 이라 SFU 가 없고, 못 붙는 망을 위한 TURN 은 `RTC_ICE_SERVERS` 로 넣는다(클라이언트가 목록을 박지 않고 서버가 `hello` 로 알려준다). **채용자 자리에 입장권을 요구하는 이유**는 토큰만으로 면접관석에 앉으면 링크를 받은 누구든 지원자의 얼굴을 보게 되기 때문이다. 상세는 [실시간-면접-시그널링](../02_tasks/실시간-면접-시그널링.md)
- **동의가 시작의 선행 조건이다.** `consented_at` 이 비어 있으면 `/start` 가 422 로 거절한다
- `findings` 에 **점수가 없다** — `consistent` / `inconsistent` / `unverified` 셋뿐이고 판단은 사람이 한다 ([ADR-0003](../03_decision/0003-ai-추천만.md))
- **영상으로도 답할 수 있다** (2026-09-07). 카메라를 켜면 **음성이 같은 파일에 들어가므로** 올리는 경로가 하나로 끝난다 — 전사는 그 파일에서 음성만 뽑고, 같은 파일이 진위 분석(ADR-0029)의 입력이 된다. **한 번 녹화로 둘 다 된다**
- **답변 음성은 이력서 업로드 경로를 쓰지 않는다** (2026-09-07 변경). `POST /public/files/presign-upload` 는 토큰 없이 누구나 부를 수 있어서, 거기에 음성 형식을 얹으면 아무나 버킷에 미디어를 올릴 수 있다. 그리고 이력서 허용 목록에 `.webm` 이 들어가면 **이력서 자리에 음성이 박힌다.** 그래서 면접 토큰이 필요한 별도 경로를 뒀다
- **전사는 `raw` 를 저장한다 — `resolved` 가 아니다.** 엔티티 해석("파이썬 이년" → "Python 2년")을 거친 문장을 저장하면, 나중에 이력서 주장과 맞춰 **원문으로 인용**할 때(ADR-0026 결정 3) 지원자가 하지 않은 말을 인용하게 된다
- **전사에 실패하면 아무것도 저장하지 않고 502.** 반쯤 저장하면 답을 못 한 채로 다음 질문으로 넘어간다. 음성은 S3 에 남지만 회차가 비어 있어 지원자에게 같은 질문이 그대로 보이고 다시 답할 수 있다
- **`pacing` — 진행 보조** (2026-09-07, [ADR-0026](../03_decision/0026-AI-면접-음성분석-제외.md) 결정 4). 답변 응답에만 붙고 조회(GET)에는 항상 `null` 이다. 모양은 `{action, message}` 이고 `action` 은 `follow_up`(되묻기) · `offer_break`(쉬어가기 권함) · `rephrase`(질문을 바꿔 보자) 셋. **점수가 없고 DB 에 저장되지 않는다** — 평가로 가는 길을 만들지 않기 위해서다. 제안할 것이 없으면 `null`. 규칙은 `app/interview_pacing.py`
  - 보는 것 둘: **답이 아주 짧다**(전사 글자 수) · **말이 유난히 느리다**(글자 수 ÷ `audio_duration_sec`, 음성으로 답했을 때만)
  - **말이 느린 것을 "긴장했다"로 적지 않는다.** 그렇게 적으면 심리 추론이 되어 ADR-0026 결정 2 를 넘는다. 우리가 말할 수 있는 것은 "말이 느렸다"까지고, 할 수 있는 것은 "질문을 바꿔 보자"까지다
  - 속도 임계값은 **임시값**이다. 실제 지원자 녹음이 쌓이면 분포를 보고 다시 정한다
  - 침묵 길이는 아직 못 본다 — 브라우저가 녹음 시작~첫 발화를 재서 보내야 한다
  - **프론트는 모르는 `action` 을 무시하도록** 짠다. 신호가 늘면 여기가 늘어난다
- 아직 없는 것: 질문 자동 생성(설계 §5-5) · 대조 판정(§5-6) · 평가 초안(§5-7). **셋 다 에이전트 폴더**다

## 지원 현황 조회 — 지원자용 (신-1 지원자 포털)

지원자가 이메일을 넣으면 **그 주소로 조회 링크를 보낸다.** 링크를 열면 자기 지원이 어디까지 왔는지 본다. 로그인도 비밀번호도 없다 — 나머지 공개 경로(면접·일정·인적성)와 같은 토큰 방식이다.

| 메서드 | 경로 | 설명 | 비고 |
|---|---|---|---|
| POST | /public/applications/lookup | 조회 링크를 메일로 발송 | **공개**. 본문 `{email}`. 항상 **202** 와 **같은 본문** |
| GET | /public/applications/status/{token} | 지원 현황 | **공개**. 없는 토큰 404 · 기한 지남 **410** |
| POST | /public/applicant/login | 지원자 앱 로그인 | **공개**. 본문 `{email, birth_date}` (8자리 `YYYYMMDD`). 실패는 전부 **401** — 형식 오류도 401 이다. 5회 실패 시 **429**(15분) |
| GET | /applicant/me | 내 지원 현황 | **지원자 토큰 전용.** 조회 인자를 받지 않는다 — 토큰의 이메일로만 찾는다. 지원마다 `interviews[]` · `aptitudes[]` · `schedules[]` 가 붙는다(각 `token`·`status`·`expires_at`) |

- **없는 주소도 똑같이 답한다.** 다르게 답하면 그것만으로 "이 사람이 여기 지원했는가"를 확인하는 도구가 된다 — 이직 준비 중인 사람에게는 지원 사실 자체가 알려지면 안 되는 정보다. 건수도 안 돌려준다
- ~~**접수번호 + 생년월일 방식을 쓰지 않았다.**~~ → **2026-09-08 개정** ([ADR-0033](../03_decision/0033-지원자-앱-로그인.md)). 앱 로그인에 **이메일 + 생년월일 8자리**를 쓴다. 위 판단(경우의 수가 만 단위라 자동으로 뚫린다)은 **지금도 기술적으로 맞고**, 그래서 안전해졌다고 적지 않는다 — 채택 이유는 시연 편의다. 막는 것은 해시가 아니라 **시도 횟수 제한**(5회/15분)이다. 메일 링크 포털은 **그대로 남는다** — 생년월일을 안 낸 사람과 앱을 안 쓰는 사람의 길이다
- **다시 요청하면 지난 링크는 죽는다.** 토큰이 UNIQUE 라 재발급이 덮어쓴다
- 한 사람이 공고 여러 개에 냈으면 **지원 건마다 한 통씩** 나간다. 메일이 지원 건에 매여 있어서(`email_logs.application_id`) 한 통에 몰면 나머지 지원의 기록에 아무것도 안 남는다
- **`rejected` 를 "불합격"이라고 쓰지 않는다.** 담당자가 통보하기 전에 화면이 먼저 말하면 안 된다 — `전형 종료` 로 내리고 **사유는 어디에도 싣지 않는다**
- **지원자가 들어갈 토큰 3종을 `/applicant/me` 가 같이 내린다** — `interviews[]`·`aptitudes[]`·`schedules[]` (2026-09-08). 본인 토큰으로 조회한 자기 것이라 새로 여는 비밀이 아니고, 이게 없으면 **로그인해 놓고도 메일함을 뒤져야 한다.** 앱에는 메일함이 없어서 [ADR-0033](../03_decision/0033-지원자-앱-로그인.md) 이 없애려던 문제가 그 탭들에 그대로 남는다
  - ~~**아직 할 일이 남은 것만 싣는다**~~ → **2026-09-09 개정. 끝난 것도 싣는다** — 면접 `pending`·`in_progress`·**`done`** · 인적성 `pending`·**`done`** · 일정 `proposed`·`confirmed`. **만료(`expired`)만 뺀다**
  - **왜 바꿨나**: 끝난 것을 빼면 면접을 마친 지원자의 화면에서 면접이 **통째로 사라진다.** "완료"와 "아직 안 잡힘"이 같은 화면이 되어, 방금 면접을 본 사람이 자기가 낸 것이 접수됐는지 알 수 없다(2026-09-09 앱 실측). `expired` 를 계속 빼는 이유는 다르다 — 그건 지원자가 놓친 것이라 화면에 띄워도 할 수 있는 일이 없다
  - **화면이 `status` 로 가른다.** 끝난 줄에는 들어가는 문을 그리지 않는다 — 앱(`applicant_summary_screen.dart`)·웹(`MyApplications.tsx`) 둘 다
  - 들어가는 곳: `/interview/{token}`(AI 면접) · `/interview-live/{token}`(실시간) · `/aptitude/{token}` · `/schedule/{token}`
  - **`status` 로 AI 면접과 실시간 면접을 가를 수 없다** — 세션에 종류 컬럼이 없고 **같은 토큰을 두 방식이 공유한다**
- **지원자 토큰은 직원 토큰과 종류가 다르다** (`typ`). 같은 비밀키로 서명하므로 **서명 검증이 이걸 못 막는다** — 양쪽 의존성에서 종류를 확인해 서로의 경로를 못 타게 한다. 지원자 토큰은 2시간이고, 볼 수 있는 것은 자기 지원의 `id`·`posting_title`·`stage_label`·`applied_at` 넷뿐이다
- 내려주는 것은 `applicant_name` · `posting_title` · `stage_label` · `submitted_at` 넷뿐이다. 평가·메모·담당자 이름은 없다

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

## 제출물 무결성 (ADR-0028)

제출 순간 이력서·자소서의 지문(SHA-256)을 떠서 append-only 사슬에 쌓는다. 나중에 원본이 바뀌면 지문이 안 맞으므로 드러난다. **전부 로그인 필요 — 지원자에게는 내려주지 않는다.** ([ADR-0028](../03_decision/0028-제출물-무결성-앵커.md))

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /applications/{id}/integrity | 제출물이 제출 당시 그대로인지 | **볼 때마다 원본을 다시 읽어 지문을 새로 뜬다.** 첨부가 있으면 S3 를 읽으므로 **목록에서 N 번 부를 API 가 아니다** — 상세에서 한 번 |
| POST | /applications/{id}/integrity/anchor | 앵커가 없는 제출물의 지문을 뜬다 (백필) | ADR-0028 이전 접수분용. **이미 앵커된 것은 건드리지 않는다** — 여러 번 눌러도 사슬이 안 부푼다 |
| GET | /integrity/chain | 원장 전체가 이어지는지 + **공개 체인 게시 상태** | `{intact, length, broken_at, reason, published, unpublished_count}`. 처음 깨진 자리에서 멈춘다 |
| POST | /integrity/publish | EVM 체인(운영: Sepolia, 2026-09-07~)에 직접 올린다 | **admin 전용.** ⚠️ **과도기·로컬 전용** — 운영에서는 GitHub Actions 가 서명한다(아래). 서버에 `CHAIN_PRIVATE_KEY` 가 있을 때만 동작. **503** 설정 없음 · **409** 올릴 것 없음 · **502** 전송 실패 |
| POST | /integrity/publish/ots | OpenTimestamps(비트코인)에 도장 | **admin 전용.** **개인키가 없어서 서버가 직접 돈다.** 응답은 대개 `pending` — 비트코인 블록에 실리기까지 몇 시간이 정상 |
| POST | /integrity/publications/start | 게시할 자리를 잡고 **올릴 값**을 알려준다 | **admin 전용.** 쿼리 `network`. GitHub Actions 가 부른다 — 서버는 서명하지 않는다. **409** 올릴 것 없음 |
| POST | /integrity/publications/{id}/result | 밖에서 서명·전송한 결과를 기록 | **admin 전용.** 본문 `{status, tx_hash?, block_number?, from_address?, proof?, error?}`. **서버는 이 값을 검증하지 못한다** — 체인의 값이 진실이고 이건 영수증이다. 없는 id 는 404 |
| GET | /integrity/publications | 못 박은 기록 목록 (최신 50) | `explorer_url` 포함 — 발표에서 이 링크를 연다 |
| POST | /integrity/publications/refresh | 확정 못 본 게시 재확인 | EVM 체인(Sepolia)은 영수증 재조회, OTS 는 캘린더 재질의. **못 받은 것은 실패가 아니라 아직인 것.** 바뀐 것만 돌려준다 |

- `verdict` 는 넷이다: `ok` · `mismatch`(**바뀌었다**) · `unreadable`(원본을 못 읽는다) · `none`(**앵커가 없다**). `none` 을 `ok` 와 섞지 않는다 — "깨끗하다"가 아니라 "증명할 근거가 없다"다
- 항목이 여럿이면 **나쁜 쪽이 이긴다** — 하나라도 어긋나면 전체가 `mismatch`
- 개별 검증과 사슬 검증은 **다른 질문**이다. 원본을 바꾸고 앵커 행까지 같이 고쳐 놓으면 개별은 통과하지만 사슬이 깨진다
- 앵커 생성은 접수 시 **백그라운드**다 — 지원자를 제출 버튼 앞에 세워 두지 않는다. 실패해도 접수는 유효
- ⚠️ **사후 앵커(백필)는 "이 시각에 이 내용이었다"까지만** 증명한다. 접수 시점의 내용이었다는 증명이 아니다
- **공개 체인에 올리는 값은 사슬 머리 하나뿐**이다 — 각 고리가 앞 고리를 재료로 쓰므로 머리 하나가 그 앞을 전부 덮는다. 원본·개인정보는 아무것도 안 나간다
- **못 박는 곳이 둘이다**: 공개 EVM 테스트넷(보여주는 쪽 — 탐색기 링크. 운영은 `ethereum-sepolia`, 2026-09-07 부터 — Amoy faucet 이 막혀 옮겼다)과 `opentimestamps`(남기는 쪽 — 비트코인, 영구). **같은 머리라도 네트워크가 다르면 각각 올린다**
- **서명 위치가 갈린다**: EVM 체인(운영 Sepolia — Amoy 는 faucet 이 막혀 09/07 보류)은 개인키가 필요해 **GitHub Actions 가** 서명한다(서버에 키를 두지 않는다 — ADR-0028). OTS 는 키가 없어 **서버가 직접** 찍는다
- `CHAIN_RPC_URL`·`CHAIN_PRIVATE_KEY` 가 없으면 **EVM 체인 게시만 꺼진다** — OTS·접수·앵커·검증은 그대로 돈다
- `unpublished_count` 는 마지막 게시 이후 쌓인 고리 수다. **그만큼이 아직 외부 증명이 없는 구간**이다

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

## 내부 (`/internal/*`) — 사람이 부르지 않는다

우리 서비스끼리 부르는 자리다. **로그인이 아니라 서비스 토큰**으로 지킨다 —
헤더 `X-Service-Token` 이 서버 `.env` 의 `ARDA_SERVICE_TOKEN` 과 같아야 한다.
**환경변수가 없으면 전부 401** 이다(실수로 열리지 않게 기본 닫힘).

| 메서드 | 경로 | 기능 | 비고 |
|---|---|---|---|
| GET | /internal/email-logs/{id}/render | n8n SMTP 노드가 읽을 완성된 제목·본문·수신자 | 이미 `sent` 면 409 ([ADR-0030](../03_decision/0030-n8n-알림-자동화-분리.md)) |
| POST | /internal/email-logs/{id}/result | 발송 결과 기록 | 멱등 — 이미 `sent` 면 no-op |
| POST | /internal/interview/{token}/verdict | 면접 실시간 판정을 담당자에게 민다 | 본문 `{truth_pct?, lie_pct?, window_sec?, …}`. **204 고정** |
| GET | /internal/interview/{token}/questions | 면접 질문 전체 `[{seq, question}]` | 워커가 시작할 때 한 번. **전사를 안 기다리고 다음 질문을 보내기 위한 것** |
| GET | /internal/interview/{token}/portrait | 이력서에 든 증명사진 원본 바이트 | `image/jpeg`. 사진이 없으면 **404**(정상 — 워커가 확인을 건너뛴다) |
| POST | /internal/interview/{token}/identity | 이력서 사진 대조 결과를 담당자에게 민다 | 본문 `{match: same\|different\|unclear, score}`. 면접당 **한 번**. 204 고정 |

- **판정은 워커 → 백엔드 → 담당자다** (2026-09-08). 전에는 지원자 기기가 받아
  중계했는데, 화면에 안 그려도 **개발자 도구를 열면 보인다** — [ADR-0029](../03_decision/0029-표정-음성-진위-판별-도입.md)
  의 "지원자에게 판정을 보여 주지 않는다"가 거기서 깨진다. 지금은 **지원자 기기를
  아예 지나가지 않는다**
- **저장하지 않는다.** 흐르는 값이고, 남기기로 한 것은 면접이 끝난 뒤의 결과다
- **담당자가 화면을 안 열었어도 204** 다. 받는 사람이 없으면 그냥 버린다 —
  그것 때문에 면접이 멈추거나 워커가 재시도하면 안 된다
- 본문은 **모양을 좁게 잡지 않았다**(`extra="allow"`). 모델이 내는 값이 늘어도
  백엔드를 고치지 않고 그대로 담당자에게 흘러간다

**동일인 확인(`portrait` · `identity`)은 판정과 다른 통로다** (2026-09-09 회의 3번).

- **저장하지 않는다.** 백엔드가 이력서 PDF 에서 사진을 꺼내 그때 넘기고, 워커는
  얼굴 지문을 메모리에만 두고 연결이 끊기면 버린다. 얼굴 지문은 갈아 끼울 수 없는
  생체정보라, 남기는 순간 지켜야 할 것이 하나 는다 — 대리응시 확인에는 그때그때
  비교로 충분하다([ADR-0026](../03_decision/0026-AI-면접-음성분석-제외.md) 과 같은 자리)
- **판정(`verdict`)에 섞지 않는다.** 참·거짓 판정은 매초 흐르는 값이고 이건 신원
  확인이라 성격이 다르다. 같은 스트림에 얹으면 화면에서 거짓말 지표처럼 읽힌다
- **`different` 를 보수적으로 낸다.** 놓친 대리응시는 면접관이 눈으로 잡을 여지가
  남지만, 멀쩡한 지원자를 의심하는 것은 되돌릴 데가 없다. 애매한 구간은
  `unclear` 로 두고 단정하지 않는다
- 사진이 없거나 대조에 실패하면 **`identity` 가 아예 안 온다.** 서식에 사진이
  빠졌다고 면접이 막히지 않는다

**서류 주장 ↔ 면접 발언 대조 (`findings`)** — 설계 §5-6 · [ADR-0026](../03_decision/0026-AI-면접-음성분석-제외.md) 결정 3 (2026-09-10).

"거짓말 탐지" 를 목소리가 아니라 **대조**로 한다. 이력서·자기소개서에 쓴 주장과
면접에서 한 말을 맞춰 보고, 어긋나면 **양쪽 원문을 인용해** 보여 준다.

- **`finish` 가 뒤에서 만든다.** 여기서 sLLM 을 기다리면 끝내기 요청이 몇십 초
  멈춘다 — 지원자는 이미 다 답했는데 화면만 붙잡힌다. 담당자 화면은 잠시 뒤
  새로고침하면 채워져 있다
- **점수가 없다.** 갈래는 `consistent` · `inconsistent` · `unverified` 셋뿐이고
  판단은 면접관이 한다 (ADR-0003). 합불에 곱해지는 수치를 만들지 않는다
- **양쪽 인용을 코드가 검증한다.** 주장은 서류에, 답변은 전사에 글자까지 같아야
  통과한다. 모델이 의역하거나 지어내면 **버린다** — 면접관이 서류에서 그 문장을
  못 찾으면 대조가 성립하지 않고, 지원자는 하지도 않은 말로 대조당한다
- `unverified` 는 **답변 칸이 빈다.** 없는 답을 지어내지 않는다 — 빈 칸이 곧
  "이건 못 물어봤다" 는 정보다
- 다시 돌리면 **지우고 새로 만든다.** 같은 주장이 두 줄로 쌓이면 어느 쪽이
  최신인지 모른다

**전사는 면접 진행을 막지 않는다** (2026-09-09).

전에는 지원자가 전사가 끝날 때까지 화면 앞에서 기다렸다. t3.large(2 vCPU)에서
36초 답변 전사가 25.4초라 **동시 3명이 한계**였고, 그 이상이면 지원자 화면이
"처리 중"에서 멈췄다. 진짜 문제는 3명이 아니라 **몇 명이 올지 미리 맞춰야
한다는 것**이다 — 쓰는 회사가 늘면 맞출 수가 없다.

- 워커가 시작할 때 `/internal/.../questions` 로 질문을 다 받아 두고, 말이 끝나면
  **다음 질문을 바로 보낸다.** 전사는 뒤에서 돌다가 끝나면 `seq` 를 붙여 저장한다
- 밀려도 면접은 안 멈춘다. **담당자가 글을 몇 초 늦게 볼 뿐**이다
- 잃은 것: 전사가 비었을 때의 **"다시 답변해 주세요"**. 다음 질문이 이미 나간
  뒤라 되물을 수 없다 — 그 칸은 빈칸으로 남고 담당자가 보고 판단한다

## 백그라운드 (HTTP 아님)

- **메일 워커** (G2·G3): SQS 폴링 → SES 발송 → `email_logs.status` 갱신, 실패 시 재시도
