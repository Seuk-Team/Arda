#!/usr/bin/env bash
# 서버 상태 숫자 3개를 CloudWatch 로 보낸다 — 10분마다 cron (2026-09-07, 인프라 오너).
#
# 왜: 디스크가 차는지·백업이 빠졌는지·API 가 죽었는지를 사람이 주 1회 보는 대신,
# 숫자를 보내 두고 CloudWatch 알람이 넘으면 SNS 메일을 쏘게 한다. 사람이 안 봐도 된다.
# 에이전트를 깔지 않는다 — 이미 있는 aws-cli 로 put-metric-data 만 부른다.
#
# 비용: CloudWatch 상시 무료 구간(사용자 지정 지표 10개·알람 10개·API 100만 건/월)
# 안이다. 여기서 보내는 건 지표 3개 · 월 1.3만 건.
#
# 지표 (네임스페이스 Arda, 차원 Host=arda-api):
#   MemUsedPercent    (total-available)/total. 알람: >= 90 (2회) — 거짓말 탐지가 같은 서버라 본다
#   DiskUsedPercent   / 의 사용률.               알람: >= 85
#   BackupAgeHours    마지막 로컬 백업 파일 나이.  알람: >= 30 (하루 1회인데 빠졌다)
#   ApiHealthy        localhost:8000/health 가 ok 면 1, 아니면 0.
#                     알람: < 1. **누락 데이터도 경보로** 두면 인스턴스가 통째로
#                     죽어 아무 숫자도 안 올 때도 울린다.
#
# 설치:
#   curl -sL https://raw.githubusercontent.com/Seuk-Team/Arda/main/infra/push-metrics.sh -o ~/push-metrics.sh && chmod +x ~/push-metrics.sh
#   ( crontab -l; echo '*/10 * * * * /home/ubuntu/push-metrics.sh >> /home/ubuntu/metrics.log 2>&1' ) | crontab -
# 권한: IAM 유저 arda-server 에 cloudwatch:PutMetricData (07-deploy "모니터링" 절).
set -uo pipefail

ENV_FILE="${ENV_FILE:-/home/ubuntu/arda/.env}"
LOCAL_DIR="${LOCAL_DIR:-/home/ubuntu/backups}"
NAMESPACE="${NAMESPACE:-Arda}"
HOST_DIM="${HOST_DIM:-arda-api}"

if [[ -f "$ENV_FILE" ]]; then
  while IFS='=' read -r k v; do
    case "$k" in
      AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_REGION) export "$k=${v%\"}" ;;
    esac
  done < <(grep -E '^(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_REGION)=' "$ENV_FILE" | sed -E 's/="?/=/')
fi
export AWS_DEFAULT_REGION="${AWS_REGION:-ap-northeast-2}"

# 1) 디스크
disk=$(df -P / | awk 'NR==2{sub("%","",$5); print $5}')

# 2) 백업 나이 — 가장 최근 로컬 파일 기준. 파일이 하나도 없으면 9999 (= 알람)
newest=$(ls -1t "$LOCAL_DIR"/arda-*.sql.gz 2>/dev/null | head -1 || true)
if [[ -n "$newest" ]]; then
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$newest") ) / 3600 ))
else
  age_h=9999
fi

# 2b) 메모리 — available 기준 (buff/cache 는 필요하면 비워지므로 used 로 재면 과장된다)
mem=$(free | awk '/Mem:/{printf "%d", (1-$7/$2)*100}')

# 3) API 헬스
if curl -sf -m 5 http://localhost:8000/health 2>/dev/null | grep -q '"ok"'; then
  healthy=1
else
  healthy=0
fi

ts=$(date -u +%FT%TZ)
aws cloudwatch put-metric-data --namespace "$NAMESPACE" --metric-data \
  "MetricName=DiskUsedPercent,Dimensions=[{Name=Host,Value=$HOST_DIM}],Unit=Percent,Value=$disk,Timestamp=$ts" \
  "MetricName=BackupAgeHours,Dimensions=[{Name=Host,Value=$HOST_DIM}],Unit=None,Value=$age_h,Timestamp=$ts" \
  "MetricName=ApiHealthy,Dimensions=[{Name=Host,Value=$HOST_DIM}],Unit=None,Value=$healthy,Timestamp=$ts" \
  "MetricName=MemUsedPercent,Dimensions=[{Name=Host,Value=$HOST_DIM}],Unit=Percent,Value=$mem,Timestamp=$ts" \
  && echo "[$ts] disk=${disk}% mem=${mem}% backup_age=${age_h}h api=${healthy}" \
  || echo "[$ts] 전송 실패 (disk=${disk}% mem=${mem}% backup_age=${age_h}h api=${healthy}) — IAM cloudwatch:PutMetricData 확인"
