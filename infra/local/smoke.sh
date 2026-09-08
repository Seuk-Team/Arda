#!/usr/bin/env bash
# 로컬 전체 스택 검증. 전부 통과하면 "운영과 같은 스택이 로컬에서 돈다" 가 사실이 된다.
set -uo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash 가 /app/... 컨테이너 경로를 Windows 경로로 바꾸지 않게 (WSL/Linux 에선 무해)
# Git Bash 에선 pwd -W 로 C:/... 형태를 쓴다 — /c/... 를 docker.exe 가 C:\c\... 로 오해한다. Linux/WSL 은 pwd.
HERE="$(cd "$(dirname "$0")" && (pwd -W 2>/dev/null || pwd))"
DC=(docker compose -f "$HERE/docker-compose.yml")
pass=0; fail=0
ok()   { echo "  ✅ $1"; pass=$((pass+1)); }
bad()  { echo "  ❌ $1"; fail=$((fail+1)); }
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 15 "$@"; }

echo "[컨테이너]"
"${DC[@]}" ps --format '  {{.Service}}\t{{.Status}}' 2>/dev/null

echo "[api 직접 · caddy 경유]"
[ "$(code http://localhost:8000/health)" = 200 ] && ok "api /health 200" || bad "api /health"
[ "$(code http://localhost:8080/health)" = 200 ] && ok "caddy → api /health 200" || bad "caddy → api /health"
c=$(code http://localhost:8080/api/v1/internal/email-logs/1/render); [ "$c" = 401 ] && ok "내부 API 서비스 토큰 게이트 401" || bad "내부 API 기대 401, 실제 $c"
c=$(code http://localhost:8080/api/v1/integrity/chain);            [ "$c" = 401 ] && ok "무결성 API 인증 게이트 401" || bad "무결성 API 기대 401, 실제 $c"

echo "[lie-detection]"
c=$(code http://localhost:8080/ai/);           [ "$c" = 200 ] && ok "caddy → lie-detection / 200" || bad "lie-detection 기대 200, 실제 $c"
c=$(code -X POST http://localhost:8080/ai/analyze); [ "$c" = 400 ] || [ "$c" = 422 ] && ok "lie-detection /analyze 빈 POST → $c (FastAPI 검증)" || bad "lie-detection /analyze 기대 400/422, 실제 $c"

echo "[n8n]"
c=$(code http://localhost:8080/n8n/); [ "$c" = 401 ] && ok "caddy → n8n Basic Auth 401" || bad "n8n Basic Auth 기대 401, 실제 $c"
r=$(curl -s --max-time 15 -X POST http://localhost:5678/webhook/stage-changed -H 'Content-Type: application/json' -d '{"email_log_id": 0}')
echo "$r" | grep -q 'Workflow was started' && ok "n8n 웹훅 활성 (Workflow was started)" || bad "n8n 웹훅 응답: ${r:0:80}"

echo "[db · alembic]"
rev=$("${DC[@]}" exec -T api /app/.venv/bin/alembic current 2>/dev/null | tail -1)
echo "$rev" | grep -q '(head)' && ok "alembic $rev" || bad "alembic 리비전: ${rev:-없음}"
"${DC[@]}" exec -T db psql -U postgres -d arda -tA -c "SELECT 'apps='||(SELECT count(*) FROM applications)||' postings='||(SELECT count(*) FROM job_postings)||' email_logs='||(SELECT count(*) FROM email_logs)" 2>/dev/null | sed 's/^/  /'

echo "[api 기동 에러 스캔 (최근 200줄)]"
# 401/404 는 위 프로브가 일부러 낸 것이라 WARNING 줄은 세지 않는다. 진짜 장애 신호만: Traceback · level ERROR/CRITICAL
errs=$("${DC[@]}" logs --tail 200 api 2>/dev/null | grep -cE 'Traceback|"level": "(ERROR|CRITICAL)"' || true)
[ "${errs:-0}" = 0 ] && ok "api 로그 Traceback/ERROR 0" || bad "api 로그 Traceback/ERROR ${errs}건 — docker compose -f infra/local/docker-compose.yml logs api"

echo; echo "결과: ✅ $pass  ❌ $fail"
[ "$fail" = 0 ]
