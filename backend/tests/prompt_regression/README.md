# 회귀 하네스 — 아르 채팅 시나리오

아르 채팅(담당자·지원자)을 실 백엔드에 실호출해 성공률·응답 시간·라우팅 정확도를 기록한다. 라우터·프롬프트·모델 변경 후 이 하네스를 다시 돌려 개선/회귀를 숫자로 본다.

**오너 (2026-09-04 팀 재배정)**: 수택 (`suvisdev`, 팀장). 하네스 자체는 팀장 소유. 에이전트 도메인 담당(박소연 `클로버키`)이 라우터·프롬프트 편집한 뒤 결과 diff 를 팀장에게 공유하는 흐름.

세 파일:
- `test_step0.py` — 정형 시나리오 10개 (인사·검색·단계 변경·확인 응답·메일·일정). 3a→4a 는 실제로 단계를 바꾸므로 전후에 김도현(id=1) 을 `screening` 으로 리셋한다
- `test_intent_variations.py` — **표현 변형 30개** (존칭·오타·존댓말·조사 변형). 의도 라우터의 채택 기준을 재는 파일. 쓰기 의도는 확인 카드까지만 만들고 실행하지 않는다
- `test_faq.py` — **FAQ 파이프 15개** (지원자용 공개 챗, `POST /public/schedule/{token}/faq`). 담당자 채팅과 별개 파이프(`app.agent.faq.answer_question`, stateless·도구 없음). 공고 답변 5 + 본인 상태 2 + 차단 5 + 미명시 1 + 프롬프트 주입 2. 실행 전 스케줄 제안이 DB 에 하나는 있어야 한다(없으면 skip)

**채택 기준** (2026-09-02 결정): 다른 레코드 쓰기 0 · 창작 이름 0 (둘 다 assert) · 의도 오분류 ≤5% · 라우팅 p50 ≤4s(참고치). LLM 라우터 실측: 30/30 정답, 구조 위반 0/70, p50 5.1s.

## 🚫 대상 백엔드 — 로컬만

이 하네스는 **로컬 백엔드(`http://localhost:8000`)를 대상으로만** 돌린다. `REGRESSION_BASE_URL` 을 운영 주소(`https://api.seuk.suvisdev.cloud`)로 넘겨도 API 자체는 응답하지만 **절대 그렇게 쓰지 말 것**:

- 09-04 인프라 이관으로 `document_anchors` 가 **DB 트리거로 추가 전용**이 됐다. 하네스가 만든 테스트 지원서·평가·메시지가 프로덕션 DB 에 영구히 남는다 (07-deploy·ADR-0028 참고)
- 운영은 `main` merge → 2분 systemd 자동배포. 프로덕션에서 회귀 재는 도구가 아니다
- 라우터·프롬프트 편집은 로컬에서 결론 낸 뒤, PR 로 올려 자동배포로 흘려보낸다

⚠️ **리셋은 `backend/.env` 의 DATABASE_URL 을 직접 읽는다.** `app.db` 는 env 가 없으면 `localhost:5432/postgres` 기본값으로 떨어지는데 이 PC 에는 네이티브 PostgreSQL 이 5432 에 살아 있어, 그대로 두면 엉뚱한 옛 DB 를 조용히 바꾼다 (실제로 겪었다). 로컬 pgvector 컨테이너는 5433 이다.

## 왜 기본 스위트 밖인가

- 실 백엔드 실호출 → 시나리오 하나당 5~40초, 로컬 sLLM 이면 더 오래
- CI 매 PR 마다 몇 분씩 밀리게 되어 부담
- **`@pytest.mark.regression`** 마커가 붙어 있고, `conftest.py` 가 기본 실행에서 자동 제외한다

## 사전 준비

1. `arda-pgvector` 컨테이너 기동: `docker start arda-pgvector` (**로컬 5433**)
2. 백엔드 실행 — `backend/.env` 의 `AGENT_*_BACKEND` 스위치로 검증하고 싶은 쪽을 선택
   - **`ollama` → 로컬 Ollama sLLM (qwen3:4b) · 하네스 기본**
   - 비움 (or `anthropic`) → Anthropic Haiku (운영 기본) · **기본으로 skip** — 옵트인 필요 (아래 실행 옵션)
3. 시드 지원자 (16명) 존재 확인 — 최소한 김도현 (id=1)
4. 검증 계정 존재 — `ollama-test@example.com` / `testpass123` / role=admin
   - 없으면 `REGRESSION_EMAIL` · `REGRESSION_PASSWORD` env 로 다른 계정 지정

## 실행

```bash
cd backend
uv run pytest -m regression tests/prompt_regression -q
```

옵션:

- `REGRESSION_BASE_URL=http://localhost:8000` — **기본값, 이 값 외에는 쓰지 말 것** (상단 "로컬만" 경고 참고)
- `REGRESSION_TAG=baseline` — 결과 파일명 태그 (기본 `run`)
  - 예: `baseline`, `router-v1`, `qwen3-4b-instruct`, `haiku-3-5`
- `REGRESSION_ALLOW_ANTHROPIC=1` — **Anthropic 백엔드로 하네스 재실행 옵트인**. 없으면 conftest 의 `_guard_anthropic_backend` 가 `AGENT_CHAT_BACKEND != ollama` 를 감지해 세션 전체를 skip 한다 (30~55회 API 콜·과금 방지)

## 결과 확인

각 실행마다 `results/{YYYYMMDD_HHMMSS}_{tag}.jsonl` 파일이 생긴다. 시나리오당 한 줄 JSON.

```jsonl
{"sid":"1a","desc":"인사","elapsed_sec":22.6,"input_tokens":6412,"output_tokens":58,"tool_calls":[],"pending":null,"fallback":false,"router_hit":false,"reply_len":68,"backend":"ollama","model":"ollama:qwen3:4b"}
{"sid":"1b","desc":"자기소개","elapsed_sec":7.8,"input_tokens":6414,"output_tokens":91,"tool_calls":[],"pending":null,"fallback":false,"router_hit":false,"reply_len":117,"backend":"ollama","model":"ollama:qwen3:4b"}
...
```

`results/` 는 `.gitignore` 로 커밋 안 된다 — 세션별 실측이라 형상 관리 대상 아님. 개선 비교는 파일 두 개를 diff/tally 해서 본다.

## 해석 요령

- **성공률** = `fallback: false` 비율
- **평균 시간** = `elapsed_sec` 평균 (첫 실행은 임베딩 모델 로드 포함이라 늘 첫 케이스가 오래 걸림)
- **router_hit** = 규칙 라우터가 잡은 시나리오 (Phase 1 LLM 분류 라우터 도입 후 `true` 등장 — PR #162)
- **tool_calls** = 도구 이름 리스트. 같은 도구 여러 번이면 폭주 가능성 (Guard 가 잡음)

## 기준선 (2026-09-02, PR #161 Guard 도입 후 · Ollama qwen3:4b)

| 지표 | 값 |
|---|---|
| 성공률 | 10/10 |
| 평균 시간 | 15초 |
| 최장 시간 | 23초 |
| 총 output_tokens | 1,458 |

Anthropic Haiku 기준선은 09-03 채팅 6.8초 · 요약 9.1초 실측 (별 세션에서 개별 측정). 하네스 30/70 종합 기준선은 09-04 이후 재측정 예정.
