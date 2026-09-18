"""이행(alembic)으로만 만든 DB 가 모델과 같은 모양인지 본다 (2026-09-17).

**왜 필요한가 — 쉬운 말로**: 이행 파일은 운영 DB 가 따르는 "공사 지시서"이고, 모델
(`app/models/`)은 "완성 설계도"다. CI 는 빈 DB 에 지시서를 적용한 뒤 테스트를 도는데,
테스트가 시작하면서 `conftest` 의 `create_all` 이 **설계도를 보고 빠진 표를 채워 넣는다.**
그래서 지시서를 빠뜨려도 CI 는 초록이고, 운영 DB 에만 표·값이 없다.

실제로 두 번 그랬다.
- 09-16 `email_logs.stage` 에 `password_setup` 을 모델에만 넣음 → 운영에서 메일 행 INSERT 거부
- 09-17 이행 번호 `0023` 중복(#282) → 운영 DB 에 `file_blobs` 가 안 생길 뻔함

그래서 **`alembic upgrade head` 직후, 테스트 전에** 이 스크립트를 돌린다. 달라진 곳이
있으면 종료 코드 1.

보는 것
1. 모델의 표가 DB 에 다 있는가
2. 모델의 컬럼이 DB 에 다 있는가 · NULL 허용이 같은가
3. 이름 붙은 CHECK 제약이 DB 에 있는가 · **허용 값 목록**(따옴표 안 문자열)이 같은가
4. 이름 붙은 UNIQUE 제약이 DB 에 있는가
5. 모델의 인덱스가 **같은 이름으로** DB 에 있는가 (2026-09-17 추가). 이름만 본다 —
   칼럼·조건식까지 비교하면 표현 차이로 시끄럽다. 추가한 날 어긋난 곳은
   `integration_clients` 하나였다(모델은 자동 이름, 0021 은 다른 이름 + 부분 인덱스)

보지 않는 것 — 타입의 세부(varchar 길이 등), 기본값. SQLAlchemy 표현과 Postgres
표현이 달라 비교가 시끄럽고, 지금까지의 사고는 전부 위 다섯 가지에서 났다.

DB 에만 있고 모델에 없는 것(옛 컬럼·인덱스 등)은 **경고만** 한다 — 지우는 이행은 일부러 늦게 한다.

사용 (backend/ 에서):
    uv run alembic upgrade head
    uv run python scripts/check_schema_drift.py

읽기만 한다. DB 에 아무것도 쓰지 않는다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import CheckConstraint, UniqueConstraint, inspect  # noqa: E402

import app.models  # noqa: E402,F401  — 모든 모델을 메타데이터에 올린다
from app.db import Base, engine, pgvector_ready  # noqa: E402

# 이행이 조건부로만 만드는 표. pgvector 확장이 없는 DB 에서는 없는 게 정상이다(0001).
_OPTIONAL_WITHOUT_VECTOR = {"application_embeddings"}
_IGNORED_DB_TABLES = {"alembic_version"}
_LITERAL = re.compile(r"'((?:[^']|'')*)'")


def _literals(sql: str | None) -> set[str]:
    """CHECK 식에서 따옴표 안 문자열만 뽑는다.

    모델의 `stage IN ('a', 'b')` 와 Postgres 가 돌려주는
    `((stage)::text = ANY ((ARRAY['a'::character varying, ...])))` 는 모양이 전혀 다르지만,
    **허용 값 목록**은 같아야 한다. 사고가 난 것도 목록이었다.
    """
    return set(_LITERAL.findall(sql or ""))


def check() -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    insp = inspect(engine)
    db_tables = set(insp.get_table_names()) - _IGNORED_DB_TABLES
    has_vector = pgvector_ready()

    for table in Base.metadata.sorted_tables:
        name = table.name
        if name not in db_tables:
            if name in _OPTIONAL_WITHOUT_VECTOR and not has_vector:
                continue
            problems.append(f"[표 없음] {name} — 모델에는 있는데 이행으로 안 만들어졌다")
            continue

        # 2. 컬럼
        db_cols = {c["name"]: c for c in insp.get_columns(name)}
        for col in table.columns:
            got = db_cols.get(col.name)
            if got is None:
                problems.append(f"[컬럼 없음] {name}.{col.name}")
                continue
            if bool(got["nullable"]) != bool(col.nullable) and not col.primary_key:
                want = "NULL 허용" if col.nullable else "NOT NULL"
                problems.append(f"[NULL 규칙 다름] {name}.{col.name} — 모델은 {want}")
        for extra in sorted(set(db_cols) - {c.name for c in table.columns}):
            warnings.append(f"[DB 에만 있는 컬럼] {name}.{extra}")

        # 3. CHECK
        db_checks = {c["name"]: c.get("sqltext") for c in insp.get_check_constraints(name)}
        for cons in table.constraints:
            if not isinstance(cons, CheckConstraint) or not cons.name:
                continue
            cname = str(cons.name)
            if cname not in db_checks:
                problems.append(f"[CHECK 없음] {name}.{cname}")
                continue
            want = _literals(str(cons.sqltext))
            got = _literals(db_checks[cname])
            if want != got:
                missing = sorted(want - got)
                extra = sorted(got - want)
                detail = []
                if missing:
                    detail.append(f"이행에 빠진 값 {missing}")
                if extra:
                    detail.append(f"DB 에만 있는 값 {extra}")
                problems.append(f"[CHECK 값 다름] {name}.{cname} — " + " · ".join(detail))

        # 4. UNIQUE
        db_uniques = {u["name"] for u in insp.get_unique_constraints(name)}
        db_unique_idx = {i["name"] for i in insp.get_indexes(name) if i.get("unique")}
        for cons in table.constraints:
            if isinstance(cons, UniqueConstraint) and cons.name:
                if str(cons.name) not in db_uniques | db_unique_idx:
                    problems.append(f"[UNIQUE 없음] {name}.{cons.name}")

        # 5. 인덱스 — 이름만. UNIQUE 제약이 만든 인덱스는 4 에서 봤으니 뺀다
        db_indexes = {
            i["name"] for i in insp.get_indexes(name) if not i.get("duplicates_constraint")
        }
        model_indexes = {str(i.name) for i in table.indexes}
        for missing in sorted(model_indexes - db_indexes):
            problems.append(f"[인덱스 없음] {name}.{missing}")
        for extra in sorted(db_indexes - model_indexes):
            warnings.append(f"[DB 에만 있는 인덱스] {extra} ({name})")

    model_tables = {t.name for t in Base.metadata.sorted_tables}
    for extra in sorted(db_tables - model_tables):
        warnings.append(f"[DB 에만 있는 표] {extra}")
    return problems, warnings


def main() -> int:
    problems, warnings = check()
    for w in warnings:
        print("경고 ", w)
    if problems:
        print(f"\n모델과 이행 결과가 다르다 — {len(problems)}건")
        for p in problems:
            print("  ✗", p)
        print(
            "\n고치는 법: 모델을 바꿨으면 같은 커밋에 alembic 이행 파일을 만든다"
            " (backend/alembic/README.md). 번호는 versions/ 의 마지막 번호 + 1."
        )
        return 1
    print(f"모델과 이행 결과가 같다 — 표 {len(Base.metadata.sorted_tables)}개 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
