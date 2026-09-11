#!/usr/bin/env bash
# 로컬 → g4dn.xlarge · arda-qwen3.gguf 업로드 + ollama create
#
# 사용:
#   export G4DN_HOST=ubuntu@1.2.3.4
#   bash deploy.sh
#
# 선행: convert_to_gguf.sh 로 arda-qwen3.gguf 생성됨

set -euo pipefail

: "${G4DN_HOST:?G4DN_HOST env 미설정 · 예: ubuntu@1.2.3.4}"
GGUF="${GGUF:-arda-qwen3.gguf}"
MODEL_NAME="${MODEL_NAME:-arda-qwen3}"
MODELFILE="${MODELFILE:-Modelfile.arda-qwen3}"

if [ ! -f "$GGUF" ]; then
  echo "[error] $GGUF 없음 · convert_to_gguf.sh 를 먼저 실행하라" >&2
  exit 1
fi

echo "[deploy] $(du -h $GGUF | awk '{print $1}') → $G4DN_HOST:/opt/models/"
scp "$GGUF" "$G4DN_HOST:/opt/models/"

echo "[deploy] Modelfile 업로드"
scp "$MODELFILE" "$G4DN_HOST:/opt/models/Modelfile"

echo "[deploy] Modelfile 안의 FROM 경로를 서버 절대 경로로 수정"
ssh "$G4DN_HOST" "sed -i 's|FROM \./arda-qwen3.gguf|FROM /opt/models/arda-qwen3.gguf|' /opt/models/Modelfile"

echo "[deploy] ollama create $MODEL_NAME"
ssh "$G4DN_HOST" "cd /opt/models && ollama create $MODEL_NAME -f Modelfile"

echo "[deploy] 등록 확인"
ssh "$G4DN_HOST" "ollama list | grep $MODEL_NAME"

echo "[deploy] 응답 테스트 (한글 인사)"
ssh "$G4DN_HOST" "curl -s http://localhost:11434/api/generate -d '{\"model\":\"$MODEL_NAME\",\"prompt\":\"안녕\",\"stream\":false}' | head -c 300"
echo

echo "[deploy] 완료 · 백엔드 .env 갱신 절차 · README.md §4 참조"
