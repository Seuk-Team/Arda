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
| `eval.py` | 규칙 판정 (eval_cases.yaml 기준 재사용) |

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
