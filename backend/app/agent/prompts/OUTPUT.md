# 요약 출력 규약

> **상태**: 초안 (2026-08-24) · 오너 suvisdev · W2 M1
> **선행**: [ADR-0003](../../../../docs/03_decision/0003-ai-추천만.md) 추천까지만 · [ADR-0011](../../../../docs/03_decision/0011-에이전트-모델-비용.md) 모델·비용 · [05-design.md](../../../../docs/00_overview/05-design.md) 요약문 배치 규칙

LLM이 무엇을 어떤 모양으로 돌려줘야 하는지 정한다. 프롬프트 파일(`*.v*.md`)은 이 규약을 참조만 하고, 규약이 바뀌면 프롬프트 버전을 올린다.

## 1. 이력서 요약 — 3단계 프롬프트 체이닝 (ADR-0022)

기존 단일 프롬프트(`summarize.v1`)를 3단계 파이프라인으로 교체했다.

### 파이프라인

| 단계 | 프롬프트 | 입력 | 출력 |
|------|----------|------|------|
| Step 1 요약 | `chain_summarize.v1` | 이력서 + 자기소개서 | 프로필 요약 (gist, key_skills, key_experiences) |
| Step 2 평가 | `chain_evaluate.v1` | Step 1 결과 + 공고 요건 | 적합도 (fit_score, fit, concerns) |
| Step 3 추천 | `chain_recommend.v1` | Step 2 결과 + 공고 제목 | 다음 액션 (action, reasons, check_points) |

각 단계는 이전 단계의 **검증된 JSON 출력**만 입력으로 받는다.
Step 1에서 `insufficient: true`이면 Step 2·3을 건너뛴다.

### 통합 출력 형식

3단계 결과를 합산한 JSON을 `ai_summary`에 저장한다.

```json
{
  "insufficient": false,
  "gist": "자소서 요지 3~5문장",
  "key_skills": ["핵심 역량 (최대 5개)"],
  "key_experiences": ["주요 경력·프로젝트 (최대 3개)"],
  "fit_score": 3,
  "fit": ["공고 요건 대비 적합 지점 (최대 3개)"],
  "concerns": ["확인 필요 지점 (최대 3개)"],
  "recommendation": {
    "action": "면접 권유 | 추가 확인 | 보류",
    "reasons": ["제안 근거 (최대 3개)"],
    "check_points": ["면접 시 확인 포인트 (최대 3개)"]
  }
}
```

| 필드 | 타입 | 출처 | 규칙 |
|---|---|---|---|
| `insufficient` | bool | Step 1 | 근거 부족 시 `true`, 나머지 필드 빈 값 |
| `gist` | string | Step 1 | 자기소개서 요지. **3~5문장**, 평서체 |
| `key_skills` | string[] | Step 1 | 제출물에서 확인된 핵심 역량. **최대 5개** |
| `key_experiences` | string[] | Step 1 | 주요 경력·프로젝트. **최대 3개** |
| `fit_score` | int(1~5) | Step 2 | 공고 요건 대비 적합도 점수 |
| `fit` | string[] | Step 2 | 적합 지점. **최대 3개**, 각 1문장 |
| `concerns` | string[] | Step 2 | 우려 지점. **최대 3개**, 각 1문장 |
| `recommendation.action` | string | Step 3 | "면접 권유" / "추가 확인" / "보류" |
| `recommendation.reasons` | string[] | Step 3 | 제안 근거. **최대 3개** |
| `recommendation.check_points` | string[] | Step 3 | 면접·추가 확인 시 질문 포인트. **최대 3개** |

### 하위 호환

`gist`, `fit`, `concerns` 필드는 기존과 동일한 위치에 유지된다.
기존 프론트엔드 코드가 이 3개 필드만 쓰고 있다면 변경 없이 동작한다.

### 저장 방식

- `ai_summary`: 통합 JSON 문자열
- `ai_summary_at`: 생성 시각
- `ai_summary_model`: `{모델명}/{step1_tag+step2_tag+step3_tag}` (예: `claude-haiku-4-5-20251001/chain_summarize.v1+chain_evaluate.v1+chain_recommend.v1`)
- `insufficient: true`이면 Step 1 결과만 저장하고 나머지는 빈 값

### 비용

Haiku 3회 호출. 각 단계 max_tokens=500. 건당 총 비용은 기존 1회 호출 대비 약 2~3배이나, Haiku 단가가 낮아 건당 수 원 수준.

### 내용 금지 사항

1. **지원 정보 필드와 겹치는 나열 금지.** 요건과 **대조하는 문장**은 허용.
2. **합불 판정 금지.** recommendation.action은 **제안**이다. "합격시켜라"가 아니다 (ADR-0003).
3. **원문에 없는 내용 금지.** 추론으로 경력·성과를 만들지 않는다.
4. **민감정보 금지.** 주민번호·주소·연락처·생년월일·가족사항.
5. **차별 소지 항목 금지.** 성별·나이·출신 지역·혼인 여부.

### 검증

단계별 JSON 파싱 실패 시 해당 단계를 빈 값으로 채우고 다음 단계를 계속 진행한다.
Step 1 파싱 실패 시에만 전체를 `insufficient: true`로 처리한다.
요약 실패가 지원 접수를 막지 않는다 (ADR-0011 §5).

## 2. 도구 호출 (`tool_agent`)

도구 호출은 벤더 tool-calling 기능을 쓰고, 프롬프트는 **무엇을 하면 안 되는지**만 규정한다. 도구 목록·스키마는 [TOOLS.md](../TOOLS.md)가 원본이다.

| 상황 | 출력 |
|---|---|
| 읽기 도구로 답할 수 있음 | 도구 호출 → 결과 인용한 한국어 답변 |
| 쓰기 도구가 필요함 | 도구를 **호출하지 말고** 무엇을 바꿀지 문장으로 제시 → 런타임이 확인 카드 표시 → 사용자 확인 후 실행 |
| 결과 0건 | 추측하지 말고 "해당 없음"과 사용한 조건을 밝힌다 |
| 권한 부족(403) | 실패로 보고하고 중단. 다른 경로로 우회하지 않는다 |
| 도구로 얻을 수 없는 질문 | 모른다고 답한다. 지원자 id·이름을 지어내지 않는다 |

실행 로그(어떤 도구를 어떤 인자로 불렀는지)는 UI에 그대로 노출한다 — 감사 근거이자 발표 소재다.

## 3. 버전 관리

- 프롬프트 파일명은 `<이름>.v<번호>.md`. 내용을 고치면 번호를 올리고 이전 파일을 남긴다.
- 호출 시 `prompts.render()`가 돌려주는 버전 태그(예: `summarize.v1`)를 토큰 사용량 로그에 함께 남긴다(ADR-0011 §3-2).
- 이 규약의 "내용 금지 사항"이 바뀌면 반드시 프롬프트 버전을 올린다. 규약만 고치고 프롬프트를 두면 저장된 요약과 규약이 어긋난다.
