#!/usr/bin/env bash
# Cloudflare 터널 만들기(처음 한 번) — Cloudflare 계정 설정과 DNS 를 바꾸는 단계라 setup.sh 와 나눴다.
#   bash infra/onprem/tunnel.sh
#
#   api-seuk.suvisdev.cloud   → caddy:8080      (API · /ai · /n8n)
#   files-seuk.suvisdev.cloud → seaweedfs:8333  (이력서·면접 음성 presigned 업로드·다운로드)
#
# 필요: 이 PC 의 cloudflared 와 ~/.cloudflared/cert.pem (cloudflared tunnel login 결과).
# 주소를 한 단계(api-seuk.)로 둔 이유: Cloudflare 무료 인증서는 *.suvisdev.cloud 한 단계만 덮어
# 터널(프록시 필수)로는 api.seuk.suvisdev.cloud 에 HTTPS 를 못 연다(2026-10-28 실측 TLS 실패).
# 예전 api.seuk 는 프록시 없이 EC2 Caddy 가 직접 인증서를 받았기에 됐던 것이다.
set -euo pipefail

NAME=arda-onprem
DIR="$HOME/.cloudflared/$NAME"
mkdir -p "$DIR"
# --config /dev/null: ~/.cloudflared/config.yml(다른 터널)의 tunnel: 값이 끼어들면 route dns 가
# 그 터널로 CNAME 을 건다(2026-10-28 실측 — api.seuk 가 lora-nb 터널로 갔다). 기본 설정을 끊고 ID 로 지정한다.
CF=(cloudflared --config /dev/null)

ID="$("${CF[@]}" tunnel list --name "$NAME" --output json | python3 -c 'import json,sys; t=json.load(sys.stdin); print(t[0]["id"] if t else "")')"
if [ -z "$ID" ]; then
  "${CF[@]}" tunnel create --credentials-file "$DIR/creds.json" "$NAME" >/dev/null
  ID="$("${CF[@]}" tunnel list --name "$NAME" --output json | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])')"
fi
[ -f "$DIR/creds.json" ] || { echo "터널은 있는데 $DIR/creds.json 이 없다 — 다른 PC 에서 만든 터널이면 그 자격 파일을 가져온다"; exit 1; }

cat > "$DIR/config.yml" <<EOF
tunnel: $ID
credentials-file: /etc/cloudflared/creds.json
ingress:
  - hostname: api-seuk.suvisdev.cloud
    service: http://caddy:8080
  - hostname: files-seuk.suvisdev.cloud
    service: http://seaweedfs:8333
  - service: http_status:404
EOF
chmod 644 "$DIR/config.yml" "$DIR/creds.json"   # 컨테이너(nonroot)가 읽는다. 폴더는 홈 안이다

for h in api-seuk.suvisdev.cloud files-seuk.suvisdev.cloud; do
  "${CF[@]}" tunnel route dns --overwrite-dns "$ID" "$h"
done
echo "터널 $NAME ($ID) 준비 끝 → docker compose -f infra/onprem/docker-compose.yml up -d"
