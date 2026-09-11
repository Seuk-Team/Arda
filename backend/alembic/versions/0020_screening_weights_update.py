"""screening 가중치 개정 — 요건 강조·우대 축소·문화 하한 규칙 도입 (2026-09-11)

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-11

fit-check 24명 실측 (2026-09-11):
- 남기훈: 요건 75(우수)·문화 35 → 총점 58 → 자동 불합격.
  자소서의 "회의 기반 의사결정" 한 문구가 인재상과 불일치 신호로 잡혀 문화 35 가 됐고,
  30% 가중치가 그대로 총점을 끌어내렸다.
- 강현우: 요건 65·우대 50·문화 55 → 총점 59 → 자동 불합격 (1점 차이).
- 임재원: 요건 65(충족)·우대 25·문화 55 → 총점 54 → 자동 불합격.
  필수 요건은 만족했는데 우대 부족 하나로 떨어졌다.

새 가중치·규칙:
1. doc_requirements 50 → 60  (필수 강조)
2. doc_preferred    20 → 10  (있으면 좋음 · 결정타 아니어야)
3. doc_culture      30 그대로 · 다만 요건 ≥ 70 이면 문화 점수 하한 50 (코드에서 처리)

시뮬:
- 남기훈: 요건 하한 규칙으로 문화 35→50 · 총점 65 → pass
- 강현우: 우대 축소로 총점 61 → pass
- 백서준: 문화 72 우수 · 총점 60 → pass (Flask 2년 · 요건 3년 미달이나 · 문화·요건 62 로 상쇄)
- 정민호: 요건 45 (실무 0년) 요건 강조로 총점 57 → reject (오히려 옳음)
- 나머지 · 자동 합격 그대로 · 자동 불합격 그대로

**hold 상태는 도입하지 않는다** — 팀장 결정 (2026-09-11).
"""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 기존 company_profile.scoring_weights JSON 에서 두 키만 갱신.
    # 다른 키(itv_answers 등) 는 그대로 둔다.
    op.execute(
        """
        UPDATE company_profile
        SET scoring_weights = jsonb_set(
            jsonb_set(
                COALESCE(scoring_weights::jsonb, '{}'::jsonb),
                '{doc_requirements}', '60'::jsonb, true
            ),
            '{doc_preferred}', '10'::jsonb, true
        )::json
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE company_profile
        SET scoring_weights = jsonb_set(
            jsonb_set(
                COALESCE(scoring_weights::jsonb, '{}'::jsonb),
                '{doc_requirements}', '50'::jsonb, true
            ),
            '{doc_preferred}', '20'::jsonb, true
        )::json
        """
    )
