#!/usr/bin/env bash
# 노트북 온프레미스 첫 설치 — AWS 종료 전 백업 폴더로 시크릿·DB·n8n·파일을 채운다.
#   bash infra/onprem/setup.sh /mnt/c/Users/<사용자>/Desktop/seuk/AWS_백업_20261026
#
# 하는 일 (WSL 의 docker 기준, 저장소 루트에서):
#   1. .env(compose 값) · .env.backend(api 값 + 온프레미스 덮어쓰기) · s3.json(저장소 키) 생성
#   2. db 복원(백업 db/*.dump) — 기존 로컬 DB 를 버리고 교체한다
#   3. n8n 볼륨 복원(백업 n8n/*.tar.gz)
#   4. 버킷 생성 + 제출 파일 업로드(백업 s3/<버킷>/)
# 터널은 따로: bash infra/onprem/tunnel.sh   (Cloudflare 설정을 바꾸는 단계라 분리)
set -euo pipefail

BACKUP="${1:?백업 폴더 경로를 주세요 (env/ db/ n8n/ s3/ 가 있는 곳)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
BUCKET=arda-resumes-seuk
PUBLIC_S3=https://files-seuk.suvisdev.cloud
DC=(docker compose -f "$HERE/docker-compose.yml")

get() { grep -E "^$1=" "$2" | tail -1 | cut -d= -f2-; }

echo "[1/4] 시크릿 파일"
ARDA_ENV="$BACKUP/env/arda.env"
S3_KEY="${S3_KEY:-arda-onprem}"
S3_SECRET="$(get S3_SECRET "$HERE/.env" 2>/dev/null || true)"
S3_SECRET="${S3_SECRET:-$(openssl rand -hex 24)}"
umask 077
# bcrypt 해시의 $ 는 운영 .env 처럼 $$ 로 이스케이프된 채 옮긴다(compose 가 $ 를 변수로 읽는다)
cat > "$HERE/.env" <<EOF
DB_PASSWORD=$(get DB_PASSWORD "$ARDA_ENV")
N8N_ENCRYPTION_KEY=$(get N8N_ENCRYPTION_KEY "$ARDA_ENV")
N8N_BASIC_AUTH_USER=$(get N8N_BASIC_AUTH_USER "$ARDA_ENV")
N8N_BASIC_AUTH_HASH=$(get N8N_BASIC_AUTH_HASH "$ARDA_ENV")
ARDA_SERVICE_TOKEN=$(get ARDA_SERVICE_TOKEN "$ARDA_ENV")
S3_KEY=$S3_KEY
S3_SECRET=$S3_SECRET
TUNNEL_DIR=$HOME/.cloudflared/arda-onprem
EOF
{
  cat "$BACKUP/env/backend.env"
  echo
  echo "# ── 온프레미스 덮어쓰기 (setup.sh) — 뒤에 오는 값이 이긴다"
  echo "S3_ENDPOINT_URL=$PUBLIC_S3"
  echo "S3_BUCKET=$BUCKET"
  echo "AWS_REGION=ap-northeast-2"
  echo "AWS_ACCESS_KEY_ID=$S3_KEY"
  echo "AWS_SECRET_ACCESS_KEY=$S3_SECRET"
} > "$HERE/.env.backend"
cat > "$HERE/s3.json" <<EOF
{"identities":[{"name":"arda","credentials":[{"accessKey":"$S3_KEY","secretKey":"$S3_SECRET"}],"actions":["Admin","Read","Write","List","Tagging"]}]}
EOF

echo "[2/4] DB 복원"
"${DC[@]}" up -d db
for _ in $(seq 1 40); do "${DC[@]}" exec -T db pg_isready -U postgres -d arda >/dev/null 2>&1 && break; sleep 1; done
"${DC[@]}" stop api 2>/dev/null || true
"${DC[@]}" exec -T db psql -U postgres -v ON_ERROR_STOP=1 -q -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='arda' AND pid<>pg_backend_pid();" \
  -c 'DROP DATABASE IF EXISTS arda;' -c 'CREATE DATABASE arda;'
DUMP="$(ls "$BACKUP"/db/*.dump | tail -1)"
"${DC[@]}" exec -T db pg_restore -U postgres -d arda --no-owner < "$DUMP" 2>&1 | grep -E 'error' | head -5 || true
"${DC[@]}" exec -T db psql -U postgres -d arda -tA -c \
  "SELECT 'apps='||(SELECT count(*) FROM applications)||' users='||(SELECT count(*) FROM users)||' postings='||(SELECT count(*) FROM job_postings)"

echo "[3/4] n8n 볼륨 복원"
N8N_TAR="$(ls "$BACKUP"/n8n/*.tar.gz | tail -1)"
"${DC[@]}" run --rm --no-deps --entrypoint sh -v "$N8N_TAR:/restore.tar.gz:ro" n8n \
  -c 'rm -rf /home/node/.n8n/* /home/node/.n8n/.[!.]* 2>/dev/null; tar xzf /restore.tar.gz -C /home/node/.n8n && ls /home/node/.n8n | head -3'

echo "[4/4] 버킷 생성 + 제출 파일 업로드"
"${DC[@]}" up -d seaweedfs
NET="arda-onprem_default"
AWS=(docker run --rm --network "$NET" -e AWS_ACCESS_KEY_ID="$S3_KEY" -e AWS_SECRET_ACCESS_KEY="$S3_SECRET" \
     -e AWS_DEFAULT_REGION=ap-northeast-2 -v "$BACKUP/s3/$BUCKET:/src:ro" amazon/aws-cli:2.27.0 --endpoint-url http://seaweedfs:8333)
for _ in $(seq 1 40); do "${AWS[@]}" s3 ls >/dev/null 2>&1 && break; sleep 1; done
"${AWS[@]}" s3 mb "s3://$BUCKET" 2>/dev/null || true
"${AWS[@]}" s3 sync /src "s3://$BUCKET" --only-show-errors
echo "버킷 객체 수: $("${AWS[@]}" s3 ls "s3://$BUCKET" --recursive | wc -l)"

echo "끝. 터널: bash infra/onprem/tunnel.sh  → 켜기: docker compose -f infra/onprem/docker-compose.yml up -d"
