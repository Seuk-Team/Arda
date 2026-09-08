#!/usr/bin/env bash
# 서버(EC2) 의 시크릿·데이터를 로컬 전체 스택용으로 가져온다 (infra/local/docker-compose.yml 짝).
#
# 전제: `ssh arda` 가 된다 (~/.ssh/config 에 Host arda). WSL 또는 Git Bash 에서:
#   bash infra/local/pull-from-server.sh
#
# 가져오는 것 (전부 이 폴더에, 전부 .gitignore):
#   .env          서버 ~/arda/.env
#   .env.backend  서버 ~/arda/backend/.env + 로컬 덮어쓰기(뒤에 붙임, env_file 은 뒤 줄이 이긴다)
#   db.sql.gz     pg_dump (--no-owner --no-privileges: 로컬 postgres 롤로 그대로 들어가게)
#   n8n.tar.gz    n8n 볼륨 (워크플로·자격 증명·owner 계정)
#
# 이 스크립트는 시크릿 값을 화면에 찍지 않는다. 파일 크기만 보여 준다.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SSH_HOST="${ARDA_SSH_HOST:-arda}"
umask 077

echo "[1/4] compose .env"
ssh -o BatchMode=yes "$SSH_HOST" 'cat ~/arda/.env' > "$HERE/.env"

echo "[2/4] backend .env (+ 로컬 덮어쓰기)"
ssh -o BatchMode=yes "$SSH_HOST" 'cat ~/arda/backend/.env' > "$HERE/.env.backend"
cors="$(grep -E '^CORS_ORIGINS=' "$HERE/.env.backend" | tail -1 | cut -d= -f2- || true)"
{
  echo ""
  echo "# ---- infra/local/pull-from-server.sh 가 붙인 로컬 덮어쓰기 ($(date -u +%FT%TZ)) — 뒤 줄이 이긴다 ----"
  echo "PUBLIC_APP_BASE_URL=http://localhost:5173"
  echo "CORS_ORIGINS=${cors:+$cors,}http://localhost:5173,http://localhost:4173,http://localhost:8080"   # 5173 dev · 4173 vite preview(프로덕션 번들)
} >> "$HERE/.env.backend"

echo "[3/4] DB pg_dump (서버 db 컨테이너에서 바로)"
ssh -o BatchMode=yes "$SSH_HOST" \
  'docker compose -f ~/arda/docker-compose.prod.yml exec -T db pg_dump -U postgres --no-owner --no-privileges arda | gzip -c' \
  > "$HERE/db.sql.gz"

echo "[4/4] n8n 볼륨 tar"
ssh -o BatchMode=yes "$SSH_HOST" \
  'docker compose -f ~/arda/docker-compose.prod.yml exec -T n8n tar czf - -C /home/node/.n8n .' \
  > "$HERE/n8n.tar.gz"

echo "--- 가져온 파일 (bytes name) ---"
ls -la "$HERE/.env" "$HERE/.env.backend" "$HERE/db.sql.gz" "$HERE/n8n.tar.gz" | awk '{print $5, $9}'
echo "다음: docker compose -f infra/local/docker-compose.yml up -d --build && bash infra/local/restore.sh"
