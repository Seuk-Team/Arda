"""company_profile 시드 — 코드브릿지 (플레이스홀더 회사)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-08

**왜 시드를.** 0013 이 만든 표는 `(id=1, name='')` 한 행이 초기값이었다.
이 상태로는 아르가 회사 관련 질문에 답할 때 회사명 없이 답하거나
`mail.COMPANY_NAME` 환경변수(=Arda) 로 폴백한다 — 데모·시연 회사가 정해질
때까지 임시로 쓸 회사 프로필을 넣는다.

**코드브릿지는 실재 회사가 아니다.** 데모용 플레이스홀더다. 실제 회사가
정해지면 이 값을 UPDATE 로 갈아 끼우거나 `docs/06_company/00-회사-소개.md`
를 새로 채운 뒤 이 마이그레이션과 같은 형태의 뒤이은 리비전으로 값을 바꾼다.

**멱등성.** 0013 이 이미 (1, '', now()) 로 한 행을 만들어 뒀으므로 여기서는
UPDATE 만 한다. 두 번 돌아도 값이 같아진다.

**PR #92 와의 번호 충돌.** PR #92 (feat/agent-traces-and-eval-cases) 도
0014 를 쓴다. 이 마이그레이션이 main 에 먼저 들어가므로 PR #92 는 머지 전에
0015 로 리넘버 필요.
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


NAME = "코드브릿지"
TAGLINE = "코드로 팀과 팀을 잇는다"
HR_EMAIL = "hr@codebridge.dev"
WEBSITE = "https://codebridge.dev"

# 아르 시스템 프롬프트 헤더에 그대로 들어가는 한 단락.
DESCRIPTION = (
    "코드브릿지는 웹·모바일 앱 개발을 대신 만들어 주는 개발 스튜디오입니다. "
    "2022년 서울 성수에서 창업했고 정규직 20명 규모입니다. "
    "스타트업·중견기업의 아이디어를 3~6개월 안에 실제 서비스로 만드는 것을 "
    "반복해 왔습니다. 기획·디자인·개발·운영을 한 팀이 처음부터 끝까지 책임집니다."
)

# 아르 프롬프트 뒤에 그대로 붙는 회사 상세. docs/06_company/00-회사-소개.md
# 의 §5·§6·§8 을 압축했다. 원본 문서가 진실 — 여기서 값이 바뀌면 문서도 같이.
NARRATIVE = """\
## 우리의 가치 세 가지

1. **정확한 판단** — 회의보다 문서로 결정한다. 결정의 근거를 기록으로 남긴다.
2. **짧은 문장** — 코드·문서·회의 발언 모두 짧게. 길면 이해가 아니라 방어다.
3. **오너십** — 자기 도메인은 자기가 판단한다. 팀장 게이트 없음.

## 일하는 방식

- **근무 시간**: 코어 타임 없음. 재량 근무 (주 40시간 기준).
- **근무 장소**: 하이브리드 (주 2일 사무실 · 주 3일 재택). 신입 첫 3개월은 주 3일 사무실 권장.
- **회의**: 하루 최대 60분 제한. 30분 넘는 회의는 사전 안건 문서 필수.
- **문서**: 단일 원본 정책. 결정·기획·API·ADR 모두 저장소에 마크다운.
- **결정 방식**: 도메인 오너제. 오너 결정 그대로 진행 — 팀장 승인 절차 없음.
- **코드 리뷰**: PR 이 곧 리뷰. 자기 PR 자기가 머지 (CI 초록 확인).
- **배포**: main 머지 = 2분 뒤 프로덕션 자동 배포.

## 채용 원칙

우리와 잘 맞는 사람:
- 문서로 생각을 정리해 본 사람
- 결정을 스스로 내려 본 사람 (승인 기다리는 것이 편하지 않은 사람)
- 자기 도메인 밖의 코드도 필요하면 고쳐 본 사람

우리와 잘 안 맞는 사람 (정직하게):
- 세세한 지시가 있어야 편한 사람
- 회의로 결정하는 것을 선호하는 사람
- 완벽할 때까지 릴리스하지 않는 사람

**공정성 원칙.** 나이·성별·출신 지역·학교로 뽑지 않는다. 이력서 상단 학력은
검토 시 가림.

**답장 원칙.** 합격·불합격 모두 지원 후 영업일 7일 안에 답장. 실무진이 아닌
경우 아르(에이전트) 가 대신 쓴다는 점을 답장에 명시.

## 아르에게 알리는 톤

- 존댓말. 단정하고 짧게.
- 지원자·담당자 모두 "{이름} 님" 호칭.
- 이모지 안 씀.
- 회사가 정하지 않은 것은 지어내지 않는다 — "채용 담당자에게 다시 물어봐 드릴게요" 로 넘긴다.
"""


def upgrade() -> None:
    # 0013 이 만든 한 행을 갱신. 두 번 돌아도 결과가 같도록 조건 절 없이 UPDATE.
    op.execute(
        sa.text(
            "UPDATE company_profile SET "
            "name = :name, tagline = :tagline, hr_email = :hr_email, "
            "website = :website, description = :description, narrative = :narrative, "
            "updated_at = now() "
            "WHERE id = 1"
        ).bindparams(
            name=NAME,
            tagline=TAGLINE,
            hr_email=HR_EMAIL,
            website=WEBSITE,
            description=DESCRIPTION,
            narrative=NARRATIVE,
        )
    )


def downgrade() -> None:
    # 값을 초기 상태(빈 문자열 + NULL) 로 되돌린다.
    op.execute(
        "UPDATE company_profile SET "
        "name = '', tagline = NULL, hr_email = NULL, website = NULL, "
        "description = NULL, narrative = NULL, updated_at = now() "
        "WHERE id = 1"
    )
