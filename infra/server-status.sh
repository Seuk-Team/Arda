#!/usr/bin/env bash
# 운영 서버 상태 한 화면 — 읽기만 한다, 아무것도 바꾸지 않는다 (2026-09-07, 인프라 오너).
#
# 왜: 디스크·컨테이너·배포·백업을 보려면 명령 다섯 개를 조합해야 했다. 주 1회 습관으로
# 볼 수 있게 한 줄로 묶는다. 경보(디스크 85% 등)는 CloudWatch 가 맡는다 — 이건 눈이다.
#
# 설치: curl -sL https://raw.githubusercontent.com/Seuk-Team/Arda/main/infra/server-status.sh -o ~/status.sh && chmod +x ~/status.sh
# 사용: ~/status.sh
set -uo pipefail

ARDA="${ARDA:-/home/ubuntu/arda}"
# compose 는 infra/ 안이다 (2026-09-09 이동). 루트 경로는 이제 없다.
COMPOSE="${COMPOSE:-$ARDA/infra/docker-compose.prod.yml}"
DISK_WARN="${DISK_WARN:-80}"   # 이 % 넘으면 빨간 표시

c() { printf '\033[%sm%s\033[0m' "$1" "$2"; }
h() { echo; c "1;36" "== $1 =="; echo; }

h "시각 · 가동"
date '+%F %T %Z'; uptime -p

h "디스크 (/)"
df -h / | tail -1 | awk -v w="$DISK_WARN" '{
  use=$5; sub("%","",use);
  mark = (use+0 >= w) ? "  <-- " w "% 넘음, 정리 필요" : "";
  printf "%s 중 %s 사용 (%s), 남은 %s%s\n", $2, $3, $5, $4, mark }'

h "메모리"
free -h | awk 'NR==2{printf "전체 %s · 사용 %s · 남음 %s\n",$2,$3,$7} NR==3{printf "스왑 %s 중 %s 사용\n",$2,$3}'

h "컨테이너"
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null || echo "(docker 접근 불가)"

h "Docker 공간 (이미지 · 빌드 캐시 — 배포 스크립트가 3GB 만 남기고 지운다)"
docker system df --format 'table {{.Type}}\t{{.TotalCount}}\t{{.Size}}\t{{.Reclaimable}}' 2>/dev/null

h "컨테이너 로그 크기 (상한: 서비스당 20MB × 3)"
if sudo -n true 2>/dev/null; then
  sudo du -sh /var/lib/docker/containers/*/ 2>/dev/null | sort -h | tail -4 | awk '{print $1, $2}' | sed -E 's#/var/lib/docker/containers/([0-9a-f]{12})[0-9a-f]*/#\1#'
else
  echo "(sudo 비밀번호 필요 — 건너뜀)"
fi

h "배포 (systemd 타이머 · 마지막 기록 · 배포된 커밋)"
printf 'arda-deploy.timer: %s\n' "$(systemctl is-active arda-deploy.timer 2>/dev/null || echo '?')"
if [[ -f "$HOME/deploy.log" ]]; then
  grep -E 'deploy (start|ok|WARN)' "$HOME/deploy.log" | tail -3
else
  echo "(deploy.log 없음)"
fi
if git -C "$ARDA" rev-parse --short HEAD >/dev/null 2>&1; then
  printf '서버 HEAD: %s  (%s)\n' "$(git -C "$ARDA" rev-parse --short HEAD)" "$(git -C "$ARDA" log -1 --format=%s | cut -c1-60)"
fi

h "DB 백업 (매일 04:00 KST → S3)"
printf 'cron: %s\n' "$(crontab -l 2>/dev/null | grep -c backup-arda-db)개 등록"
if [[ -f "$HOME/backup.log" ]]; then
  grep -E '업로드 완료|실패' "$HOME/backup.log" | tail -2
else
  echo "(backup.log 없음 — 아직 한 번도 안 돌았다)"
fi
ls -lh "$HOME/backups"/arda-*.sql.gz 2>/dev/null | awk '{print "  로컬:", $5, $9}' | tail -3

h "API 헬스 (localhost:8000)"
if out=$(curl -sf -m 5 http://localhost:8000/health 2>/dev/null); then
  echo "$out"
else
  c "1;31" "응답 없음 — docker compose logs api --tail 50"; echo
fi

h "n8n 헬스 (localhost:5678 — ADR-0030)"
if curl -sf -m 5 http://localhost:5678/healthz >/dev/null 2>&1 || curl -sf -m 5 http://localhost:5678/n8n/healthz >/dev/null 2>&1; then
  echo "ok — 편집 화면 https://api.seuk.suvisdev.cloud/n8n/ (Basic Auth, 팀 공유)"
else
  c "1;31" "응답 없음 — 컨테이너가 없으면 아직 미설치(07-deploy n8n 절), 있으면 docker compose logs n8n --tail 50"; echo
fi
ls -lh "$HOME/backups"/n8n-*.tar.gz 2>/dev/null | awk '{print "  n8n 백업:", $5, $9}' | tail -1

h "앵커 게시 (매일 09:10 KST, GitHub Actions)"
echo "여기선 안 보인다 — gh run list --workflow anchor-publish.yml --limit 3 (관리자 PC)"
echo
