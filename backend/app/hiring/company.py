"""회사 소개 (company_profile) — 조회·기본값 폴백.

`docs/06_company/00-회사-소개.md` 가 사람이 쓰는 원본 문서, 이 모듈이 그 값을 DB
로 옮겨 아르 프롬프트·메일 변수 치환에 쓴다. 단일 회사 전제 (ADR 없음, 프로젝트
범위 밖).

**폴백 규약.** `company_profile` 행이 아직 채워지지 않았거나 `name` 이 빈 문자열
이면, `mail.COMPANY_NAME` 환경변수의 값(기본 "Arda") 을 쓴다. 관리자가 값을 넣으면
그 순간부터 그 값이 이긴다. 코드는 어느 쪽인지 몰라도 된다 — 이 모듈에 물어보면
"지금 쓰고 있는 회사명" 을 답한다.
"""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompanyProfile

# `mail.py` 의 상수를 여기서 참조하지 않는다 — 순환 import 를 만든다.
# 두 곳이 같은 환경변수를 읽으므로 결과는 같다.
_ENV_FALLBACK_NAME = os.getenv("COMPANY_NAME", "Arda")


def get_profile(db: Session) -> CompanyProfile:
    """단일 회사 소개 행을 반환한다. 없으면 빈 행을 만들어 준다.

    마이그레이션 0013 이 첫 행을 넣지만, 마이그레이션 없이 create_all 로 뜬 테스트
    DB (backend/tests/conftest.py) 에서는 이 함수가 처음 불릴 때 만든다.
    """
    row = db.execute(select(CompanyProfile).where(CompanyProfile.id == 1)).scalar_one_or_none()
    if row is None:
        row = CompanyProfile(id=1, name="")
        db.add(row)
        db.flush()
    return row


def name_for(db: Session | None) -> str:
    """{회사명} 치환·프롬프트 헤더에 쓸 회사 이름.

    프로파일에 값이 있으면 그것, 없으면 환경변수. 이 함수를 거치지 않고 프로파일
    을 바로 읽으면 빈 문자열이 그대로 메일에 나가 "회사에 지원해 주셔서" 같은
    이상한 문장이 만들어진다.
    """
    if db is None:
        # 메일 워커의 단발 렌더 경로 등, DB 세션이 아직 없을 때. 이 시점엔 프로파일
        # 조회가 불가능하므로 환경변수 폴백만 쓴다.
        return _ENV_FALLBACK_NAME
    profile = get_profile(db)
    return profile.name.strip() or _ENV_FALLBACK_NAME


def prompt_context(db: Session) -> str:
    """아르 시스템 프롬프트 뒤에 붙일 회사 절.

    비어 있는 항목은 통째로 뺀다. 아르에게 "정보 없음" 을 보여 주면 그 자리에서
    지어내려 든다 — 아예 절이 없으면 지어낼 근거도 없다.
    """
    p = get_profile(db)
    lines: list[str] = ["", "---", "", "## 회사 정보"]

    name = p.name.strip() or _ENV_FALLBACK_NAME
    lines.append(f"- 회사명: {name}")
    if p.tagline:
        lines.append(f"- 한 줄 소개: {p.tagline}")
    if p.website:
        lines.append(f"- 웹사이트: {p.website}")
    if p.hr_email:
        lines.append(f"- 채용 문의: {p.hr_email}")
    if p.description:
        lines.append("")
        lines.append(p.description.strip())
    if p.narrative:
        lines.append("")
        lines.append("### 회사 배경 (자세히)")
        lines.append("")
        lines.append(p.narrative.strip())

    # 마지막에 규약 한 줄 — 아르에게 "여기 없는 사실은 지어내지 말라" 를 상기.
    lines.append("")
    lines.append(
        "**규약.** 회사 관련 질문에는 위 절을 근거로만 답한다. "
        "여기 없는 사실은 지어내지 않고 '회사 담당자에게 확인 필요' 로 안내한다."
    )
    return "\n".join(lines)
