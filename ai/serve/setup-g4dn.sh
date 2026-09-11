#!/usr/bin/env bash
# AWS g4dn.xlarge 부트스트랩 (Ubuntu 22.04)
#
# 필요: NVIDIA 드라이버 · Docker · nvidia-container-toolkit · Ollama
# 실행: 인스턴스 SSH 접속 후
#   curl -O https://raw.githubusercontent.com/Seuk-Team/Arda/main/ai/serve/setup-g4dn.sh
#   bash setup-g4dn.sh

set -euo pipefail

log() { echo "[$(date +%H:%M:%S)] $*"; }

# ─────────────────────────────────────────────────────────────
log "1/5 · apt 패키지 업데이트"
sudo apt-get update -y
sudo apt-get install -y build-essential curl wget htop nvtop

# ─────────────────────────────────────────────────────────────
log "2/5 · NVIDIA 드라이버 (Ubuntu 자동 감지)"
if ! command -v nvidia-smi &>/dev/null; then
  sudo apt-get install -y ubuntu-drivers-common
  sudo ubuntu-drivers autoinstall
  log "  ! 드라이버 설치 완료 · 재부팅 필요 · 재부팅 후 이 스크립트를 다시 실행하라"
  echo "  sudo reboot"
  exit 0
fi
nvidia-smi

# ─────────────────────────────────────────────────────────────
log "3/5 · Docker + nvidia-container-toolkit"
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  sudo usermod -aG docker "$USER"
fi

# nvidia-container-toolkit
distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# ─────────────────────────────────────────────────────────────
log "4/5 · Ollama 설치"
if ! command -v ollama &>/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi

# systemd 로 부팅 시 자동 기동 (Ollama 기본)
sudo systemctl enable ollama
sudo systemctl start ollama

# 외부 접속 허용 (내부 VPC 안에서만 접근 · security group 으로도 막음)
sudo mkdir -p /etc/systemd/system/ollama.service.d
cat <<'EOF' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
Environment="OLLAMA_MODELS=/opt/ollama/models"
EOF
sudo systemctl daemon-reload
sudo systemctl restart ollama

# 모델 저장 경로 (EBS 100GB 를 여기 쓸 것)
sudo mkdir -p /opt/ollama/models /opt/models
sudo chown -R $USER: /opt/ollama /opt/models

# ─────────────────────────────────────────────────────────────
log "5/5 · 확인"
sleep 3
ollama list || true
curl -sf http://localhost:11434/api/tags | head -c 500
echo
log "완료 · 다음: 로컬에서 deploy.sh 로 arda-qwen3.gguf 를 이 서버에 올릴 것"
log "GPU 상태:"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
