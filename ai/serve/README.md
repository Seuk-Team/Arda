# 아르(Qwen3-8B LoRA) 시연 배포 (Ollama · AWS g4dn.xlarge)

> **상태**: 초안 · 2026-09-11 · 오너 suvisdev
> **선행**: `ai/qwen-training/` 학습 완료 · `output/final/adapter_model.safetensors` 존재
> **근거**: [ADR-0032](../../docs/03_decision/0032-추론-모델-3종-확정.md) · [ADR-0031](../../docs/03_decision/0031-aws-최소화.md)

## 전체 흐름

```
로컬 (4060 8GB)                          AWS g4dn.xlarge (T4 16GB)
─────────────────                        ──────────────────────────
학습 완료:
  output/final/adapter_model.safetensors    (LoRA 어댑터)
        │
        │ ① merge_lora.py
        ▼
  merged/  (base + LoRA 합친 fp16 · HF)
        │
        │ ② convert_to_gguf.sh
        ▼
  arda-qwen3.gguf  (~5-6GB Q4 양자화)
        │
        │ ③ scp
        └──────────────────────────► /opt/models/arda-qwen3.gguf
                                            │
                                            │ ④ setup-g4dn.sh
                                            │     - Ollama 설치
                                            │     - ollama create arda-qwen3 -f Modelfile
                                            ▼
                                       http://<ip>:11434/api/chat  ◄── 백엔드 스위치
                                                                        AGENT_CHAT_BACKEND=ollama
```

## 파일

| 파일 | 역할 |
|---|---|
| `merge_lora.py` | LoRA 어댑터 + base → 병합 모델 (`merged/`) |
| `convert_to_gguf.sh` | llama.cpp 로 GGUF 변환 · Q4_K_M 양자화 |
| `Modelfile.arda-qwen3` | Ollama Modelfile · agent.v1.md 시스템 프리픽스 포함 |
| `setup-g4dn.sh` | AWS 인스턴스 부트스트랩 · Docker · NVIDIA · Ollama 설치 |
| `deploy.sh` | 로컬에서 원격으로 모델 파일 push + `ollama create` 실행 |

## 실행 순서 (학습 완료 후)

### 1. 로컬 · LoRA 병합 + GGUF 변환

```bash
cd ai/serve
source ../qwen-training/.venv/Scripts/activate

# 병합 (fp16 · ~15GB · 임시)
python merge_lora.py \
  --base Qwen/Qwen3-8B \
  --adapter ../qwen-training/output/final \
  --out merged/

# llama.cpp 필요 (없으면 clone)
if [ ! -d llama.cpp ]; then
  git clone https://github.com/ggerganov/llama.cpp.git
  cd llama.cpp && make -j && cd ..
fi

# GGUF 변환 + Q4_K_M 양자화
bash convert_to_gguf.sh
# → arda-qwen3.gguf (~5-6GB)
```

### 2. AWS · g4dn.xlarge 시작

```bash
# 콘솔에서 g4dn.xlarge · Ubuntu 22.04 · 100GB EBS · 서울 리전
# SSH 접속 후:
curl -O https://raw.githubusercontent.com/Seuk-Team/Arda/main/ai/serve/setup-g4dn.sh
bash setup-g4dn.sh
```

### 3. 모델 배포

```bash
# 로컬에서
export G4DN_HOST=ubuntu@<ip>
bash deploy.sh
# → GGUF 업로드 + ollama create arda-qwen3
```

### 4. 백엔드 스위치

서버 `arda/backend/.env` 에 추가:

```
AGENT_CHAT_BACKEND=ollama
OLLAMA_HOST=http://<g4dn-private-ip>:11434
OLLAMA_CHAT_MODEL=arda-qwen3
```

`docker compose restart api worker` → 아르가 Qwen 으로 응답.

## 롤백

문제 있으면 `AGENT_CHAT_BACKEND` 를 다시 `anthropic` 로 · 재기동. 한 줄.

## 비용 관리

| 상태 | 시간당 |
|---|---|
| g4dn.xlarge running | ~$0.65 |
| stopped | 0 (EBS 만 시간당 ~$0.01) |
| terminated | 0 |

시연·리허설 때만 `aws ec2 start-instances` · 끝나면 즉시 `aws ec2 stop-instances`. 예산 $400 안에 10시간 = ~$7.
