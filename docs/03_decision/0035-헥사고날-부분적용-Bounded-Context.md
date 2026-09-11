# ADR-0035. 헥사고날 부분 적용 · Bounded Context 로 다중 스타 · Full DDD 는 안 한다

> **상태: 확정 · 2026-09-12** · 작성 인프라·총괄(suvisdev). 개정 경로: 오너가 개정 ADR 을 쓰면 바뀐다 ([03-conventions](../00_overview/03-conventions.md) "결정 문서 개정").
> **개정 대상 없음**. 새 규약. 기존 ADR-0024·0031·0032 (sLLM 로컬 모델) 는 그대로.
> **연계**: [01-erd.md](../00_overview/01-erd.md) 는 스키마 단일 계약 · 이 ADR 은 코드 조직 계약. 두 계약을 동시에 만족해야 한다.

## 문제

`backend/app/` 는 레이어 분리 없이 22개 라우터 · 23개 SQLAlchemy 엔티티 (`models.py` 1,137 줄) · 도메인 로직 · 인프라 어댑터가 한 패키지에 평평하게 놓여 있다. 이 구조가 다음 통증을 낳는다:

- **`app.models` 가 71개 파일에서 89회 import** — 스키마 변경 파급이 파악 어렵고, ORM 이 곧 도메인이라 SQLAlchemy 학습 곡선이 도메인 이해 곡선과 얽힌다.
- **라우터가 500~900 줄** (interviews 885 / agent 698 / schedules 569) — FastAPI 라우터가 유스케이스를 직접 조립해 서비스 계층이 없다. 단위 테스트가 라우터 통합 테스트로 몰린다.
- **`screening.py` · `stages.py` · `stage_service.py` 삼각 결합** — "단계 전이" 하나가 세 파일에 흩어져 있어 규칙 개정 시 세 곳을 동시에 고쳐야 한다.
- **LLM 백엔드 스위치 (`AGENT_FINDINGS_BACKEND=anthropic`) 는 반쪽** — 환경변수로 갈아치우지만 인터페이스 승격이 안 돼 A/B·프로바이더 혼용이 코드에 박혀 있다.

한편 `agent/backends/` 는 이미 `ChatBackend` · `StreamingChatBackend` · `ToolRunner` Protocol 로 Ports & Adapters 를 쓰고 있어 여기만 계층화돼 있다.

## 결정

**헥사고날 부분 적용 · 라이트웨이트 DDD (Repository + Bounded Context + Ubiquitous Language)** 로 간다. Full DDD 와 단일 스타 온톨로지는 **버린다**.

### 1. 채택 (Adopt)

- **Ports & Adapters (헥사고날)**: `app/ports/output/*_port.py` (ABC) + `adapter/outbound/{pg,llm,mail,s3}/*` (구현). 지금 `agent/backends/base.py` 의 Protocol 패턴을 전 도메인에 확장한다.
- **Repository 패턴**: `models.py` 를 71개 파일이 직접 참조하는 결합을 해체한다. 도메인별 Repository ABC → `PgRepository` 구현.
- **Bounded Context = 다중 스타**: Arda 는 자연 허브가 4개 (JobPosting · User · Application · InterviewSession). 하나의 스타로 몰면 왜곡되므로 **4개 컨텍스트 각자 자기 스타**.
  - **Hiring** ★ JobPosting (company · stages · screening_rules)
  - **Talent** ★ User (resume · profile · auth · notifications)
  - **Application** ★★★ Application (screening_scores · stage_history · decisions · mail_logs · agent_traces) — 가장 큰 스타 · 워크플로 축
  - **Interview** ★★ InterviewSession (turns · probes · findings · scores · audio_segments · lie_analysis)
- **Use Case 분리 (대형 라우터에만)**: interviews (885) · agent (698) · schedules (569) 세 라우터만 `app/use_cases/*_interactor.py` 로 뽑는다. 그 외 라우터는 그대로 둔다.
- **Ubiquitous Language**: 컨텍스트별 용어 사전 (예: Application 의 `status` 와 InterviewSession 의 `state` 를 다르게 유지, 지금은 뒤섞임). 상세는 팀 워크샵 이후 별도 문서.

### 2. 거부 (Reject)

- **Full DDD 파편**: Aggregate Root 명시 / Domain Events / Event Sourcing / Value Object 전면 도입 — Arda 의 CRUD + 워크플로 성격에 오버. Score 같은 몇 개 VO 는 필요 시 도입하되 전면 도입 금지.
- **DTO ↔ Pydantic Schema 이중 레이어**: Arda 는 Pydantic 하나로 충분하다. 22개 라우터 × 20개 스키마를 이중화하면 스키마를 고칠 때마다 두 곳을 고쳐야 하고, 어긋나면 런타임에만 드러난다.
- **grpc · websocket · scheduler 폴더 미리 생성 금지**: 현재 Arda 는 REST + (별도 서비스로 분리된) WS + worker.py 뿐. `adapter/inbound/api/` 만 만든다. WS·worker 어댑터는 실제 흡수할 때 그때 만든다.
- **단일 중심 스타 토폴로지**: Arda 에는 자연 허브가 4개다 (지원자·면접·공고·사용자). 하나로 몰지 않는다.
- **`domain/entities/` 순수 dataclass 를 ORM 과 별도 보관**: `Entity.from_orm(orm)` 식 팩토리로 분리하면 매핑 코드가 배로 늘고 얻는 것은 순수성뿐이다. Arda 는 SQLAlchemy 2.0 `mapped_column` 모델을 그대로 도메인으로 쓰고, 컨텍스트는 파일·폴더 이름으로만 표기한다.

### 3. 파일·폴더 규약

```
backend/app/
├── main.py, db.py, deps.py, security.py, logging_conf.py, errors.py
├── models.py                   ← 그대로 유지 (facade). 컨텍스트별 파일로 분해는 Phase 5 이후 선택.
├── schemas/                    ← Pydantic (그대로)
├── api/                        ← 라우터 (그대로)
│
├── ports/
│   ├── output/                 ← ABC · 도메인이 요구하는 밖의 계약
│   │   ├── application_repository.py
│   │   ├── interview_repository.py
│   │   ├── llm_port.py         ← agent/backends/base.py 에서 승격
│   │   ├── mail_port.py
│   │   └── s3_port.py
│   └── input/                  ← ABC · 밖이 도메인을 부르는 계약 (선택 · 대형 라우터에만)
│       ├── interview_use_case.py
│       ├── agent_use_case.py
│       └── schedule_use_case.py
│
├── use_cases/                  ← Input Port 구현 · 대형 라우터에서 뽑은 오케스트레이션
│   ├── interview_interactor.py
│   ├── agent_interactor.py
│   └── schedule_interactor.py
│
└── adapter/
    ├── outbound/
    │   ├── pg/                 ← *_pg_repository.py (Repository 구현)
    │   ├── llm/                ← anthropic_backend.py, ollama_backend.py 이관
    │   ├── mail/               ← ses_adapter.py
    │   └── s3/                 ← s3_adapter.py
    └── inbound/                ← 지금은 만들지 않는다 (기존 api/ 유지)
```

**중요**: `agent/`, `screening.py`, `stages.py`, `stage_service.py` 등 기존 파일은 **삭제·이동 없이** Phase 1 부터 차차 안쪽을 Repository/UseCase 로 밀어 넣고, 껍데기만 남으면 그때 제거한다. **모든 리팩터는 파일 삭제 없이 단계적으로 가고, 각 Phase 는 스스로 CI 초록·main 배포 가능** 이어야 한다.

### 4. Phase 순서 (되돌리기 쉬운 순 → 어려운 순)

- **Phase 0 · LLM Port 승격** (반나절 · 최소 리스크) — `agent/backends/base.py` 의 Protocol 을 `app/ports/output/llm_port.py` 로 옮기고 `agent/backends/` 를 `adapter/outbound/llm/` 로 이관. import path 만 갈아치우고 로직 손대지 않는다. **이 ADR 커밋과 함께 이번 PR 에 포함.**
- **Phase 1 · Application 컨텍스트 Repository** (반나절-하루) — `application_repository.py` (ABC) + `application_pg_repository.py` (구현). `screening.py` · `stage_service.py` 가 `models.Application` 직접 접근하는 부분을 Repository 로 감싼다. models.py 는 유지.
- **Phase 2 · 대형 라우터 3개 UseCase 분리** (선택 · 1-2일) — `interviews.py` · `agent.py` · `schedules.py` 를 라우터 (얇게) + UseCase (두껍게) 로 나눈다. 라우터는 파싱·검증·반환만.
- **Phase 3 · 나머지 컨텍스트** (미정) — Hiring · Talent · Interview Repository. 각 도메인 오너가 자기 시점에 진행.
- **Phase 4+ · Ubiquitous Language 정착** (팀 워크샵 후) — 용어 사전 · Bounded Context 간 참조 규약 (예: 컨텍스트를 넘길 때 엔티티 대신 `UserId` 같은 식별자만 넘긴다) 등.

### 5. 오너 · 게이트 · 개정

- 코드 리팩터는 **각 컨텍스트 오너 자율** ([04-team.md](../00_overview/04-team.md) 표). 팀장 게이트 없음. 오너가 자기 도메인 안에서 Repository 패턴을 도입하거나 UseCase 를 뽑는 판단을 스스로 한다.
- **컨텍스트 경계 변경**은 팀 채널 사후 공지. 예: Application 스타에 `agent_traces` 넣을지 별도 축(Observability) 로 뺄지.
- 이 ADR 개정은 오너가 개정 ADR 을 쓰면 바뀐다.

## 대안과 버린 이유

- **Full DDD 전면 도입** (Aggregate Root · Domain Events · Entity/ORM 분리 · DTO 이중화) — 팀 4명 규모·발표 임박·auto-CD 리스크 대비 비용이 이득을 초과. 지금 아프지 않은 곳에 넣은 장치는 그대로 유지비가 된다.
- **Clean Architecture 4층 엄격 (Entity → UseCase → Adapter → Framework)** — AI 운용 관점 이득은 Ports & Adapters (§1 채택 항목) 에서 이미 취함. 4층 분리는 순수성만 챙기고 AI 관점 추가 이득 없음.
- **단일 스타 온톨로지 (하나의 aggregate root 로 모든 것 방사)** — 자연 허브가 하나인 도메인이면 쉽지만 Arda 는 4개다. 하나로 몰면 나머지 3개가 위성으로 왜곡된다.
- **일괄 대규모 리팩터 (전 라우터·엔티티 한 PR)** — main auto-CD (2분 후 프로덕션) 환경에서 폭발 반경 위험. Phase 단위로 CI 초록·머지 가능하게 자른다.

## 검증

- 각 Phase 는 **기존 API 응답이 동일** (스키마·상태코드·본문) 함을 통합 테스트로 확인. Repository 도입 자체는 관측되는 행동을 바꾸지 않는다.
- Phase 0 완료 시 `pytest backend/tests/` 초록 · CI 초록 · main 머지 후 프로덕션 배포 정상 동작 확인.
- Phase 1 이후 `screening_pg_repository.py` 를 mock 으로 갈아치운 유닛 테스트 최소 3건 추가 (Repository 패턴 이득 증명).

## 참고

- `agent/backends/base.py` — 이미 존재하는 Protocol 기반 Port 패턴. Phase 0 의 출발점.
- ADR-0032 (추론 모델 3종 확정) — LLM Port 승격의 사용처 (Anthropic ↔ Qwen Ollama 스위치).
