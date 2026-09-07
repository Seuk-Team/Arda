#!/usr/bin/env bash
# 운영 DB 백업 — 매일 pg_dump 를 gzip 으로 떠서 S3 에 올린다 (2026-09-07, 인프라 오너).
#
# 왜 있나: 서버는 EC2 한 대, DB 는 EBS 볼륨 하나다. 인스턴스 사고 한 번이면 지원자
# 개인정보와 무결성 원장이 같이 사라진다. 특히 chain_publications.proof(OTS 증명)는
# "잃어버리면 다시 못 만든다"(ADR-0028). 08/31 에 손으로 한 번 뜬 것 말고 백업이 없었다.
#
# 어디서 도나: 서버 /home/ubuntu/backup-arda-db.sh 로 복사해 cron 이 매일 04:00 KST 에 돈다.
#   0 19 * * * /home/ubuntu/backup-arda-db.sh >> /home/ubuntu/backup.log 2>&1
#
# 권한 모델: 서버의 IAM 유저(arda-server)는 백업 버킷에 **쓰기(PutObject)만** 있다.
# 읽기·삭제가 없어서 서버가 털려도 백업을 지우거나 내려받지 못한다. 복원은 관리자
# (suvisdev 콘솔)가 한다 — 절차는 docs/00_overview/07-deploy.md "백업" 절.
#
# 필요한 것: awscli (`sudo apt-get install -y awscli`), ~/arda/.env 의 AWS_* 키,
#            환경변수 BACKUP_BUCKET (없으면 아래 기본값).
set -euo pipefail

COMPOSE="${COMPOSE:-/home/ubuntu/arda/docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-/home/ubuntu/arda/.env}"
BACKUP_BUCKET="${BACKUP_BUCKET:-arda-db-backups-seuk}"
LOCAL_DIR="${LOCAL_DIR:-/home/ubuntu/backups}"
KEEP_LOCAL="${KEEP_LOCAL:-3}"   # 로컬에는 최근 N개만. 진짜 보관은 S3(수명주기 30일)

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="arda-${STAMP}.sql.gz"
mkdir -p "$LOCAL_DIR"
OUT="${LOCAL_DIR}/${FILE}"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

# AWS 키는 서버 .env 것(arda-server)을 그대로 쓴다. 파일 전체를 source 하지 않는다 —
# 다른 시크릿까지 이 프로세스 환경에 실을 이유가 없다.
if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r k v; do
    case "$k" in
      AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_REGION) export "$k=${v%\"}" ;;
    esac
  done < <(grep -E '^(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_REGION)=' "$ENV_FILE" | sed -E 's/="?/=/')
fi
export AWS_DEFAULT_REGION="${AWS_REGION:-ap-northeast-2}"

log "덤프 시작 → $OUT"
# 컨테이너 안의 POSTGRES_USER/DB 를 그대로 쓴다 — 여기 비밀번호를 적지 않는다.
# --no-owner: 복원하는 쪽 사용자 이름이 달라도 그대로 들어가게.
docker compose -f "$COMPOSE" exec -T db sh -c \
  'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges' \
  | gzip -9 > "$OUT"

# 빈 파일·깨진 gzip 을 S3 에 올려 "백업 있다"고 착각하는 게 최악이다. 두 번 확인한다.
SIZE=$(stat -c %s "$OUT")
if (( SIZE < 1024 )); then
  log "실패: 덤프가 ${SIZE}B 뿐이다 — DB 컨테이너가 죽었거나 빈 DB"; rm -f "$OUT"; exit 1
fi
gzip -t "$OUT"

aws s3 cp "$OUT" "s3://${BACKUP_BUCKET}/db/${FILE}" --only-show-errors
log "업로드 완료 s3://${BACKUP_BUCKET}/db/${FILE} (${SIZE}B)"

# 로컬은 최근 N개만 남긴다 — 19GB 디스크다 (09/01 디스크 고갈 전력)
ls -1t "${LOCAL_DIR}"/arda-*.sql.gz 2>/dev/null | tail -n +"$((KEEP_LOCAL + 1))" | xargs -r rm -f
log "끝"
