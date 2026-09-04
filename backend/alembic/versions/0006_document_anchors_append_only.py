"""무결성 원장을 DB 단에서 추가 전용으로 잠근다 (ADR-0028 2단계 준비)

지금까지 "고쳐 쓰지 않는다"는 **코드의 약속**일 뿐이었다. 약속은 앱을 거치지
않는 손(psql·관리도구·다른 서비스)에는 아무 구속력이 없다. DB 가 직접 거부하게
만든다.

**허용**: INSERT · `ots_status`/`ots_proof` 만 바꾸는 UPDATE (2단계 타임스탬프가
쓸 자리다. 이걸 막으면 2단계에서 이 트리거를 걷어내야 하고, 그러면 잠금이
잠금이 아니게 된다)
**거부**: DELETE · TRUNCATE · 그 외 모든 컬럼의 UPDATE

**한계를 분명히 한다** — 트리거를 끌 수 있는 권한자(superuser·테이블 소유자)는
이것도 우회한다. 이 리비전은 봉인이 아니라 **문턱**이다. 진짜 봉인은 우리가 못
고치는 곳(공개 타임스탬프)에 못 박을 때 생긴다. ADR-0028 "남은 것" 절.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-04
"""

from __future__ import annotations

from alembic import op


revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None


# 행 단위 — UPDATE·DELETE 를 본다.
# ots_* 두 칸을 뺀 나머지가 하나라도 달라지면 거부한다. 컬럼을 나열하는 대신
# ROW(...) IS DISTINCT FROM ROW(...) 로 비교해 NULL 도 제대로 걸린다
# (`NEW.x <> OLD.x` 는 한쪽이 NULL 이면 NULL 이 되어 통과해 버린다).
_ROW_FN = """
CREATE OR REPLACE FUNCTION document_anchors_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION
            '무결성 원장은 삭제할 수 없습니다 (document_anchors seq=%)', OLD.seq
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF ROW(NEW.id, NEW.seq, NEW.application_id, NEW.doc_type, NEW.file_id,
           NEW.content_sha256, NEW.prev_chain_hash, NEW.chain_hash, NEW.anchored_at)
       IS DISTINCT FROM
       ROW(OLD.id, OLD.seq, OLD.application_id, OLD.doc_type, OLD.file_id,
           OLD.content_sha256, OLD.prev_chain_hash, OLD.chain_hash, OLD.anchored_at)
    THEN
        RAISE EXCEPTION
            '무결성 원장은 고쳐 쓸 수 없습니다 (document_anchors seq=%). 바꿀 수 있는 것은 ots_status·ots_proof 뿐입니다', OLD.seq
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# 문장 단위 — TRUNCATE 는 행 트리거를 타지 않는다. 따로 막지 않으면
# 위의 것을 전부 통과해 원장이 한 번에 비워진다.
_TRUNCATE_FN = """
CREATE OR REPLACE FUNCTION document_anchors_no_truncate() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '무결성 원장은 비울 수 없습니다 (document_anchors TRUNCATE)'
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_ROW_FN)
    op.execute(_TRUNCATE_FN)
    op.execute(
        """
        CREATE TRIGGER trg_document_anchors_append_only
        BEFORE UPDATE OR DELETE ON document_anchors
        FOR EACH ROW EXECUTE FUNCTION document_anchors_append_only();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_document_anchors_no_truncate
        BEFORE TRUNCATE ON document_anchors
        FOR EACH STATEMENT EXECUTE FUNCTION document_anchors_no_truncate();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_document_anchors_no_truncate ON document_anchors")
    op.execute("DROP TRIGGER IF EXISTS trg_document_anchors_append_only ON document_anchors")
    op.execute("DROP FUNCTION IF EXISTS document_anchors_no_truncate()")
    op.execute("DROP FUNCTION IF EXISTS document_anchors_append_only()")
