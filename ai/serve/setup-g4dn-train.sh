#!/usr/bin/env bash
# AWS g4dn.xlarge 학습 환경 부트스트랩 (Ubuntu 22.04 · T4 16GB)
#
# 이 스크립트는 학습 전용 · 나중에 setup-g4dn.sh (Ollama) 를 더 돌려 시연 서버로 겸용.
# 실행:
#   curl -O https://raw.githubusercontent.com/Seuk-Team/Arda/main/ai/serve/setup-g4dn-train.sh
#   bash setup-g4dn-train.sh

set -euo pipefail
log() { echo "[$(date +%H:%M:%S)] $*"; }

# ─────────────────────────────────────────────
log "1/5 · apt · Python 3.12 · CUDA 확인"
sudo apt-get update -y
sudo apt-get install -y python3.12 python3.12-venv python3-pip git build-essential curl htop nvtop tmux

# NVIDIA 드라이버는 g4dn AMI 에 기본 포함 · 없으면 설치
if ! command -v nvidia-smi &>/dev/null; then
  sudo apt-get install -y ubuntu-drivers-common
  sudo ubuntu-drivers autoinstall
  log "  ! 드라이버 설치 · 재부팅 필요 · 재부팅 후 이 스크립트 다시 실행"
  echo "  sudo reboot"
  exit 0
fi
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader

# ─────────────────────────────────────────────
log "2/5 · Arda 저장소 가져오기"
if [ ! -d ~/Arda ]; then
  git clone https://github.com/Seuk-Team/Arda.git ~/Arda
fi
cd ~/Arda
git pull

# ─────────────────────────────────────────────
log "3/5 · venv + Python 학습 의존성"
cd ~/Arda/ai/qwen-training
if [ ! -d .venv ]; then
  python3.12 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip

# torch CUDA 12.1 (T4 지원)
pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cu121

# 학습 스택
pip install 'transformers>=4.44,<5.0' 'peft>=0.13' 'bitsandbytes>=0.43' 'accelerate>=1.0'
pip install 'trl>=0.11,<1.0' 'datasets>=3.0' sentencepiece protobuf pyyaml anthropic
python -c "import torch; print(f'torch {torch.__version__} · cuda {torch.cuda.is_available()} · {torch.cuda.get_device_name(0)}')"

# ─────────────────────────────────────────────
log "4/5 · Qwen3-8B 모델 다운로드 (~16GB)"
python -c "
from huggingface_hub import snapshot_download
p = snapshot_download('Qwen/Qwen3-8B')
print(f'downloaded: {p}')
"

# ─────────────────────────────────────────────
log "5/5 · 학습 파이프라인 확인"
if [ ! -f dataset.train.jsonl ]; then
  log "  ! 데이터셋 없음 · 로컬에서 rsync 로 파이프라인 산출물 전송 필요:"
  echo "     rsync -avz ai/qwen-training/{raw_traces.json,synth_cases.jsonl,dataset.*.jsonl,synth_seed*.yaml} ubuntu@<g4dn-ip>:~/Arda/ai/qwen-training/"
  log "  ! 또는 이 서버에서 파이프라인 처음부터:"
  echo "     python fetch_traces.py    # 서버 DB 접근 필요 (arda-db-1)"
  echo "     python synth_expand.py    # ANTHROPIC_API_KEY 필요"
  echo "     python build_dataset.py"
else
  log "  ✅ 데이터셋 존재 · train=$(wc -l < dataset.train.jsonl)"
fi

log "완료 · 다음: tmux 안에서 python train.py (5-6h · 종료돼도 죽지 않음)"
log ""
log "  tmux new -s train"
log "  cd ~/Arda/ai/qwen-training && source .venv/bin/activate"
log "  MAX_SEQ_LENGTH=4096 python -u train.py 2>&1 | tee train.log"
log "  # Ctrl+B, D 로 detach · 다시 붙기: tmux attach -t train"
