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

## 3. 브랜치 규칙 + 배포 — 이제 자동이다

**기본 규칙 (2026-09-04 확정): main 직접 푸시 금지 — 브랜치 만들어 PR로
머지한다.** 승인은 필요 없다(각자 자기 PR 을 바로 머지) — 단 **CI 가
초록일 때만**. GitHub 이 main 직접 푸시를 막아 주므로 규칙을 외울 필요는
없고, 브랜치에서 시작하는 습관만 들이면 된다.

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
4. 주요 위치:
   - EC2 인스턴스 `arda-api` — 백엔드 · Caddy · **n8n**
   - S3 `arda-resumes-seuk` — 이력서 저장
   - S3 `arda-db-backups-seuk` — 매일 04:00 DB 백업
   - CloudFormation 스택 `arda-alarms` — 경보 6개(디스크·백업·API·메모리·n8n·EC2 자동 복구)

**AWS 축소 방향 (ADR-0031, 2026-09-08 확정)**: 예산 만료 (10-27) 뒤에도 서비스가 돌아야 해서 SES · SQS · SNS · CloudFormation 은 self-host 대안 뒤로 물러난다. 콘솔에 SQS `arda-mail` 이 아직 보이지만 **더 이상 쓰지 않는다** — 메일은 n8n 으로 이관됐다. 자세한 것은 아래 §6.

## 6. n8n 워크플로 열람 (선택 · 메일과 알림 담당)

발송되는 메일 흐름을 사람이 볼 수 있게 도식으로 만들어 둔 것. 문구·조건·헤더를 바꾸려면 여기에서 한다.

1. 접속: https://api.seuk.suvisdev.cloud/n8n/
2. Basic Auth 자격 (`arda / <비밀번호>`): 팀 채널·DM 에서 확인 (여기 평문으로 안 남긴다)
3. 워크플로 `stage-changed`: 단계 변경 → 내부 API 로 본문 렌더 → **팀 계정(ssuvisdev@gmail.com) 지메일 SMTP** 로 발송 → 결과 기록
4. 참고 ADR: [ADR-0030 n8n 알림·메일 자동화 분리](../03_decision/0030-n8n-알림-자동화-분리.md) · [ADR-0031 AWS 최소화](../03_decision/0031-aws-최소화.md)

> **바꾸는 절차는 코드 커밋 없이 UI 에서 가능하지만, 저장소의 `infra/n8n/stage-changed.json` 도 같이 export 해 두면** 다음 서버·워크스페이스로 이식할 때 자동으로 복원된다.

## 7. 로컬 개발 — 달라진 것 없음

- 기존대로 루트 `docker-compose.yml` + `backend/.env`(`.env.example` 참고)
- dev 프록시 기본 타깃만 새 API 로 바뀌었다(`frontend/app/vite.config.ts`) —
  로컬 백엔드를 띄우면 기존처럼 `VITE_DEV_API_TARGET` 으로 덮으면 된다

## 8. 알아둘 운영 상태

- **메일은 실발송** (2026-09-08 부터). `MAIL_DISPATCH=n8n` 이 기본이며 n8n 이 **팀 지메일 SMTP** 로 보낸다. AWS SES 는 리허설 통과 후 폐기 예정 (ADR-0031). 지원자 이메일이 바뀌었는지 자기 화면에서 확인할 때만 실제 발송이 일어난다
- **DB 는 새로 시작**(빈 상태) — 옛 서버의 과정용 데이터는 이관하지 않았다
- **거짓말 탐지는 GPU 가 필요 없다** (scikit-learn + mediapipe, CPU) — 백엔드 EC2 를
  **t3.medium(4GB)** 으로 올려 같은 서버에 붙인다(2026-09-07, PR #42). 메모리만 문제였다
- **GPU 서버(g4dn.xlarge)는 로컬 STT·sLLM(qwen) 시연이 필요할 때만** — 쿼터 승인 후
  만들되 **켜고 끄는 전제**다. AWS 예산이 총 **$400 · 2026-10-27 까지**라 24시간
  가동(월 ≈$470)은 불가. 8시간×20일이면 ≈$105
- 서버 SSH·AWS 관리·비용은 suvisdev 소관 — 인프라 문제는 팀 채널에

## 9. 2026-09-07 에 바뀐 것 (운영)

- **앵커 체인 Polygon Amoy → Ethereum Sepolia** (PR #29). Amoy faucet 이 전부 메인넷 잔액을 요구해 막혔다. Actions secret 6개 등록 완료, 매일 09:10 자동 게시 초록. 탐색기는 sepolia.etherscan.io
- **DB 매일 04:00 S3 백업** · **컨테이너 로그 상한** · **배포마다 이미지·빌드 캐시 정리** (디스크 76%→45%)
- **CloudWatch 경보 3개** (디스크 ≥85% · 백업 30h 넘김 · API 죽음) → suvisdev 메일. 서버 `~/status.sh` 로 한 화면 확인
- **OpenAI STT 키** 서버 반영 (수택 개인 결제, $5 선불·월 $5 한도). 음성 답변(PR #40) 전사 가능
- 저장소 옛 주소(`api.arda.seuk.cloud`) 정리 → 정본 `api.seuk.suvisdev.cloud` (PR #30)
- 규칙: **ADR 은 오너가 쓰면 확정, 팀장 확정 대기 없음** (PR #49, [03-conventions](03-conventions.md))
- Discord `#github` 알림은 저장소 이관 때 끊겼다 — 웹후크 재등록 예정(서버 소유자 woojeongalex 권한 필요)

## 10. 2026-09-08 에 바뀐 것 (인프라 축소 · 메일 이관 · 모델 확정)

- **AWS 최소화 방향 확정 ([ADR-0031](../03_decision/0031-aws-최소화.md))**: EC2 · S3 만 남기고 SES · SQS · CloudWatch · SNS · CloudFormation 은 self-host 대안 뒤로. 10-27 예산 만료 대비. 로컬 PC 로 전체 스택 복제 실증 완료 (`infra/local/`)
- **메일 발송이 n8n → Gmail SMTP 로 이관 완료 ([ADR-0030](../03_decision/0030-n8n-알림-자동화-분리.md))**. `MAIL_DISPATCH=n8n` 기본. `worker` 의 SES 코드는 폴백으로만 남음
- **추론 모델 3종 확정 ([ADR-0032](../03_decision/0032-추론-모델-3종-확정.md))**: 표정 = ViT (소연 학습 완료, FER2013 69.84%) · 음성 = Whisper large-v3-turbo + faster-whisper · sLLM = Qwen3-8B (팀이 직접 학습 예정)
- **지원자 앱 로그인 도입 ([ADR-0033](../03_decision/0033-지원자-앱-로그인.md))**: 이메일 + 생년월일 8자리. 지원 폼에 생년월일 입력 추가 (선택 항목)
- **회사 소개 표 도입** (`company_profile` · PR #89): 회사명·미션·문화가 아르 시스템 프롬프트에 자동 주입되고 메일 `{회사명}` 도 이 표에서 치환된다. 다른 회사가 이 코드를 갈아 끼우려면 이 표만 채우면 된다 — 템플릿은 [docs/06_company/00-회사-소개.md](../06_company/00-회사-소개.md)
- **Cloudflare TURN 자격 자동 발급** (PR #82): 24시간 만료를 API 가 스스로 갱신·캐시. `RTC_ICE_SERVERS` 수동 등록 불필요
- **아르 동명이인 선택 버튼** (PR #98): "홍서우 3명" 상황에서 텍스트 표 대신 클릭 가능한 버튼 줄을 낸다. 담당자가 ID 를 손으로 치지 않아도 됨
- **UI 3종** (PR #94): 시스템 발송 이력 접기 · 성향 설문·AI 면접이 각 단계에 진입한 뒤 표시 · 스크롤바 시각적 숨김
