#!/bin/bash
# 운영 서버 자동 배포 스크립트 — 서버 /home/ubuntu/deploy-arda.sh 의 **저장소 사본** (2026-09-07 회수).
#
# 서버 것이 진실이고 여기는 사본이다. 서버를 바꾸면 여기도 같은 커밋에서, 여기를 바꾸면
# 서버에 복사한다:  curl -sL https://raw.githubusercontent.com/Seuk-Team/Arda/main/infra/deploy-arda.sh -o ~/deploy-arda.sh
# (배포 tar 는 이 파일을 안 덮는다 — compose·Caddyfile 과 같은 규칙.)
#
# 부르는 쪽: systemd `arda-deploy.timer` (2분마다 `arda-deploy.service` → 이 스크립트).
# 로그: ~/deploy.log. 새 커밋이 없으면 아무것도 안 하고 끝난다.
#
# 이력: 09-04 alembic 단계 추가(호스트 마운트 방식) → 09-07 마운트 제거(이미지가 alembic 을
# 가진다, PR #20) + 빌드 캐시 prune(--keep-storage 3g) 추가. 백업 ~/deploy-arda.sh.bak·.bak2.
#
# main 에 새 커밋이 오면 pull → build → up. systemd 타이머(2분)가 부른다.
set -euo pipefail
cd /home/ubuntu/arda
git fetch -q origin main
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTE" ] && exit 0
LOG=/home/ubuntu/deploy.log
echo "$(date -Is) deploy start: $LOCAL -> $REMOTE" >> "$LOG"
git merge --ff-only origin/main >> "$LOG" 2>&1
# compose 파일은 저장소 안 `infra/docker-compose.prod.yml` 이다 (root 아님).
# 이전에는 이 스크립트가 `-f docker-compose.prod.yml` (root) 로 참조하면서 서버에
# 남아 있던 옛 사본 `~/arda/docker-compose.prod.yml` (Sep 8 이전) 를 계속 썼다.
# 결과: compose 변경(#103 env_file/mem_limit 등)이 배포에 반영되지 않았다.
# 서버의 옛 사본 삭제와 함께 이 경로를 명시적으로 고정한다.
# 빌드를 up 과 분리 — 빌드가 깨져도 돌던 컨테이너는 안 죽는다 (팀 07-deploy 교훈)
docker compose -p arda -f infra/docker-compose.prod.yml build >> "$LOG" 2>&1
# 스키마 이행 (기동 전에) — 컬럼 추가/변경은 create_all 이 못 함. #17
echo "$(date -Is) alembic upgrade..." >> "$LOG"
docker compose -p arda -f infra/docker-compose.prod.yml run --rm api /app/.venv/bin/alembic upgrade head >> "$LOG" 2>&1
docker compose -p arda -f infra/docker-compose.prod.yml up -d >> "$LOG" 2>&1
sleep 10
if curl -sf http://localhost:8000/health >> "$LOG" 2>&1; then
  echo "$(date -Is) deploy ok: $REMOTE" >> "$LOG"
else
  echo "$(date -Is) deploy WARN: health check 실패 — 로그 확인 필요" >> "$LOG"
fi
docker image prune -f > /dev/null 2>&1 || true
docker builder prune -f --keep-storage 3g > /dev/null 2>&1 || true
