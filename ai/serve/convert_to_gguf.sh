#!/usr/bin/env bash
# 병합된 HF 모델 → GGUF Q4_K_M (Ollama 배포용)
#
# 선행: merge_lora.py 로 merged/ 생성됨
# 산출: arda-qwen3.gguf (~5-6GB) · Modelfile 이 이걸 가리킴

set -euo pipefail

MERGED_DIR="${MERGED_DIR:-merged}"
OUT_FILE="${OUT_FILE:-arda-qwen3.gguf}"
QUANT="${QUANT:-Q4_K_M}"

if [ ! -d "$MERGED_DIR" ]; then
  echo "[error] $MERGED_DIR 없음 · merge_lora.py 를 먼저 실행하라" >&2
  exit 1
fi

if [ ! -d "llama.cpp" ]; then
  echo "[gguf] llama.cpp 클론 중..." >&2
  git clone --depth 1 https://github.com/ggerganov/llama.cpp.git
  (cd llama.cpp && make -j LLAMA_OPENBLAS=1)
fi

# 1단계: HF → GGUF fp16 (중간 파일)
echo "[gguf] HF → GGUF fp16 변환" >&2
python llama.cpp/convert_hf_to_gguf.py "$MERGED_DIR" \
  --outfile "arda-qwen3-fp16.gguf" \
  --outtype f16

# 2단계: fp16 → Q4_K_M 양자화
echo "[gguf] Q4_K_M 양자화" >&2
./llama.cpp/build/bin/llama-quantize "arda-qwen3-fp16.gguf" "$OUT_FILE" "$QUANT"

# 중간 파일 삭제 (14GB · 아까움)
rm -f "arda-qwen3-fp16.gguf"

echo "[gguf] 완료: $(ls -lh $OUT_FILE | awk '{print $5, $NF}')"
