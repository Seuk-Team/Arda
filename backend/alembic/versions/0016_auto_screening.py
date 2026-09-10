"""자동 심사 (ADR-0034) — 서류 점수·판정, 공고 임계·면접관 풀, 면접 AI 점수, 가중치

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-10

팀장 결정(2026-09-10): 서류·면접은 아르가 점수를 매기고 단계를 옮긴다. 최종 합불만
사람. 이 리비전은 그 판정을 **기록할 자리**를 만든다. 자동 이동 자체는 서비스
레이어(app/screening.py)가 한다 — 트리거로 넣지 않는 이유는 stages.py 머리말과 같다.

- job_postings.pass_threshold(기본 60) · screening_mode('auto'|'manual')
- posting_interviewers: 공고별 기본 면접관 풀 (자동 배정 재료)
- applications.doc_score(0~100) · doc_score_detail(JSON) · doc_decision · doc_decided_at
  · decision_source('agent'|'human') — 사람이 옮기면 human 이 되고 자동에서 빠진다
- interview_sessions.ai_score · ai_score_detail · truth_samples(JSON 집계) · scored_at
- company_profile.scoring_weights(JSON) · talent_profile(인재상 원문)

전부 nullable 또는 기본값이 있어 기존 행에 영향이 없다.
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

DEFAULT_WEIGHTS = (
    '{"doc": 50, "interview": 50, "doc_requirements": 50, "doc_preferred": 20, '
    '"doc_culture": 30, "itv_answers": 70, "itv_truth": 30}'
)

# docs/06_company/00-회사-소개.md §8.1·§8.2 — 서류·면접 인재상 채점의 재료.
DEFAULT_TALENT_PROFILE = (
    "[함께 일하고 싶은 사람]\n"
    "- 문서로 생각을 정리해 본 사람\n"
    "- 결정을 스스로 내려 본 사람 (승인 기다리는 것이 편하지 않은 사람)\n"
    "- 자기 도메인 밖의 코드도 필요하면 고쳐 본 사람\n"
    "- 실패를 공개할 수 있는 사람\n"
    "- 짧은 문장으로 쓰려고 노력한 흔적이 있는 사람\n"
    "[잘 안 맞는 사람]\n"
    "- 세세한 지시가 있어야 편한 사람\n"
    "- 회의로 결정하는 것을 선호하는 사람\n"
    "- 완벽할 때까지 릴리스하지 않는 사람\n"
    "- 자기 도메인만 지키는 것이 편한 사람"
)


def upgrade() -> None:
    op.add_column(
        "job_postings",
        sa.Column("pass_threshold", sa.SmallInteger, nullable=False, server_default="60"),
    )
    op.add_column(
        "job_postings",
        sa.Column("screening_mode", sa.String(20), nullable=False, server_default="auto"),
    )
    op.create_check_constraint(
        "ck_job_postings_screening_mode", "job_postings",
        "screening_mode IN ('auto', 'manual')",
    )
    op.create_check_constraint(
        "ck_job_postings_pass_threshold", "job_postings",
        "pass_threshold BETWEEN 0 AND 100",
    )

    # 로컬 개발 DB 는 pytest 의 create_all 이 먼저 돌아 이 표를 이미 만들었을 수 있다
    # (create_all 은 없는 표는 만들고 없는 컬럼은 못 만든다). 그때는 건너뛴다 —
    # 운영·CI 는 이행이 먼저라 항상 만든다. 0013 이 같은 이유로 같은 처리를 했다.
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("posting_interviewers"):
        _create_posting_interviewers()


def _create_posting_interviewers() -> None:
    op.create_table(
        "posting_interviewers",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "job_posting_id", sa.BigInteger,
            sa.ForeignKey("job_postings.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("job_posting_id", "user_id", name="uq_posting_interviewers"),
    )

    op.add_column("applications", sa.Column("doc_score", sa.SmallInteger, nullable=True))
    op.add_column("applications", sa.Column("doc_score_detail", sa.JSON, nullable=True))
    op.add_column("applications", sa.Column("doc_decision", sa.String(20), nullable=True))
    op.add_column(
        "applications", sa.Column("doc_decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("applications", sa.Column("decision_source", sa.String(10), nullable=True))
    op.create_check_constraint(
        "ck_applications_doc_decision", "applications",
        "doc_decision IS NULL OR doc_decision IN ('pass', 'reject', 'hold')",
    )
    op.create_check_constraint(
        "ck_applications_decision_source", "applications",
        "decision_source IS NULL OR decision_source IN ('agent', 'human')",
    )

    op.add_column("interview_sessions", sa.Column("ai_score", sa.SmallInteger, nullable=True))
    op.add_column("interview_sessions", sa.Column("ai_score_detail", sa.JSON, nullable=True))
    op.add_column("interview_sessions", sa.Column("truth_samples", sa.JSON, nullable=True))
    op.add_column(
        "interview_sessions", sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column(
        "company_profile",
        sa.Column(
            "scoring_weights", sa.JSON, nullable=False,
            server_default=sa.text(f"'{DEFAULT_WEIGHTS}'::json"),
        ),
    )
    op.add_column("company_profile", sa.Column("talent_profile", sa.Text, nullable=True))
    # 코드브릿지 시드(0014)가 있는 행에만 인재상 기본값을 넣는다 — 비어 있을 때만.
    op.execute(
        sa.text(
            "UPDATE company_profile SET talent_profile = :t "
            "WHERE id = 1 AND (talent_profile IS NULL OR talent_profile = '')"
        ).bindparams(t=DEFAULT_TALENT_PROFILE)
    )


def downgrade() -> None:
    op.drop_column("company_profile", "talent_profile")
    op.drop_column("company_profile", "scoring_weights")
    for col in ("scored_at", "truth_samples", "ai_score_detail", "ai_score"):
        op.drop_column("interview_sessions", col)
    op.drop_constraint("ck_applications_decision_source", "applications", type_="check")
    op.drop_constraint("ck_applications_doc_decision", "applications", type_="check")
    for col in ("decision_source", "doc_decided_at", "doc_decision", "doc_score_detail", "doc_score"):
        op.drop_column("applications", col)
    op.drop_table("posting_interviewers")
    op.drop_constraint("ck_job_postings_pass_threshold", "job_postings", type_="check")
    op.drop_constraint("ck_job_postings_screening_mode", "job_postings", type_="check")
    op.drop_column("job_postings", "screening_mode")
    op.drop_column("job_postings", "pass_threshold")
