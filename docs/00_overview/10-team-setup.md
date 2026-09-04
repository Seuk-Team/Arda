# 10. 팀원 셋업 — 새 인프라 (2026-09-04 이전 완료)

> 운영 서버·AWS·저장소가 전부 바뀌었다. **이 문서 하나로 각자 5분이면 끝난다.**
> 배경·상세는 [07-deploy](07-deploy.md) 상단 공지와 [09-handover](09-handover.md) 2차 절.

## 1. 저장소 remote 교체 (전원 필수)

구 저장소 `Team-Seuk/Arda` 는 삭제됐다. 로컬 클론에서 한 줄만 실행:

```bash
git remote set-url origin https://github.com/Seuk-Team/Arda.git
git fetch origin        # 이게 성공하면 끝
```

## 2. 새 주소 (북마크 교체)

| 무엇 | URL |
|---|---|
| 서비스(프론트) | https://seuk.suvisdev.cloud |
| API | https://api.seuk.suvisdev.cloud |
| Swagger | https://api.seuk.suvisdev.cloud/docs |
| OpenAPI 스펙 | https://api.seuk.suvisdev.cloud/openapi.json |
| 공개 지원 링크 | `https://seuk.suvisdev.cloud/apply/<token>` |

## 3. 배포 — 이제 자동이다

- **프론트**: main 머지 → Vercel이 1~2분 내 자동 배포
- **백엔드**: main 머지 → 서버가 **2분마다 main 을 폴링**해 pull→build→up
  (빌드 포함 총 5~10분). **"배포해 주세요" 요청이 더 이상 필요 없다.**
- 반영 확인: `https://api.seuk.suvisdev.cloud/health` 가 ok 면 살아 있는 것.
  배포가 됐는지는 서버 관리자(suvisdev)에게 `~/deploy.log` 확인 요청
- 주의: **main 머지가 곧 프로덕션 배포**다. CI(pytest·프론트 빌드)가 초록인
  PR만 머지할 것

## 4. 서비스 admin 계정

- production 은 공개 가입이 잠겨 있다. **기존 admin(suvisdev)에게 요청**하면
  Swagger 의 `POST /api/v1/auth/signup` 으로 각자 이메일 계정을 만들어 준다
- 초기 비밀번호는 개별 전달 → 로그인 후 변경 권장

## 5. AWS 콘솔 열람 (선택)

서버·큐·메일 상태를 직접 보고 싶은 사람용. 리소스 조회만 되고 변경·삭제는
안 되는 권한(ViewOnlyAccess)이다.

1. 로그인: https://suvisdev.signin.aws.amazon.com/console
2. 계정(유저명·임시 비밀번호)은 suvisdev가 **개별 DM**으로 발급 — 첫 로그인
   때 비밀번호를 새로 만든다
3. 로그인 후 **우측 상단 리전을 "서울(ap-northeast-2)"로** 바꿔야 리소스가 보인다
4. 주요 위치: EC2 인스턴스 `arda-api`(백엔드) · S3 `arda-resumes-seuk`(이력서)
   · SQS `arda-mail`(메일 큐) · SES(발신 도메인)

## 6. 로컬 개발 — 달라진 것 없음

- 기존대로 루트 `docker-compose.yml` + `backend/.env`(`.env.example` 참고)
- dev 프록시 기본 타깃만 새 API 로 바뀌었다(`frontend/app/vite.config.ts`) —
  로컬 백엔드를 띄우면 기존처럼 `VITE_DEV_API_TARGET` 으로 덮으면 된다

## 7. 알아둘 운영 상태

- **메일은 아직 dry-run** (`MAIL_DRY_RUN=1`) — SES 프로덕션 승인 대기 중.
  발송 테스트는 `success@simulator.amazonses.com` 수신자로. 승인되면 공지한다
- **DB 는 새로 시작**(빈 상태) — 옛 서버의 과정용 데이터는 이관하지 않았다
- **GPU 서버는 준비 중** — g4dn.xlarge 쿼터 승인 후 생성 예정. 거짓말 탐지 등
  GPU 워크로드는 그쪽에 올린다(백엔드 EC2 는 t3.small, GPU 없음)
- 서버 SSH·AWS 관리·비용은 suvisdev 소관 — 인프라 문제는 팀 채널에

