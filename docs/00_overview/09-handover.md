# 09. 인수인계 — 2026-09-02

> 2026-09-02 기준으로 바꾼 것 / 없어진 것 / 넘긴 것 목록입니다.

## 바꾼 것

- 백엔드 재배포 `f227673` (09/02) — 서비스 정상, `/health` ok
- 검증 데이터 삭제: 지원자 24 · 공고 3 · S3 객체
- 서버 `.env` 의 AWS 키 → IAM 유저 `arda-server` 것으로 교체
- 운영 DB: bestcow 계정 비활성·익명화, 테스트 지원자 id 7 삭제, 시연 지원자 id 12 메일 → `seukathon@gmail.com`
- 서버에만 있던 `docker-compose.prod.yml`·`Caddyfile` → `infra/`

## 없어진 것

- Anthropic, OpenAI API 키 — 제 개인 결제라 폐기했습니다. 서버 `.env` 에 남은 값은 죽은 키이니 누군가가 새로 결제해서 쓰시면 됩니다.
- 팀장 역할 — 계획, 문서 관리, 코드리뷰, 작업 분배, 발표, 총괄, 인프라 등은 앞으로 나눠서 맡으시면 됩니다.

## 넘긴 것

| 무엇                        | 누구에게                                                  |
| --------------------------- | --------------------------------------------------------- |
| AWS 콘솔 (EC2·S3·SES·SQS)   | woojeongalex — IAM 유저, 그룹 `arda-ops`(PowerUserAccess) |
| GitHub org `Team-Seuk` 오너 | woojeongalex                                              |
| Discord 서버                | woojeongalex                                              |
| Vercel `arda` 프로젝트      | woojeongalex — 이전 링크 발급.                            |

## 남긴 것

- AWS 계정 루트 — 학원이 이미 제 계정으로 400달러 넣어놨으니까 이건 과정 끝날때까지 유지하겠습니다
- 도메인 `seuk.cloud` (가비아) — 프로젝트 끝날 때까지 두겠습니다

상세는 [ADR-0025](../03_decision/0025-운영-권한-이관.md), [07-deploy 2026-09-02 절](07-deploy.md), 커밋 이력.
