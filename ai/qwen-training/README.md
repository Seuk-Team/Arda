# Qwen3-8B QLoRA 학습 (아르 에이전트 · 로컬)

> **상태**: 2026-09-11 착수 · 오너 suvisdev
> **모델**: Qwen/Qwen3-8B-Instruct · 4-bit nf4 + LoRA r=16
> **GPU**: RTX 4060 8GB (로컬 · 학습만 · 시연은 AWS G4dn)
> **근거**: [ADR-0032](../../docs/03_decision/0032-추론-모델-3종-확정.md) · [ADR-0024](../../docs/03_decision/0024-sLLM-로컬-모델-전략.md)

## 왜 QLoRA 인가

Qwen3-8B 를 4-bit 로 로드하면 8GB VRAM 에 들어간다. LoRA 로 어댑터만 학습해 파라미터 극소·학습 시간 몇 시간·다시 어댑터만 배포한다. baseline 벤치(`infra/gpu/results/qwen3-8b-final-2026-09-08.json`) 20/17 통과에서 mail·multi_turn 카테고리를 끌어올리는 것이 목표.

## 학습 범위 (2026-09-11 사용자 확정)

Qwen 은 **아르(도구 호출)** 뿐 아니라 **면접 답변 처리 chain 전체** 를 커버:

| chain | 프롬프트 | 무엇 |
|---|---|---|
| **agent** | `agent.v1.md` | 자연어 → 도구 호출 (search·detail·write·mail) |
| **interview_probe** | `interview_probe.v3.md` | 서류에서 확인할 만한 주장 → 질문 |
| **interview_findings** | `interview_findings.v1.md` | 면접 후 전사↔서류 대조 (최대 8건) |
| **interview_findings_turn** | `interview_findings_turn.v1.md` | 답변 하나마다 즉시 대조 (최대 3건, #175 신설) |
| **interview_score** | `interview_score.v1.md` | 답변 점수 (answers_score 0~100) |

시연 서버 (AWS G4dn T4 16GB) 에 Ollama 로 올려 `AGENT_CHAT_BACKEND=ollama` 스위치 하나로 전부 전환.

## 데이터셋 조립

`agent_traces` 실측이 21건뿐이라 라벨된 것 0건. **합성 데이터로 부풀린다**:

1. **실측**: 21건 (anthropic 백엔드 · 라벨 없음이지만 Claude 응답이 곧 답) — PII 마스킹 후 넣는다.
2. **agent 시드 확장**: `synth_seed.yaml` (수작업 47건) → Claude Haiku 로 각 4 변형 → ~180건.
3. **인터뷰 chain 시드**: `synth_seed_interview.yaml` (수작업 ~10건 · chain 마다 2~3) → 확장 안 함 (input 길이·비용).
4. 총 ~210건 · 80/10/10 스플릿.

인터뷰 chain 시드는 **입력이 길다** (자기소개서·이력서·전사 원문). Haiku 확장 시 토큰 비용이 급증하므로 손 시드로 유지하고, 나중에 실측 세션이 쌓이면 라벨해서 교체.

## 파일

| 파일 | 역할 |
|---|---|
| `synth_seed.yaml` | agent 시드 (도구 호출) |
| `synth_seed_interview.yaml` | 인터뷰 chain 시드 (probe · findings · findings_turn · score) |
| `fetch_traces.py` | 서버 DB → `raw_traces.json` |
| `synth_expand.py` | agent 시드 → Haiku 변형 → `synth_cases.jsonl` |
| `build_dataset.py` | 실측 + 합성 + 인터뷰 chain 병합 · PII 마스킹 · 스플릿 → `dataset.{train,val,test}.jsonl` |
| `train.py` | QLoRA 학습 |
| `judge.py` | **판정 규칙 한 벌** (torch 없이 돈다) — 아래 두 평가가 공유한다 |
| `eval.py` | 학습한 어댑터 평가 (로컬 HF · GPU 필요) |
| `eval_anthropic.py` | **Claude 를 같은 케이스·같은 채점기로** 평가 (GPU 불필요) |

## 측정 결과 (2026-09-12)

같은 파일(`dataset.test.jsonl` 23건) · 같은 채점기(`judge.evaluate_one`) 로 재었다.

| 모델 | 통과 | 비율 | 정답 상한 대비 |
|---|---|---|---|
| **Claude Haiku 4.5** (운영이 쓰는 모델) | **16/23** | **69.6%** | 84.2% |
| 파인튜닝 Qwen3-8B (QLoRA, 09-11) | 6/23 | 26.1% | 31.6% |

비용: Claude 23건 $0.32 (캐시 미적용 · 운영은 프리픽스 캐시로 호출당 평균 $0.0075).

### 이 숫자를 읽을 때 — 평가 도구 자체의 한계 3가지

1. **정답 상한이 19/23 (82.6%) 이다.** 정답을 그대로 채점기에 넣어도 4건이 떨어진다
   — `pending_pass` 규칙이 "확인을 받은 **뒤**의 실행 응답"(「변경했습니다」)에도 확인
   문구를 요구한다. 만점이 23이 아니므로 비율은 상한 대비로도 같이 본다.
2. **「먼저 찾고 나서 실행」 을 틀렸다고 본다.** Claude 실패 7건은 대부분
   `search_applications` 를 먼저 부른 것이다 — 이름만 받았을 때 지원자를 찾는
   것은 운영에서 옳은 동작인데(entity_resolver 경로), 정답은 `change_stage` 를
   바로 부르길 기대한다. 이 평가는 "한 턴에 정답 도구 집합을 정확히 뱉는가" 를
   재는 것이고 "일을 해내는가" 를 재지 않는다.
3. **정답 데이터에 없는 도구가 있다** — `update_candidate_stage` (우리 도구는
   `change_stage`). 합성 데이터 생성에서 들어간 오류다.

그래서 "Claude 70% / Qwen 26%" 는 **두 모델의 상대 비교로는 유효**하지만(같은 자·같은
편향), 절대 품질 점수로 읽으면 안 된다. 위 3가지를 고치면 두 숫자 다 올라간다.

## 실행 순서

```bash
# 1. venv
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# 2. 데이터셋
python fetch_traces.py                 # 서버 SSH 필요
python synth_expand.py                 # ANTHROPIC_API_KEY 필요
python build_dataset.py                # 마스킹 + 스플릿

# 3. 학습 (3~5h · 8GB 빠듯)
python train.py

# 4. 평가
python eval.py --checkpoint output/
```

## 산출물

- `output/checkpoint-*/adapter_model.safetensors` — LoRA 어댑터
- `output/qwen3-8b-lora-YYYY-MM-DD.gguf` — Ollama 배포용 (`llama.cpp` 변환)
- `results/qwen3-8b-lora-YYYY-MM-DD.json` — 평가 결과

## 주의

- **개인정보 마스킹**은 `build_dataset.py` 가 한다. 실지원자 이메일·이름·생년월일이 학습 데이터에 남지 않게.
- **8GB VRAM 넘치면**: `train.py` 의 `max_seq_length` 를 2048→1024 로.
- **Ollama 배포**: `llama.cpp` 의 `convert_hf_to_gguf.py` 로 병합 후 GGUF 변환 → `ollama create arda-qwen3 -f Modelfile`.
