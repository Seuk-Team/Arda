# infra — Docker · AWS · CI/CD

- `docker-compose.prod.yml` — EC2 운영 compose (2026-09-02 서버에서 회수). 서버 `~/arda/docker-compose.prod.yml` 이 진실이고 여기는 사본 — 서버를 바꾸면 여기도 같은 커밋에서.
- `Caddyfile` — 운영 리버스 프록시(`api.seuk.suvisdev.cloud` → api:8000, `/demo/*` 정적). 위와 같은 규칙.
- 로컬 개발 compose 는 저장소 루트 `docker-compose.yml`.
- CI: `.github/workflows/ci.yml` (백엔드 pytest + 프론트 빌드, 2026-09-02). 배포 자동화(J4)는 아직 수동 — 절차는 [07-deploy](../docs/00_overview/07-deploy.md).
- AWS: EC2(api·워커) · S3(이력서) · SES(메일) · SQS(메일 큐). 권한 모델은 07-deploy "주의" 절.
- K8s는 쓰지 않는다 ([ADR-0001](../docs/03_decision/0001-k8s-제외.md)).
- 시크릿은 서버 `.env` — repo 에 커밋 금지. `.env.example` 은 `backend/`.
