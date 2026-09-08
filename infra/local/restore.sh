#!/usr/bin/env bash
# pull-from-server.sh 가 가져온 db.sql.gz · n8n.tar.gz 를 로컬 compose 볼륨에 넣는다.
# 로컬 전용 볼륨이라 **기존 로컬 DB 를 통째로 버리고** 교체한다. 운영엔 아무 영향 없다.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash 가 /app/... 컨테이너 경로를 Windows 경로로 바꾸지 않게 (WSL/Linux 에선 무해)
# Git Bash 에선 pwd -W 로 C:/... 형태를 쓴다 — /c/... 를 docker.exe 가 C:\c\... 로 오해한다. Linux/WSL 은 pwd.
HERE="$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))"
DC=(docker compose -f "$HERE/docker-compose.yml")

echo "[1/4] db 기동·대기"
"${DC[@]}" up -d db
for _ in $(seq 1 40); do
  "${DC[@]}" exec -T db pg_isready -U postgres >/dev/null 2>&1 && break
  sleep 1
done

echo "[2/4] DB 교체 (api 가 붙어 있으면 먼저 내린다)"
"${DC[@]}" stop api worker 2>/dev/null || true
"${DC[@]}" exec -T db psql -U postgres -v ON_ERROR_STOP=1 -q \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='arda' AND pid<>pg_backend_pid();" \
  -c 'DROP DATABASE IF EXISTS arda;' -c 'CREATE DATABASE arda;'
# 덤프에 CREATE EXTENSION vector 가 들어 있다(pgvector 이미지라 통과). 경고는 무시, 에러는 세지 않고 진행.
gunzip -c "$HERE/db.sql.gz" | "${DC[@]}" exec -T db psql -U postgres -d arda -q 2>&1 | grep -E 'ERROR' | head -5 || true
"${DC[@]}" exec -T db psql -U postgres -d arda -tA -c \
  "SELECT 'apps='||(SELECT count(*) FROM applications)||' postings='||(SELECT count(*) FROM job_postings)||' email_logs='||(SELECT count(*) FROM email_logs)||' users='||(SELECT count(*) FROM users)"

echo "[3/4] n8n 볼륨 복원 (워크플로·자격 증명·owner 계정)"
"${DC[@]}" stop n8n 2>/dev/null || true
"${DC[@]}" run --rm --no-deps --entrypoint sh \
  -v "$HERE/n8n.tar.gz:/restore.tar.gz:ro" n8n \
  -c 'rm -rf /home/node/.n8n/* /home/node/.n8n/.[!.]* 2>/dev/null; tar xzf /restore.tar.gz -C /home/node/.n8n && ls /home/node/.n8n | head'

echo "[4/4] 전체 기동 + alembic 리비전"
"${DC[@]}" up -d
sleep 5
"${DC[@]}" exec -T api /app/.venv/bin/alembic current 2>/dev/null | tail -1 || echo "(alembic current 실패 — api 로그 확인)"
echo "다음: bash infra/local/smoke.sh"
