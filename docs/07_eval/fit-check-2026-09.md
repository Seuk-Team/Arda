# 적합도 확인 — 회사에 맞는 사람을 아르가 앞에 세우는가 (2026-09-10)

> **왜.** 멘토링(2026-09-10) 2번 "다양한 이력서에서 요약이 나오는지(영어 포함)", 8번 "다른 직종이 지원했을 때 잘 나올지", 12번 "적합성 점수화". 지금까지 더미·평가 케이스가 전부 한국어 개발 직군이라 **회사 인재상에 맞는 사람을 데이터로 골라내는지** 실측이 없었다. 요강 두 개([06_company/01-채용요강-2026-09.md](../06_company/01-채용요강-2026-09.md))와 지원자 24명으로 확인한다.
>
> **무엇을 본다.** ① 서류 적합도 `fit_score`(1~5)·`fit`·`concerns`·추천 `action` 이 사람이 매긴 기대 등급(A/B/C)과 같은 순서로 나오는가 ② 정보가 부족한 지원서에 `insufficient` 로 실토하는가(지어내지 않는가) ③ 영어 이력서·비개발 직군·직무 교차 지원이 "무관/일부" 로 갈리는가 ④ 인재상(§8.1·§8.2 문화 신호)을 `concerns` 로 잡는가 ⑤ 아르 의미 검색이 "React 성능 최적화 해본 사람" 같은 문장에 맞는 사람을 앞에 세우는가.

## 코드로 먼저 확인한 것 (2026-09-10)

| 사실 | 근거 | 뜻 |
|---|---|---|
| 적합도 평가는 공고의 **`description` 한 칸만** 요건으로 읽는다 | `backend/app/agent/summarizer.py:95-96` `posting_requirements = posting.description` | 09-08 에 추가된 `requirements`·`preferred`·`benefits` 컬럼과 `company_profile`(회사 소개 표)은 평가에 안 들어간다. **요강을 description 에 통째로 넣어야** 요건 대조가 된다 |
| 평가 프롬프트는 "프로필에 있는 사실만, 대조하는 문장으로" | `backend/app/agent/prompts/chain_evaluate.v1.md` | 인재상은 프롬프트에 없다. description 에 [인재상] 절을 넣으면 요건의 일부로 대조된다(이번 실험이 그 효과를 잰다) |
| 이력서 파일이 없으면 폼 필드 + 자기소개서만으로 요약한다 | `summarizer.py:100-125` | 이번 데이터셋은 파일 없이 넣는다 — 짧은 자기소개(문가영·장우진)는 `insufficient` 가 정답 |
| 의미 검색 임베딩 입력은 이름·학력·경력·기술 (자소서 제외) | `backend/app/agent/embedder.py` (`EMBEDDING_INCLUDE_INTRO=0`) | "실패를 공개하는 사람" 같은 **문화 문장은 의미 검색으로는 못 찾는다.** skills 정확 일치가 최상위 신호 |
| 임베딩 모델은 한국어 전용 `ko-sroberta` | `embedder.py:29` | 영어 이력서(Emily Park·Daniel Kim)는 요약은 되지만 의미 검색 순위는 기대하지 말 것 |

**결론 미리**: "회사에 맞는 인재상" 을 잡는 힘은 지금 **서류 적합도 평가(description 대조)** 에 있고, 의미 검색은 기술 스택 매칭용이다. 아래 실험은 그 두 축을 따로 잰다.

## 데이터셋

`backend/scripts/fit_check/applicants.yaml` — 역할별 12명. 각 사람에 사람이 매긴 기대 등급과 근거가 있다.

| 유형 | 프론트 | 백엔드 | 무엇을 검증하나 |
|---|---|---|---|
| A 요건·우대·인재상 전부 | 한지우 · 오세린 · 윤하늘(경력 상한 초과) · Emily Park(영어) | 조민석 · 배수아 · 류성민(경력 상한 경계) · Daniel Kim(영어) | 4~5점이 나오는가, 경력 상한을 concerns 로 잡는가, 영어가 되는가 |
| B 일부 충족 | 김태호(경력 하한) · 박도윤(Vue) · 서지훈(Angular) | 임재원(SQLite·CI 없음) · 신예은(Java) · 오하람(데이터 엔지니어) · 백서준(경력 하한 미달) | 3점 근처, 부족한 요건이 concerns 에 정확히 적히는가 |
| B 기술은 충족, 문화는 충돌 | 강현우(승인 대기·완벽주의) | 남기훈(자기 도메인만·승인 라인) | **인재상 §8.2 를 concerns 로 잡는가** — 이 실험의 핵심 |
| C 직무 교차 | 이서연(백엔드→프론트) | 홍지민(프론트→백엔드) | "무관" 으로 갈리는가 |
| C 비개발 | 최유진(마케터) | 최유진(같은 사람) | 멘토링 8번 — insufficient 가 아니라 "요건 무관" 이어야 한다 |
| C 경력 없음 | 정민호(부트캠프) | — | 우대(공개 포트폴리오)만 있을 때 |
| 정보 부족 | 문가영("React 로 3년") | 장우진("파이썬 백엔드 4년") | `insufficient` 로 실토하는가 |

## 순서

1. **담당자**: 웹에서 공고 2개 등록. 제목·description·마감일은 요강 문서 "§ Arda description 에 붙여 넣을 것" 그대로. 공개 링크 발급. 공고 id 두 개를 확보(주소창 또는 목록).
2. **투입** (로그인 불필요, 누구나):
   ```bash
   cd backend
   .venv/Scripts/python.exe scripts/fit_check/submit.py --role frontend --posting <프론트 id>
   .venv/Scripts/python.exe scripts/fit_check/submit.py --role backend  --posting <백엔드 id>
   ```
   24명 × Claude 3회 = 72회 호출, Haiku 라 $0.2 안팎. 1~2분 기다린다.
3. **결과표** (담당자 계정, 비밀번호는 터미널이 직접 묻는다):
   ```bash
   .venv/Scripts/python.exe scripts/fit_check/report.py --role frontend --posting <프론트 id> --search "React 성능 최적화 해본 사람" --search "WebRTC 실시간 화면 만든 사람" --search "실패를 공개하고 문서로 결정하는 사람"
   .venv/Scripts/python.exe scripts/fit_check/report.py --role backend  --posting <백엔드 id> --search "FastAPI 와 PostgreSQL 튜닝 경험" --search "LLM 도구 호출 붙여 본 사람" --search "ADR 로 결정을 남기는 사람"
   ```
   결과는 `docs/07_eval/fit-check-results/<role>-<날짜>.md` 에 저장된다. 표의 `⚠` 가 기대와 다른 등급이다.
4. **판독**: 아래 표를 채운다.

## 판독 기준

| 질문 | 통과 기준 | 실패하면 고칠 곳 |
|---|---|---|
| A 4명이 4~5점인가 | 4명 중 3명 이상 | `chain_evaluate.v1.md` 점수 기준 문구 |
| C 6명이 1~2점 또는 "무관" 인가 | 6명 전부 3점 미만 | 같은 프롬프트. 마케터가 3점이면 "요건 대조" 규칙 강화 |
| 문화 충돌 2명(강현우·남기훈)의 concerns 에 승인·도메인 언급이 있나 | 2명 중 1명 이상 | description 의 [인재상] 절이 안 읽히는 것 → `_build_prompt_vars` 에 회사 §8.1·§8.2 별도 변수로 주입 |
| 정보 부족 2명이 insufficient 인가 | 2명 전부 | 지어냈다면 `chain_summarize` 의 insufficient 규칙 |
| 영어 2명이 A 인가 | 2명 전부 4점 이상 | 프롬프트에 "영어 입력도 한국어로 대조" 한 줄 |
| 경력 상한 초과(윤하늘·류성민)를 concerns 로 잡나 | 1명 이상 | description 의 경력 구간 표기 |
| 의미 검색 "React 성능 최적화" 상위 3에 한지우·Emily 가 있나 | 둘 중 하나 | skills 신호 확인. 영어는 기대 X |
| 의미 검색 "실패를 공개하고 문서로 결정" 이 A 를 앞에 세우나 | 기대: **못 세운다**(임베딩이 자소서를 안 봄) | 이건 결함이 아니라 설계. 문화 검색은 요약 JSON 의 fit/concerns 를 검색 대상에 넣는 확장이 필요 |

## 결과

(report.py 출력 붙일 것 — `fit-check-results/`)

## 정리 후 할 것

- 검증용 공고 2개는 `closed` 로 내린다(09-02 C7 실측과 같은 방식). 지원자 24명은 `fitcheck-` 접두어라 검색으로 골라 지울 수 있다.
- 발견이 있으면 에이전트 오너(cloverky)에게 넘긴다: ① `_build_prompt_vars` 가 `requirements`·`preferred`·회사 인재상을 읽게 ② 문화 검색을 위해 요약 fit/concerns 를 임베딩 입력에 포함할지.
