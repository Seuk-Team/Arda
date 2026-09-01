# 에이전트 도구 스펙

> **상태**: 확정 v1.1 (2026-08-26) · 오너 suvisdev  
> **원칙**: [ADR-0003](../../docs/03_decision/0003-ai-추천만.md) — AI는 추천까지, 확정은 사람.  
> **UI 진입**: [ADR-0009](../../docs/03_decision/0009-에이전트-UI-위치.md) 확정 — ⌘K 콘솔 + 확인 카드.  
> **API 목록**: [02-api.md](../../docs/00_overview/02-api.md) — 도구는 **기존 REST/서비스 레이어를 재사용**한다. 권한 우회 경로를 만들지 않는다.

## 1. 분류

| 종류 | 확인 단계 | 예시 |
|---|---|---|
| **읽기** | 없음 — 바로 실행·결과 표시 | 검색·상세·공고 목록 |
| **쓰기** | **필수** — 실행 전 사용자 확인 | 단계 변경 · 면접관 배정 · 메일 초안 |
| **제외** | — | 최종 합불 자동 확정 · SES 실발송 · 스키마/권한 변경 |

쓰기 확인 카피 예: `김도현을 서류 검토로 옮길까요? [취소] [확인]`  
메일은 **초안(`draft_email`) + 발송(`send_email`)** 둘 다 도구 범위다 (G4). 발송은 확인 게이트를 반드시 지나고, 수신자는 지원자 본인으로 고정된다 — 도구가 주소를 인자로 받지 않는다.

## 2. 도구 목록 ↔ API 매핑

에이전트 런타임은 동일 프로세스에서 DB 세션을 직접 사용한다 (HTTP 호출 아님).  
아래 매핑 열은 **동등한 REST 엔드포인트** — 같은 서비스 레이어·같은 권한 검사를 탄다.  
JWT는 현재 요청의 것을 그대로 전달 — 에이전트가 별도 슈퍼유저 토큰을 갖지 않는다.

### 읽기 도구

| 도구명 | 하는 일 | 동등 REST | 비고 |
|---|---|---|---|
| `search_applications` | 이름·이메일·단계 + **역량 기반 시맨틱 검색**으로 지원자 찾기 | `GET /api/v1/applications?q=&stage=` | H1·H2. 전역 검색 경로 사용. `semantic` 은 §2.1 |
| `get_application` | 지원자 상세 (프로필·AI 요약·평가·이력·파일·메모 수) | `GET /api/v1/applications/{id}` | D4. 평가·이력·메모를 한 번에 반환하므로 개별 조회 도구 불필요 |
| `list_postings` | 채용공고 목록 + 공고별 지원자 수 | `GET /api/v1/postings` | 공고 이름 → posting_id 변환에 사용 |
| `search_users` | 내부 사용자(면접관·어드민) 이름·이메일 검색 | `GET /api/v1/users?q=` | 면접관 이름 → user_id 변환에 사용 |
| `list_availability` | 면접관의 가용 시간(면접 가능한 시간대) 조회 | `GET /api/v1/availability?interviewer_id=` | 일정 제안 전 빈 시간 확인용 |
| `get_schedule_status` | 지원자의 면접 일정 제안 상태 조회 | `GET /api/v1/schedules/status/{application_id}` | none/proposed/confirmed/expired/canceled |
| `list_interviews` | 확정된 면접 일정 목록 조회 | `GET /api/v1/schedules/interviews` | 기간 필터, mine=true로 내 면접만 조회 가능 |

### 2.1 `search_applications` 반환 계약 (ADR-0021)

리스트가 아니라 **dict** 를 돌려준다. 검색이 온전히 돌았는지를 아르가 알아야 하기 때문이다.

```json
{ "results": [...], "count": 3, "search_mode": "semantic+keyword", "note": "..." }
```

| `search_mode` | 뜻 | 아르가 해야 할 것 |
|---|---|---|
| `semantic+keyword` | 벡터 + 키워드 둘 다 돔 | 그대로 답한다 |
| `keyword_fallback` | **벡터가 못 돌아 키워드로만 찾음** (pgvector·모델·임베딩 없음, 임계값 밖) | 0건이어도 "없습니다" 로 단정 금지. `note` 를 전달 |
| `lexical` / `all` | 이름·이메일 검색 | 그대로 답한다 |

결과 항목의 `matched_by` 는 `both` > `semantic` > `keyword` 순 신뢰도이고, `similarity`(0~1)는
벡터에 걸린 건에만 붙는다. 정렬은 이미 이 순서다.

**임계값**: 두 겹이다. 절대 상한 `SEMANTIC_MAX_DISTANCE`(기본 0.70) + 1등 기준 상대 창
`SEMANTIC_RELATIVE_WINDOW`(기본 0.15). 절대 상한 하나로는 안 걸러진다 — 실측 근거는
`embedder.py` 임계값 주석.

**병합**: 벡터 결과 ∪ 키워드 결과, id 중복 제거. 키워드는 이름·이메일뿐 아니라
스킬·자기소개서·학력까지 본다 — 그래야 벡터가 죽어도 "Python 경험자" 가 걸린다.

**임베딩 입력**: 스킬 + 학력 + 경력. **자기소개서는 넣지 않는다** — 모델
`max_seq_length` 가 128토큰이라 자소서를 넣으면 잘린 상투구가 벡터를 지배해 순위가
망가진다(ADR-0021 구현 메모). 자소서는 키워드 쪽이 계속 훑는다. 되돌리려면
`EMBEDDING_INCLUDE_INTRO=1`.

**백필**: `python -m app.agent.embedder`(`--dry-run` 으로 대상 건수만, `--force` 로 전건 재생성).
서버 기동 시 자동 실행하지 않는다 (ADR-0011 비용 가드). `model_name` 에 모델 + 입력 규칙
버전(`.../text-v2`)을 적어두므로, 규칙이 바뀌면 백필이 낡은 벡터를 알아서 다시 만든다.

**주의**: `sentence-transformers`·`pgvector` 가 컨테이너에 없거나 DB 에 `vector` 확장이
없으면 시맨틱 검색은 조용히 꺼지고 키워드 폴백만 돈다. 배포 후 실제로 벡터가 도는지는
`search_mode` 값으로 확인한다.

### 쓰기 도구 (확인 필수)

| 도구명 | 하는 일 | 동등 REST | 확인 후 동작 |
|---|---|---|---|
| `change_stage` | 단계 변경 | `PATCH /api/v1/applications/{id}/stage` | 이력 기록(D5) + 메일 큐 트리거. **확인 없이 실행 금지** |
| `assign_interviewer` | 면접관 배정 | `POST /api/v1/applications/{id}/interviewers` | 어드민만 가능 (ADR-0017). 중복 배정은 무시 |
| `create_schedule_proposal` | 면접 일정 후보 제안 | `POST /api/v1/schedules/proposals` | 면접관 배정 + 가용 시간 등록 선행 필요 |
| `draft_email` | 이메일 **초안** 생성 | `GET /api/v1/email-templates` 와 같은 문구 | **확인 불필요** — 부수효과가 없다. 설정 화면에서 편집한 문구를 그대로 쓴다 |
| `send_email` | 이메일 **발송** | `POST /api/v1/applications/{id}/emails` | 확인 카드에 수신자·제목·본문 전문 표시 → 승인 시 `email_logs(stage=custom, actor_kind=agent)` 생성 + 큐 발행. 서명은 "채용 에이전트 아르 드림" |

### 에이전트 전용 HTTP

| 메서드 | 경로 | 기능 | 구현 |
|---|---|---|---|
| POST | `/api/v1/agent/chat` | 자연어 → 도구 계획·실행 로그 반환 (읽기 즉시 / 쓰기는 pending_action) | ✅ M3 |
| POST | `/api/v1/agent/confirm` | 대기 중 쓰기 도구 실행 확정 | ✅ M4 |
| POST | `/api/v1/agent/applications/{id}/summarize` | AI 요약 재생성 (담당자 이상) | ✅ M2 |

## 3. 데모 문장 → 도구 분해

> "Python 2년 이상이고 AWS 경험 있는 사람 서류 합격 처리하고 안내 메일 초안 써줘"

| 단계 | 도구 | 종류 |
|---|---|---|
| 1 | `search_applications` (q≈Python,AWS · stage=applied) | 읽기 |
| 2 | (결과 0명이면 중단·안내) | — |
| 3 | `change_stage` → **확인 카드** → 확인 시 서류심사(`screening`) | 쓰기 |
| 4 | `draft_email` (purpose=interview) → 초안 표시 | 읽기(초안) |
| 5 | `send_email` (승인 후) → 발송 | 쓰기(확인 필수) |

실행 로그는 UI(⌘K 콘솔, ADR-0009)에 그대로 노출 — 면접 스토리용.

## 4. 가드

1. **환각**: 응답·요약은 도구 결과·추출 텍스트만 인용. 없는 지원자 id를 만들어내지 않음.
2. **권한**: 조회는 전원 허용, 배정은 admin 전용 (ADR-0017). 권한 에러면 도구 실패로 로그하고 중단.
3. **비용**: 더미 10만 건 루프에 LLM 호출 금지 ([agent.md](../../docs/01_role/agent.md) §3).
4. **쓰기 테스트**: "확인 없이 `change_stage`가 실행되면 실패" 단위 테스트로 강제.
5. **라운드 제한**: 도구 호출 최대 10회. 초과 시 안내 메시지 반환.

## 5. 구현 현황

| 마일스톤 | 범위 | 상태 |
|---|---|---|
| M1 | 이력서 텍스트 추출 PoC | ✅ PR #76 |
| M2 | 요약 파이프라인 (`summarizer.py` + `/summarize` API) | ✅ PR #83 |
| M3 | 읽기 에이전트 (`runtime.py` + `/chat` API + 읽기 도구 7개) | ✅ PR #83, #151, #153 |
| M4 | 쓰기 도구 + 확인 메커니즘 (`/confirm` API + 쓰기 도구 4개) | ✅ PR #83 |

**남은 작업**: 프롬프트 튜닝 (W3) · 단위 테스트 · E2E 데모 시나리오 (API 키 필요)

## 6. 열린 질문

- [x] 전역 검색 경로 — `GET /api/v1/applications` 구현됨 (search 라우터)
- [x] `change_stage` body 필드명 — `application_id` + `to_stage` 확정
- [ ] 메일 초안을 저장할지(임시 테이블) vs UI 세션만인지
