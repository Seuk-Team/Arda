# infra — Docker · AWS · CI/CD

- `docker-compose.prod.yml` — EC2 운영 compose (2026-09-02 서버에서 회수). 서버 `~/arda/docker-compose.prod.yml` 이 진실이고 여기는 사본 — 서버를 바꾸면 여기도 같은 커밋에서.
- `Caddyfile` — 운영 리버스 프록시(`api.seuk.suvisdev.cloud` → api:8000, `/demo/*` 정적). 위와 같은 규칙.
- 로컬 개발 compose 는 저장소 루트 `docker-compose.yml`.
- CI: `.github/workflows/ci.yml` (백엔드 pytest + 프론트 빌드, 2026-09-02). **배포는 자동**(2026-09-04) — 서버 systemd 타이머가 2분마다 main 을 폴링해 pull→build→alembic→up. 절차·로그 위치는 [07-deploy](../docs/00_overview/07-deploy.md).
- `anchor-publish.yml` — 매일 09:10 KST 무결성 앵커 게시(Sepolia + OpenTimestamps). 개인키는 Actions secret, 서버엔 없다 (ADR-0028).
- `server-status.sh` — 서버 상태 한 화면(디스크·컨테이너·배포·백업·헬스). 읽기만. 서버 `~/status.sh` 로 복사해 주 1회 본다 (2026-09-07).
- `backup-arda-db.sh` — 운영 DB 매일 백업 → S3 `arda-db-backups-seuk` (2026-09-07). 서버 `~/backup-arda-db.sh` 로 복사해 cron 이 돈다. 설치·복원은 07-deploy "DB 백업" 절.
- AWS: EC2(api·워커) · S3(이력서) · SES(메일) · SQS(메일 큐). 권한 모델은 07-deploy "주의" 절.
- K8s는 쓰지 않는다 ([ADR-0001](../docs/03_decision/0001-k8s-제외.md)).
- 시크릿은 서버 `.env` — repo 에 커밋 금지. `.env.example` 은 `backend/`.
