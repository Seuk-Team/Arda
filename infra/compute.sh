#!/bin/bash
# 거짓말 탐지(ai/lie-detection) 를 CPU 로 돌릴지 GPU 로 돌릴지 — **손잡이는 이것 하나다** (2026-10-14).
# 절차 · GPU 호스트 준비 · 끄는 순서는 infra/gpu/README.md.
#
# 구조: 운영 서버(t3.large)에는 GPU 가 없다. 이 서버의 lie-detection 은 **늘 CPU 판으로 떠 있고**,
# GPU 모드는 Caddy 가 /ai/* 를 다른 기계(g4dn 등)의 GPU 판으로 넘기는 것이다. 그동안 CPU 컨테이너는
# 뒤에서 대기하다가 GPU 가 응답하지 않으면 Caddy 가 저절로 그쪽으로 돌린다(Caddyfile lie_remote).
#
# 운영 서버에서 (~/arda):
#   bash infra/compute.sh status                       지금 모드 · 양쪽 헬스 · /ai/* 가 실제로 가는 곳
#   bash infra/compute.sh gpu 10.0.1.23                /ai/* → GPU 호스트. 헬스·cuda 스모크가 통과해야 바꾼다
#   bash infra/compute.sh gpu 10.0.1.23 --ssh ubuntu@10.0.1.23
#                                                      + 그 기계 코드를 main 으로 올려 다시 띄운 뒤 전환,
#                                                        이후 배포 때도 같은 길로 따라 올린다 (권장)
#   bash infra/compute.sh gpu                          지난번 GPU 호스트로 다시
#   bash infra/compute.sh cpu                          /ai/* → 이 서버 CPU. **GPU 를 끄기 전에 반드시**
# GPU 호스트에서 (~/arda):
#   bash infra/compute.sh serve [--pull]               GPU 판 빌드·기동·cuda 스모크 (--pull: main 으로 올린 뒤)
# deploy-arda.sh 가 부르는 것 (사람이 칠 일 없음):
#   bash infra/compute.sh env                          기록된 모드의 Caddy 환경변수 (KEY=VAL 줄)
#   bash infra/compute.sh on-deploy <0|1>              GPU 호스트 점검·갱신(1=lie-detection 바뀜), 안 되면 cpu 로
#
# 상태 기록: ~/arda/.compute (git 밖 · .gitignore). 없으면 cpu. 이 스크립트만 쓴다.
# 멱등: 바뀐 것이 없으면 compose 가 아무것도 재시작하지 않는다 — 같은 명령을 두 번 쳐도 안전.
set -euo pipefail

ARDA_DIR=${ARDA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}
STATE=${ARDA_COMPUTE_STATE:-$ARDA_DIR/.compute}
PROJECT=${ARDA_PROJECT:-arda}                    # deploy-arda.sh 의 -p 와 같은 값
GPU_PROJECT=${ARDA_GPU_PROJECT:-arda-gpu}
SITE=${ARDA_SITE:-api.seuk.suvisdev.cloud}
CADDY_AI=${ARDA_CADDY_AI:-https://$SITE/ai}      # Caddy 를 거쳐 /ai/* 를 볼 주소 (이 서버로 붙는다)
DEPLOY_SCRIPT=${ARDA_DEPLOY_SCRIPT:-$HOME/deploy-arda.sh}
GPU_DIR=${ARDA_GPU_DIR:-arda}                    # GPU 호스트의 저장소 위치 (ssh 홈 기준)
# 시험용: 운영 compose 위에 오버레이를 더 붙인다(공백 구분). 운영에서는 비워 둔다.
FRONT_EXTRA=${ARDA_FRONT_EXTRA_COMPOSE:-}

# Caddy 에 넣을 값. 기본은 기록대로(read_state) — 그래야 status 같은 명령이 compose 를 불러도
# caddy 설정이 달라 보이지 않는다.
WANT_PROXY=local
WANT_UPSTREAM=""

say()  { echo "[compute] $*"; }
warn() { echo "[compute] WARN: $*" >&2; }
die()  { echo "[compute] 중단: $*" >&2; exit 1; }

valid_hostport() { [[ "$1" =~ ^[A-Za-z0-9._-]+:[0-9]{1,5}$ ]]; }
valid_ssh()      { [[ "$1" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9._-]+$ ]]; }

# ── 상태 ──────────────────────────────────────────────────────
# MODE: cpu|gpu · GPU_HOST: 지금(또는 지난번) GPU 호스트 · GPU_SSH: 그 기계에 들어갈 ssh 대상
read_state() {
  MODE=cpu; GPU_HOST=""; GPU_SSH=""; SINCE=""
  [ -f "$STATE" ] || return 0
  local k v
  while IFS='=' read -r k v; do
    case "$k" in
      ARDA_COMPUTE) MODE=$v ;;
      LIE_GPU_UPSTREAM) GPU_HOST=$v ;;
      LIE_GPU_SSH) GPU_SSH=$v ;;
      SINCE) SINCE=$v ;;
    esac
  done < <(grep -E '^[A-Z_]+=' "$STATE" | tr -d '\r')
  # 값이 이상하면 cpu 로 본다 — caddy 가 못 뜨는 것보다 CPU 로 도는 편이 낫다
  valid_hostport "$GPU_HOST" || GPU_HOST=""
  valid_ssh "$GPU_SSH" || GPU_SSH=""
  if [ "$MODE" != gpu ] || [ -z "$GPU_HOST" ]; then MODE=cpu; fi
  proxy_env_of "$MODE" "$GPU_HOST"
}

write_state() {  # mode host ssh
  local tmp="$STATE.tmp.$$"
  {
    echo "# infra/compute.sh 가 쓴다 — 손으로 고치지 말 것. 보기: bash infra/compute.sh status"
    echo "ARDA_COMPUTE=$1"
    echo "LIE_GPU_UPSTREAM=$2"
    echo "LIE_GPU_SSH=$3"
    echo "SINCE=$(date -Is)"
  } > "$tmp"
  mv "$tmp" "$STATE"
}

# 모드 → Caddy 환경변수 (Caddyfile 의 lie_local / lie_remote)
proxy_env_of() {  # mode host
  if [ "$1" = gpu ]; then WANT_PROXY=remote; WANT_UPSTREAM=$2; else WANT_PROXY=local; WANT_UPSTREAM=""; fi
}

# ── compose ───────────────────────────────────────────────────
# 운영 서버 compose. deploy-arda.sh 와 **같은 자리에서 같은 꼴로** 부른다 — .env 를 찾는 곳이 같아야 한다.
front_dc() {
  local extra=() f
  for f in $FRONT_EXTRA; do extra+=(-f "$f"); done
  (cd "$ARDA_DIR" && LIE_PROXY="$WANT_PROXY" LIE_GPU_UPSTREAM="$WANT_UPSTREAM" \
    docker compose -p "$PROJECT" -f infra/docker-compose.prod.yml "${extra[@]}" "$@")
}

# GPU 호스트 compose — lie-detection 하나 + GPU 오버레이
gpu_dc() {
  (cd "$ARDA_DIR" && docker compose -p "$GPU_PROJECT" \
    -f infra/docker-compose.gpu-host.yml -f infra/docker-compose.gpu.yml "$@")
}

# ── HTTP ──────────────────────────────────────────────────────
# 서버에 jq 가 없다 — JSON 한 칸은 python3 로 읽는다. 경로는 점으로(compute.deception).
jget() {
  python3 -c 'import json, sys
d = json.load(sys.stdin)
for k in sys.argv[1].split("."):
    d = d.get(k) if isinstance(d, dict) else None
print("" if d is None else d)' "$1"
}

# 컨테이너 안에서 자기 자신(127.0.0.1:5000)을 부른다. 토큰은 컨테이너 환경의 것 — 셸에 안 꺼낸다.
IN_PY='import os, sys, urllib.request
req = urllib.request.Request("http://127.0.0.1:5000" + sys.argv[1], method=sys.argv[2],
                             headers={"X-Service-Token": os.environ.get("ARDA_SERVICE_TOKEN", "")})
sys.stdout.write(urllib.request.urlopen(req, timeout=float(sys.argv[3])).read().decode())'
front_call() { front_dc exec -T lie-detection python -c "$IN_PY" "$1" "${2:-GET}" "${3:-10}"; }
gpu_call()   { gpu_dc exec -T lie-detection python -c "$IN_PY" "$1" "${2:-GET}" "${3:-10}"; }

# 원격 GPU 호스트. 토큰은 이 서버 lie-detection 의 것(같은 backend/.env) — 명령줄(ps)에 안 보이게 넘긴다.
remote_get() { curl -sf --max-time "${2:-5}" "http://$GPU_HOST$1"; }
remote_selftest() {
  local token
  token=$(front_dc exec -T lie-detection printenv ARDA_SERVICE_TOKEN 2>/dev/null | tr -d '\r') || true
  [ -n "$token" ] || { warn "이 서버 lie-detection 에서 ARDA_SERVICE_TOKEN 을 못 읽었다"; return 1; }
  curl -sf --max-time "${1:-900}" -X POST -H @<(printf 'X-Service-Token: %s\n' "$token") \
    "http://$GPU_HOST/selftest"
}

# Caddy 를 거친 /ai/* — 이 서버의 443 으로 붙는다(DNS 를 타지 않는다)
caddy_get() { curl -sk --max-time 5 --resolve "$SITE:443:127.0.0.1" "$CADDY_AI$1"; }

wait_health() {  # 부를 함수(front_call|gpu_call), 기다릴 초
  local out
  for _ in $(seq 1 "$2"); do
    if out=$("$1" /health GET 5 2>/dev/null) && [ "$(echo "$out" | jget status)" = ok ]; then return 0; fi
    sleep 1
  done
  return 1
}

# 셀프 테스트 결과 → 모델마다 한 줄. 기대 장치(cpu|cuda)와 다르게 돈 모델이 있으면 실패.
#   STT·ViT 는 핵심 — 켜져 있는데 못 올렸으면(unavailable) 실패. 둘 중 하나는 실제로 돌아야 한다.
#   참/거짓 둘은 참고 지표 — 못 올린 것(openai-whisper 미설치 등)은 알리기만 하고, 돌다 터지면 실패.
CHECK_PY='import json, sys
expect = sys.argv[1]
d = json.load(sys.stdin)
models = d.get("models", {})
bad = 0
for name, m in models.items():
    st, dev = m.get("status", "?"), m.get("device") or "-"
    ms = "%dms" % m["ms"] if m.get("ms") is not None else ""
    print("    %-18s %-11s %-7s %7s  %s" % (name, st, dev, ms, m.get("detail") or ""))
    if st == "ok" and not dev.startswith(expect):
        print("      ↑ %s 가 아니다" % expect); bad += 1
    if st == "error" or (name in ("stt", "vit") and st == "unavailable"):
        bad += 1
if not any(models.get(n, {}).get("status") == "ok" for n in ("stt", "vit")):
    print("    STT·ViT 어느 것도 돌지 않았다"); bad += 1
sys.exit(1 if bad else 0)'
check_selftest() { python3 -c "$CHECK_PY" "$1"; }

# ── Caddy ─────────────────────────────────────────────────────
caddy_running() { [ -n "$(front_dc ps -q caddy 2>/dev/null)" ]; }

# 새 환경으로 Caddyfile 을 읽어 본다. 못 읽으면 바꾸지 않는다 — 잘못 바꾸면 사이트 전체가 안 뜬다.
caddy_validate() {
  front_dc run --rm --no-deps -T caddy caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile \
    > /dev/null 2>&1
}

# 환경이 지금과 같으면 compose 가 건드리지 않는다. 다르면 caddy 만 다시 만든다(2~3초 끊김).
caddy_apply() {
  if ! caddy_running; then
    warn "caddy 컨테이너가 없다 — 기록만 바꿨다 (다음 배포·기동 때 반영)"
    return 0
  fi
  front_dc up -d --no-deps caddy
}

caddy_env_now() {
  local id; id=$(front_dc ps -q caddy 2>/dev/null) || true
  [ -n "$id" ] || { echo "(caddy 없음)"; return; }
  docker inspect "$id" --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | grep -E '^LIE_(PROXY|GPU_UPSTREAM)=' | tr '\n' ' ' || true
}

# /ai/health 가 기대한 쪽에서 오는가. 참/거짓 모델 장치(compute.deception)로 가른다 —
# 어느 판이든 늘 값이 있고, GPU 판만 cuda 다.
verify_via_caddy() {  # cpu|cuda
  caddy_running || { say "caddy 없음 — Caddy 경유 확인은 건너뛴다"; return 0; }
  local dev=""
  for _ in $(seq 1 30); do
    dev=$(caddy_get /health 2>/dev/null | jget compute.deception 2>/dev/null) || true
    [ "$dev" = "$1" ] && { say "Caddy 경유 /ai/health → $dev ✓"; return 0; }
    sleep 1
  done
  warn "Caddy 경유 /ai/health 가 $1 가 아니다 (받은 값: ${dev:-응답 없음})"
  return 1
}

# ── 점검 ──────────────────────────────────────────────────────
# GPU 호스트가 받을 준비가 됐나: 헬스 → GPU 보임 → (smoke=1 이면) 모델이 cuda 에서 돈다
gpu_ready() {  # smoke(0|1)
  local h n out
  h=$(remote_get /health 5) || { warn "GPU 호스트 http://$GPU_HOST/health 응답 없음 — 인스턴스·컨테이너·보안 그룹(5000) 확인"; return 1; }
  [ "$(echo "$h" | jget status)" = ok ] || { warn "GPU 호스트 헬스가 ok 가 아니다"; return 1; }
  n=$(echo "$h" | jget compute.cuda_devices)
  [ "${n:-0}" -ge 1 ] 2>/dev/null || { warn "GPU 호스트에 GPU 가 안 보인다(cuda_devices=${n:-?}) — GPU 판이 아니거나 GPU 없이 떴다"; return 1; }
  [ "$(echo "$h" | jget compute.deception)" = cuda ] || { warn "GPU 호스트가 CPU 설정으로 떠 있다 — 그 기계에서 compute.sh serve"; return 1; }
  [ "${1:-1}" = 1 ] || return 0
  say "GPU 호스트 셀프 테스트 (모델 4종 1건씩 — 처음이면 모델 내려받기로 몇 분)"
  out=$(remote_selftest 900) || { warn "셀프 테스트 호출 실패"; return 1; }
  echo "$out" | check_selftest cuda
}

check_deploy_script() {
  [ -f "$DEPLOY_SCRIPT" ] || return 0   # 운영 서버가 아니다(시험 기계)
  grep -q 'compute.sh' "$DEPLOY_SCRIPT" && return 0
  die "서버 $DEPLOY_SCRIPT 가 옛 판이라 배포 때 GPU 모드를 모른다 — 이대로면 main 이 배포되는 순간 CPU 로 돌아간다. 먼저 한 번:
    cp $ARDA_DIR/infra/deploy-arda.sh $DEPLOY_SCRIPT     (infra/gpu/README.md 준비 ⑥)"
}

remote_serve() {
  [ -n "$GPU_SSH" ] || return 1
  say "GPU 호스트 갱신: ssh $GPU_SSH → compute.sh serve --pull"
  ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "$GPU_SSH" \
    "cd $GPU_DIR && bash infra/compute.sh serve --pull"
}

# ── 명령 ──────────────────────────────────────────────────────
cmd_gpu() {
  local host="" ssh="" a
  while [ $# -gt 0 ]; do
    a=$1; shift
    case "$a" in
      --ssh) ssh=${1:-}; shift || true ;;
      -*) die "모르는 인자: $a" ;;
      *) host=$a ;;
    esac
  done
  read_state
  if [ -z "$host" ]; then
    host=$GPU_HOST
    [ -n "$host" ] || die "GPU 호스트를 적는다: bash infra/compute.sh gpu <사설IP>[:포트] [--ssh ubuntu@<사설IP>]"
    say "지난번 GPU 호스트로: $host"
  fi
  [[ "$host" == *:* ]] || host="$host:5000"
  valid_hostport "$host" || die "호스트 형식이 이상하다: $host"
  # ssh 는 적은 것 > 같은 호스트로 기록돼 있던 것
  if [ -z "$ssh" ] && [ "$host" = "$GPU_HOST" ]; then ssh=$GPU_SSH; fi
  [ -z "$ssh" ] || valid_ssh "$ssh" || die "--ssh 는 user@host 꼴: $ssh"
  GPU_HOST=$host; GPU_SSH=$ssh

  check_deploy_script

  if [ -n "$GPU_SSH" ]; then
    remote_serve || die "GPU 호스트에서 serve 실패 — 전환하지 않았다 (지금 모드 그대로)"
  else
    say "--ssh 없음 — GPU 호스트 코드는 그 기계에서 serve 한 그대로 쓴다 (lie-detection 이 바뀌어 배포되면 cpu 로 돌아간다)"
  fi
  say "GPU 호스트 점검: http://$GPU_HOST"
  gpu_ready 1 || die "GPU 호스트가 준비되지 않았다 — 전환하지 않았다 (지금 모드 그대로)"

  proxy_env_of gpu "$GPU_HOST"
  caddy_validate || die "새 Caddy 설정을 읽지 못한다 — 전환하지 않았다"
  write_state gpu "$GPU_HOST" "$GPU_SSH"
  caddy_apply
  if ! verify_via_caddy cuda; then
    warn "Caddy 가 GPU 로 넘기지 못한다 — cpu 로 되돌린다"
    proxy_env_of cpu ""
    write_state cpu "$GPU_HOST" "$GPU_SSH"
    caddy_apply
    die "GPU 전환 실패 · cpu 로 복귀함"
  fi
  say "완료: /ai/* → GPU ($GPU_HOST). 이 서버 CPU 컨테이너는 대기(GPU 가 죽으면 Caddy 가 그쪽으로)."
  say "끌 때는 반드시 먼저: bash infra/compute.sh cpu"
}

cmd_cpu() {
  local force=0
  [ "${1:-}" = --force ] && force=1
  read_state
  say "이 서버 CPU 컨테이너 점검"
  front_dc up -d --no-deps lie-detection   # 떠 있으면 아무 일 없다
  if ! wait_health front_call 120; then
    [ "$force" = 1 ] || die "이 서버 lie-detection(CPU) 이 응답하지 않는다 — 전환하지 않았다. **GPU 를 끄지 말 것.**
    로그: docker compose -p $PROJECT -f infra/docker-compose.prod.yml logs --tail 50 lie-detection
    그래도 바꾸려면: bash infra/compute.sh cpu --force"
    warn "CPU 가 응답하지 않지만 --force 로 바꾼다"
  fi
  proxy_env_of cpu ""
  caddy_validate || die "Caddy 설정을 읽지 못한다 — 전환하지 않았다"
  write_state cpu "$GPU_HOST" "$GPU_SSH"   # 지난 GPU 호스트는 남겨 둔다(`gpu` 만 쳐도 다시)
  caddy_apply
  local rc=0
  say "CPU 셀프 테스트 (모델 4종 1건씩)"
  front_call /selftest POST 600 | check_selftest cpu || rc=1
  verify_via_caddy cpu || rc=1
  [ "$rc" = 0 ] && say "완료: /ai/* → 이 서버 CPU. 이제 GPU 인스턴스를 꺼도 된다." \
                || warn "전환은 했지만 점검에 실패한 항목이 있다 — 위 줄 확인"
  return "$rc"
}

cmd_serve() {
  local pull=0
  [ "${1:-}" = --pull ] && pull=1
  command -v nvidia-smi > /dev/null && nvidia-smi -L > /dev/null 2>&1 \
    || die "이 기계에 GPU 가 안 보인다(nvidia-smi) — GPU 판은 GPU 호스트에서만 빌드한다 (운영 서버 디스크 보호)"
  # grep -q 를 쓰지 않는다 — pipefail 에서 docker 가 SIGPIPE 를 받아 멀쩡한데도 실패로 읽힌다
  docker info 2> /dev/null | grep -i nvidia > /dev/null \
    || die "docker 에 nvidia 런타임이 없다 — nvidia-container-toolkit 설치 (infra/gpu/README.md 준비 ②)"
  [ -f "$ARDA_DIR/backend/.env" ] || die "$ARDA_DIR/backend/.env 가 없다 — 운영 서버 것을 복사 (infra/gpu/README.md 준비 ③)"
  if [ "$pull" = 1 ]; then
    say "main 으로 올린다"
    (cd "$ARDA_DIR" && git fetch -q origin main && git merge --ff-only -q origin/main)
  fi
  say "GPU 판 빌드·기동 ($(cd "$ARDA_DIR" && git rev-parse --short HEAD 2>/dev/null || echo '?'))"
  gpu_dc up -d --build lie-detection
  wait_health gpu_call 180 || die "GPU 판이 헬스에 응답하지 않는다 — 로그: docker compose -p $GPU_PROJECT logs --tail 50 lie-detection"
  [ -n "$(gpu_dc exec -T lie-detection printenv ARDA_SERVICE_TOKEN 2> /dev/null | tr -d '\r')" ] \
    || die "backend/.env 에 ARDA_SERVICE_TOKEN 이 없다 — 판정을 백엔드로 못 밀고 셀프 테스트도 닫혀 있다 (운영 것과 같은 값)"
  say "셀프 테스트 (모델 4종 1건씩 — 처음이면 모델 내려받기로 몇 분)"
  gpu_call /selftest POST 900 | check_selftest cuda || die "GPU 에서 돌지 않는 모델이 있다 — 위 줄 확인"
  say "완료: 이 기계 :${LIE_PORT:-5000} 에서 GPU 판이 돈다. 운영 서버에서: bash infra/compute.sh gpu <이 기계 사설IP>"
}

cmd_status() {
  read_state
  local h
  echo "모드(기록) : $MODE${SINCE:+  ($SINCE)}"
  [ -z "$GPU_HOST" ] || echo "GPU 호스트 : $GPU_HOST${GPU_SSH:+  · ssh $GPU_SSH}$([ "$MODE" = gpu ] || echo '  (지난번)')"
  echo "Caddy 환경 : $(caddy_env_now)"
  if h=$(front_call /health GET 5 2>/dev/null); then
    echo "CPU(이 서버): ok · $(echo "$h" | jget compute)"
  else
    echo "CPU(이 서버): 응답 없음"
  fi
  if [ -n "$GPU_HOST" ]; then
    if h=$(remote_get /health 5 2>/dev/null); then
      echo "GPU 호스트 : ok · $(echo "$h" | jget compute)"
    else
      echo "GPU 호스트 : 응답 없음$([ "$MODE" = gpu ] && echo ' ← Caddy 가 CPU 로 받고 있다. 기록 맞추기: bash infra/compute.sh cpu')"
    fi
  fi
  if caddy_running; then
    local dev; dev=$(caddy_get /health 2>/dev/null | jget compute.deception 2>/dev/null) || true
    echo "/ai/* 실제 : ${dev:-응답 없음}$([ "$dev" = cuda ] && echo ' (GPU)')$([ "$dev" = cpu ] && echo ' (이 서버 CPU)')"
  fi
}

cmd_env() {
  read_state
  proxy_env_of "$MODE" "$GPU_HOST"
  echo "LIE_PROXY=$WANT_PROXY"
  echo "LIE_GPU_UPSTREAM=$WANT_UPSTREAM"
}

# 배포 때 — GPU 모드면 GPU 호스트를 따라 올리고, 못 하거나 죽어 있으면 기록을 cpu 로.
# **배포를 실패시키지 않는다** (늘 0) — 판단은 기록에 남기고 deploy-arda.sh 가 env 로 반영한다.
cmd_on_deploy() {
  local changed=${1:-0}
  read_state
  if [ "$MODE" != gpu ]; then echo "compute: cpu"; return 0; fi
  if [ "$changed" = 1 ]; then
    if [ -z "$GPU_SSH" ]; then
      warn "lie-detection 이 바뀌었는데 GPU 호스트를 올릴 길(--ssh)이 없다 — 옛 코드로 두지 않고 cpu 로 돌린다"
      write_state cpu "$GPU_HOST" "$GPU_SSH"; return 0
    fi
    if ! remote_serve; then
      warn "GPU 호스트 갱신 실패 — cpu 로 돌린다"
      write_state cpu "$GPU_HOST" "$GPU_SSH"; return 0
    fi
  fi
  if ! gpu_ready 0; then
    warn "GPU 호스트가 준비되지 않았다 — cpu 로 돌린다"
    write_state cpu "$GPU_HOST" "$GPU_SSH"; return 0
  fi
  echo "compute: gpu 유지 ($GPU_HOST)"
}

case "${1:-}" in
  status) cmd_status ;;
  gpu) shift; cmd_gpu "$@" ;;
  cpu) shift; cmd_cpu "$@" ;;
  serve) shift; cmd_serve "$@" ;;
  env) cmd_env ;;
  on-deploy) shift; cmd_on_deploy "$@" ;;
  *) sed -n '2,25p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
