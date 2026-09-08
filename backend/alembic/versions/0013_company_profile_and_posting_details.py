"""company_profile + job_postings 상세 컬럼

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-08

**왜 두 개를 한 마이그레이션으로.** 회사 소개 문서(`docs/06_company/00-회사-소개.md`)
와 공고 상세는 같은 조각이다 — 회사 문서는 회사 전체 이야기, 공고 상세는 그 안의
포지션별 이야기. 아르 프롬프트·메일 변수 치환·시연에서 둘이 같이 인용된다.

**단일 회사 전제.** 멀티테넌시는 이 프로젝트 범위 밖(ADR 없음)이다. `company_profile`
은 항상 한 행이다 — `id = 1` 을 CHECK 로 못 박고, 서비스는 이 한 행을 upsert 한다.

**빈 값 정책.** 이 마이그레이션의 컬럼은 전부 nullable 이다. 기존 공고를 깨지 않기
위해서, 그리고 다른 회사가 이 코드를 갈아 끼울 때 자기 회사에 없는 항목(예: 재택
정책 미정)을 빈 채로 둘 수 있게 하려는 것이 목적이다. 애플리케이션 코드가 빈 값을
"미공개" 로 안내한다.

**메일 변수 이전.** `mail.COMPANY_NAME` 환경변수는 이 표가 채워지면 뒤로 물러난다 —
`company_profile.name` 이 있으면 그것을, 없으면 환경변수를 쓴다.
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_profile",
        sa.Column("id", sa.BigInteger, primary_key=True),
        # 회사명 — {회사명} 변수 치환에 쓰인다. 빈 문자열은 허용하지만 NULL 은 막는다
        # (NULL 이면 "회사명이 정해지지 않았다" 상태를 코드가 매번 분기해야 한다).
        sa.Column("name", sa.String(100), nullable=False, server_default=""),
        sa.Column("tagline", sa.String(200), nullable=True),
        # 채용 문의 회신 주소. 메일 Reply-To 로 쓰인다 — 없으면 발신 주소로 폴백.
        sa.Column("hr_email", sa.String(255), nullable=True),
        sa.Column("website", sa.String(255), nullable=True),
        # 회사 한 단락 소개 — 아르 시스템 프롬프트 헤더에 그대로 들어간다.
        sa.Column("description", sa.Text, nullable=True),
        # 회사 전체 이야기 (문화·복지·채용 원칙·FAQ). 아르 프롬프트 뒤에 그대로 붙는다.
        # 여기가 채워질수록 아르가 회사에 대해 더 정확히 답한다. 비면 그 절만 생략된다.
        sa.Column("narrative", sa.Text, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # 단일 행 강제. 두 번째 INSERT 가 오면 UNIQUE 로 튀는 게 아니라 CHECK 로 튀도록
        # 만들어 오류 메시지가 "id 는 1 이어야 한다" 로 명확해진다.
        sa.CheckConstraint("id = 1", name="ck_company_profile_singleton"),
    )
    # 초기 한 행. 값은 전부 빈 상태 — 관리자가 채운다.
    op.execute(
        "INSERT INTO company_profile (id, name, updated_at) "
        "VALUES (1, '', now())"
    )

    # job_postings 상세 컬럼. 전부 nullable — 기존 7건이 그대로 유효하게.
    with op.batch_alter_table("job_postings") as b:
        # 근무지 — "서울 판교" 처럼 자유 형식. 여러 곳이면 콤마 구분.
        b.add_column(sa.Column("location", sa.String(200), nullable=True))
        # 근무 형태 — 정규직 · 계약직 · 인턴 · 프리랜서. CHECK 로 좁히지 않는다:
        # 새 형태(예: 파트타임)가 필요할 때 마이그레이션 없이 늘리려는 것.
        b.add_column(sa.Column("employment_type", sa.String(30), nullable=True))
        # 경력 요건 — 최소·최대 년수. 신입은 min=0. 무관은 둘 다 NULL.
        b.add_column(sa.Column("experience_min", sa.SmallInteger, nullable=True))
        b.add_column(sa.Column("experience_max", sa.SmallInteger, nullable=True))
        # 급여 — 만원 단위 정수. 협의는 둘 다 NULL. 상한 없음은 max=NULL, min 만.
        b.add_column(sa.Column("salary_min", sa.Integer, nullable=True))
        b.add_column(sa.Column("salary_max", sa.Integer, nullable=True))
        # 재택 정책 — 자유 형식으로 두어 회사마다 표현이 다르게 (주 2일 재택 등).
        b.add_column(sa.Column("remote_policy", sa.String(100), nullable=True))
        # 필수·우대·복지 — 마크다운 텍스트. 지원 폼과 아르 답변에 그대로 인용된다.
        b.add_column(sa.Column("requirements", sa.Text, nullable=True))
        b.add_column(sa.Column("preferred", sa.Text, nullable=True))
        b.add_column(sa.Column("benefits", sa.Text, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("job_postings") as b:
        for col in (
            "location", "employment_type", "experience_min", "experience_max",
            "salary_min", "salary_max", "remote_policy",
            "requirements", "preferred", "benefits",
        ):
            b.drop_column(col)
    op.drop_table("company_profile")
