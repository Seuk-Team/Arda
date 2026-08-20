# infra — Docker · AWS · CI/CD

> 아직 코드 없음.

- Docker Compose (로컬: api + postgres + 워커)
- AWS: EC2(api·워커) · S3(이력서) · SES(메일) · SQS(메일 큐)
- CI/CD: GitHub Actions (J4) — 테스트 → 빌드 → 배포
- K8s는 쓰지 않는다 ([../docs/adr/0001-k8s-제외.md](../docs/adr/0001-k8s-제외.md))
- 시크릿은 GitHub Secrets / `.env` — repo에 커밋 금지
