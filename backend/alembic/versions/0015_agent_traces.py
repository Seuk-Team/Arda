"""agent_traces — 아르 대화 로그 (Qwen 학습 데이터 수집·평가)

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-08 (2026-09-09 리넘버 — 0014 는 main 의 company_profile 시드가 선점)

**왜 이 표가 필요한가.** ADR-0024 개정으로 팀이 확정한 3모델(ViT · Whisper turbo ·
Qwen3-8B) 중 소연이 오늘 ViT 를 학습해 69.84% (커밋 31f0051). Qwen 은 우리가 직접
학습한다(팀장 결정, 09-08 저녁). 그러려면 **정답 라벨이 붙은 대화 쌍** 이 필요하고,
그 뿌리가 이 표다.

**표 하나가 두 역할을 한다.**
- **관측**: 매 대화의 요청·도구 호출·답변·비용을 남긴다. 어떤 라우터·백엔드가
  탔는지·얼마나 걸렸는지를 나중에 회고할 수 있다.
- **학습 데이터**: 담당자가 나중에 "이건 잘 답한 케이스" 를 라벨하면 그 쌍이 QLoRA
  학습셋으로 넘어간다. 잘못된 답변엔 `label_correction` 에 사람이 쓴 정답을 남긴다.

**라벨은 사후·낙관적이다.** 아르가 답변을 낼 때는 라벨 필드가 전부 NULL 이다.
담당자·관리자가 나중에 별도 화면(추후 PR)에서 훑으며 라벨을 붙인다. 라벨이 없는
행은 관측용으로만 쓰이고 학습셋엔 안 들어간다.

**개인정보.** 지원자 이메일·이력서 내용이 요청·답변에 섞여 들어올 수 있다. 이 표
는 서버 내부 학습 파이프라인의 원본이다 — 외부 노출은 금지(향후 조회 API 는 admin
전용, 지원자 본인 조회 없음).
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_traces",
        sa.Column("id", sa.BigInteger, primary_key=True),
        # 요청 상관 관계 — logs 의 request_id 와 조인해 서버 로그와 붙일 수 있다.
        sa.Column("request_id", sa.String(64), nullable=True, index=True),
        # 대화 스레드. 담당자가 새 창을 열면 새 값이 된다. 다중 턴 학습에 필요.
        sa.Column("session_id", sa.String(64), nullable=True, index=True),
        sa.Column("turn_index", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column(
            "user_id",
            sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_message", sa.Text, nullable=False),
        sa.Column("assistant_reply", sa.Text, nullable=False, server_default=""),
        # 이전 턴들. AgentHistoryMessage 구조 (role · content) 배열.
        sa.Column(
            "history", sa.JSON, nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        # 실행된 도구 목록. {name, input, output(가능하면 JSON)} 배열.
        sa.Column(
            "tool_calls", sa.JSON, nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
        sa.Column("pending_action", sa.JSON, nullable=True),
        # 라우터·백엔드 구분. router:v1 · anthropic:claude-* · ollama:qwen3:8b 등.
        sa.Column("backend", sa.String(50), nullable=False, server_default=""),
        sa.Column("model_tag", sa.String(200), nullable=False, server_default=""),
        sa.Column("input_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # ── 라벨 (사후 · nullable) ──
        # good / bad / needs_fix / null(미라벨)
        sa.Column("label_verdict", sa.String(20), nullable=True),
        # "이렇게 답했어야 한다" — 사람이 쓴 정답. bad · needs_fix 일 때 채운다.
        sa.Column("label_correction", sa.Text, nullable=True),
        sa.Column(
            "label_by", sa.BigInteger,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("label_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "label_verdict IS NULL OR label_verdict IN ('good','bad','needs_fix')",
            name="ck_agent_traces_label_verdict",
        ),
    )
    # 라벨된 행만 훑을 인덱스 (학습셋 export 시 자주 스캔한다).
    op.create_index(
        "ix_agent_traces_verdict_created",
        "agent_traces",
        ["label_verdict", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_traces_verdict_created", table_name="agent_traces")
    op.drop_table("agent_traces")
