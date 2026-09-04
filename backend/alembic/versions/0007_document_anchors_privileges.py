"""무결성 원장 권한 분리 — 앱은 넣기만, 고치고 지우는 것은 관리자만 (ADR-0028)

0006 의 트리거는 "앱이 실수로/마음대로 고치는 것"을 막지만, **앱이 슈퍼유저로
붙어 있으면 앱 스스로 트리거를 끌 수 있다.** 지금 구조가 그렇다 — 로컬·운영
모두 `postgres` 로 접속한다(docker-compose.yml · infra/docker-compose.prod.yml).
잠금 위에 잠금을 얹어도 열쇠를 같은 사람이 들고 있으면 소용이 없다.

그래서 **앱이 쓰는 롤에서 UPDATE·DELETE·TRUNCATE 권한 자체를 회수한다.**
권한이 없으면 트리거를 끄는 것도 못 한다(트리거 조작은 테이블 소유자·슈퍼유저
권한이다). 관리자 롤(테이블 소유자)은 그대로 전부 할 수 있다.

**이 리비전만으로는 아직 갈라지지 않는다.** 앱이 소유자와 같은 롤로 붙어 있는
한 회수할 대상이 없기 때문이다. 실제 분리는 두 단계다:

1. 서버에서 앱 전용 롤을 만들고 `DATABASE_URL` 을 그 롤로 바꾼다 (사람이 한다 —
   비밀번호가 필요하다). 절차는 ADR-0028 "권한 분리 절차" 절
2. `ARDA_APP_DB_ROLE` 환경변수에 그 롤 이름을 넣고 이 리비전을 돌린다

**환경변수가 없으면 아무것도 하지 않는다.** 운영에서 이 리비전이 먼저 돌아도
서비스가 죽지 않게 하기 위해서다 — 권한을 잘못 회수하면 접수가 통째로 멈춘다.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-04
"""

from __future__ import annotations

import os
import re

from alembic import op


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None

_TABLE = "document_anchors"
_SEQUENCE = "document_anchors_id_seq"

# 롤 이름은 파라미터 바인딩이 안 되는 자리(식별자)라 문자열로 끼워 넣어야 한다.
# 그래서 모양을 먼저 검사한다 — 통과하지 못하면 아무것도 하지 않는다.
_ROLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]{0,62}$")


def _app_role() -> str | None:
    role = (os.getenv("ARDA_APP_DB_ROLE") or "").strip()
    if not role:
        return None
    if not _ROLE_NAME.match(role):
        raise ValueError(
            f"ARDA_APP_DB_ROLE 이 롤 이름 모양이 아닙니다: {role!r}. "
            "영문자·밑줄로 시작하고 영숫자·밑줄·$ 만 씁니다."
        )
    return role


def upgrade() -> None:
    # PUBLIC 은 "모든 롤"이다. 여기 붙은 권한은 나중에 만드는 롤에도 자동으로
    # 따라붙으므로 먼저 떼어 낸다. 보통 비어 있지만 확인 없이 믿지 않는다.
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE {_TABLE} FROM PUBLIC")

    role = _app_role()
    if role is None:
        return

    # 없는 롤에 GRANT 하면 에러다. 이행이 그것 때문에 멈추면 안 되므로 먼저 본다.
    exists = op.get_bind().exec_driver_sql(
        "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
    ).scalar()
    if not exists:
        raise RuntimeError(
            f"ARDA_APP_DB_ROLE 로 지정한 롤 '{role}' 이 DB 에 없습니다. "
            "먼저 롤을 만들고 DATABASE_URL 을 바꾼 뒤 다시 돌리세요 (ADR-0028)."
        )

    # 앱이 할 수 있는 것: 읽기 + 새 고리 추가. 그게 전부다.
    op.execute(f'REVOKE ALL ON TABLE {_TABLE} FROM "{role}"')
    op.execute(f'GRANT SELECT, INSERT ON TABLE {_TABLE} TO "{role}"')
    # INSERT 하려면 id 시퀀스를 쓸 수 있어야 한다. 이걸 빼먹으면 접수가 멈춘다.
    op.execute(f'GRANT USAGE, SELECT ON SEQUENCE {_SEQUENCE} TO "{role}"')

    # 2단계(공개 타임스탬프)가 ots_* 두 칸을 채워야 한다. 컬럼 단위 UPDATE 로만
    # 연다 — 테이블 전체 UPDATE 를 주면 0006 트리거가 유일한 방어선이 되고,
    # 그건 앱이 끌 수 있는 방어선이 아니어야 한다는 이 리비전의 취지와 어긋난다.
    op.execute(f'GRANT UPDATE (ots_status, ots_proof) ON TABLE {_TABLE} TO "{role}"')


def downgrade() -> None:
    role = _app_role()
    if role is not None:
        # 되돌리기는 "앱이 다시 다 할 수 있게" 다. 소유자 권한은 건드린 적이 없다.
        op.execute(f'GRANT ALL ON TABLE {_TABLE} TO "{role}"')
        op.execute(f'GRANT ALL ON SEQUENCE {_SEQUENCE} TO "{role}"')
