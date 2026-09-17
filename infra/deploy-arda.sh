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
#
# 2026-09-14: **선택적 빌드**. 옛 스크립트는 매 배포마다 `api·lie-detection` 둘 다
# 재빌드 → 프론트만 바꿔도 10분씩 걸리고 lie-detection 이 torch 200MB 재다운로드.
# 이제 `$LOCAL..$REMOTE` diff 로 어느 서비스가 실제로 바뀌었는지 판정한다.
#
# 규칙:
#   backend/ 또는 infra/docker-compose.prod.yml 바뀜  → api 재빌드
#   ai/lie-detection/ 바뀜                            → lie-detection 재빌드
#   그 외만 바뀜 (docs · frontend · ai/qwen-training) → 재빌드 없음 (up -d 로 재구성만)
# compose 파일이 바뀌면 두 서비스 다 안 바뀌더라도 up -d 로 반영은 해야 하므로,
# 이후의 `up -d` 는 조건 없이 실행한다 (이 아래 그대로).
CHANGED=$(git diff --name-only "$LOCAL" "$REMOTE" 2>>"$LOG" || true)
BUILD_TARGETS=""
if echo "$CHANGED" | grep -qE "^(backend/|infra/docker-compose\.prod\.yml)"; then
  BUILD_TARGETS="api"
fi
if echo "$CHANGED" | grep -qE "^ai/lie-detection/"; then
  BUILD_TARGETS="$BUILD_TARGETS lie-detection"
fi
BUILD_TARGETS=$(echo "$BUILD_TARGETS" | xargs)  # 앞뒤 공백 정리
if [ -n "$BUILD_TARGETS" ]; then
  echo "$(date -Is) build 대상: $BUILD_TARGETS" >> "$LOG"
  docker compose -p arda -f infra/docker-compose.prod.yml build $BUILD_TARGETS >> "$LOG" 2>&1
else
  echo "$(date -Is) build 스킵 (백엔드·lie-detection 변경 없음)" >> "$LOG"
fi
# 스키마 이행 (기동 전에) — 컬럼 추가/변경은 create_all 이 못 함. #17
echo "$(date -Is) alembic upgrade..." >> "$LOG"
docker compose -p arda -f infra/docker-compose.prod.yml run --rm api /app/.venv/bin/alembic upgrade head >> "$LOG" 2>&1
# `--remove-orphans` — compose 에서 제거된 서비스의 컨테이너를 자동 정리 (2026-09-14).
# 없으면 삭제된 서비스가 계속 살아 있다: 09-14 SQS 워커 폐기(#213) 후 이 스크립트가 자동
# 배포는 했지만 arda-worker-1 이 그대로 남아 SQS 를 계속 폴링했다. 수동 `docker rm -f`
# 필요했음. 이 옵션은 프로젝트 이름(`-p arda`) 에 속하지만 compose 파일에 없는 컨테이너만
# 대상이라 수동 띄운 게 없는 우리 환경에서 안전.
docker compose -p arda -f infra/docker-compose.prod.yml up -d --remove-orphans >> "$LOG" 2>&1
# 헬스는 최대 60초 재시도 — 10초 한 번은 api 가 뜨는 중이라 가짜 WARN 이 났다
# (09-09 15:12Z a6cb5c3: 컨테이너는 다 떴는데 "health check 실패" 로 기록됨).
HEALTHY=0
for _ in $(seq 1 20); do
  if curl -sf http://localhost:8000/health >> "$LOG" 2>&1; then HEALTHY=1; break; fi
  sleep 3
done
if [ "$HEALTHY" = 1 ]; then
  echo "$(date -Is) deploy ok: $REMOTE" >> "$LOG"
else
  echo "$(date -Is) deploy WARN: health check 60초 실패 — 로그 확인 필요" >> "$LOG"
fi

# uvicorn 워커 1개 재확인 (2026-09-17 우정 B9 지적).
# 세션 방·티켓·잠금·STT 모델이 프로세스 인메모리라 여러 워커면 지원자·담당자가
# 다른 프로세스에 앉아 서로를 못 본다. compose command 에 `--workers 1` 이 명시되어
# 있지만 배포 뒤 실제 프로세스 수를 한 번 더 본다. 2개 이상이면 즉시 알림.
WORKERS=$(docker exec arda-api-1 sh -c 'ps -ef | grep -c "uvicorn app.main:app.*--port 8000$"' 2>/dev/null || echo "0")
if [ "$WORKERS" != "1" ]; then
  echo "$(date -Is) deploy WARN: uvicorn 워커 $WORKERS 개 (기대 1) — compose command 확인 필요" >> "$LOG"
else
  echo "$(date -Is) uvicorn worker=1 확인" >> "$LOG"
fi
docker image prune -f > /dev/null 2>&1 || true
docker builder prune -f --keep-storage 3g > /dev/null 2>&1 || true
