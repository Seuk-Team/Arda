"""제출물 무결성 앵커 — 이력서·자소서의 지문을 사슬로 묶는다 (ADR-0028).

**한 문장 정의**: 제출 순간 문서의 지문(SHA-256)을 떠서, 앞 지문을 재료로 쓰는
사슬에 한 줄씩 쌓아 둔다. 나중에 원본이 바뀌면 지문이 안 맞으므로 드러난다.

공책에 비유하면 이렇다 — 각 장 맨 위에 **앞장의 지문을 베껴 적는다.** 누가
가운데 한 장을 찢고 다시 써 넣으면, 그 뒤 모든 장의 지문이 어긋난다. 한 줄만
조용히 고치는 것이 불가능해지는 것이 사슬의 전부다.

**이것이 막아 주는 것과 아닌 것**을 분명히 해 둔다:
- 막는다: 원본 파일·자기소개가 제출 뒤에 바뀐 것을 **탐지**한다.
- 못 막는다: 바뀌는 것 자체. 그리고 DB 를 통째로 다시 쓸 수 있는 내부자.
  사슬 전체를 다시 계산하면 앞뒤가 맞는 위조본이 되기 때문이다.
  그 구멍을 메우는 것이 2단계(공개 타임스탬프)다 — ADR-0028 "남은 것" 절.

파일 본문은 평소 이 서버를 지나가지 않는다(`app/s3.py`). 지문을 뜰 때만
S3 에서 한 번 읽는다. 그래서 제출 응답을 붙잡지 않도록 **백그라운드로 돈다**.
"""

import hashlib
import logging
from datetime import datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import s3
from app.models import Application, DocumentAnchor, File

logger = logging.getLogger(__name__)

# 사슬에 append 할 때 잡는 Postgres 어드바이저리 락의 키.
# 사슬은 "앞 행을 읽고 → 그 해시를 재료로 새 행을 쓴다"라서, 둘이 동시에 들어오면
# 같은 앞 행을 읽고 같은 자리(seq)를 노린다. 트랜잭션 단위 락으로 줄을 세운다.
# 임의의 상수이며 다른 곳에서 같은 키를 쓰지 않는다.
_CHAIN_LOCK_KEY = 0x4152444101  # "ARDA" + 01

# 지문 재료를 이어 붙일 때 쓰는 구분자. 필드 안에 나올 수 없는 문자여야
# "ab|c" 와 "a|bc" 가 같은 지문이 되는 일(구분자 혼동)이 없다.
_SEP = "\x1f"  # ASCII Unit Separator


def sha256_bytes(data: bytes) -> str:
    """바이트의 지문. 소문자 16진수 64자."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(value: str) -> str:
    """텍스트의 지문. **UTF-8 로 굳혀서** 뜬다.

    인코딩을 고정하지 않으면 같은 글자가 환경에 따라 다른 지문이 되어, 위조가
    아닌데 위조로 잡힌다.
    """
    return sha256_bytes(value.encode("utf-8"))


def compute_chain_hash(
    *,
    prev_chain_hash: str | None,
    seq: int,
    application_id: int,
    doc_type: str,
    file_id: int | None,
    content_sha256: str,
    anchored_at: datetime,
) -> str:
    """사슬 고리 하나의 지문.

    **앞 고리의 지문이 재료에 들어간다** — 이것이 사슬을 사슬로 만든다.
    첫 행은 앞이 없으므로 빈 문자열을 쓴다.

    재료에 `anchored_at` 까지 넣는 이유: 같은 파일을 같은 지원서에 다시 앵커해도
    시각이 다르면 다른 고리가 된다. 시각을 빼면 재현 가능한 값이 되어, 지운 뒤
    같은 자리에 다시 만들어 넣는 것이 쉬워진다.

    검증할 때 이 함수를 **저장된 값 그대로 다시 불러** 같은 결과가 나오는지 본다.
    그래서 재료 구성·순서·구분자를 바꾸면 과거 행이 전부 깨진다. 바꿀 일이 생기면
    새 버전 컬럼을 두고 갈라야 한다.
    """
    material = _SEP.join(
        [
            prev_chain_hash or "",
            str(seq),
            str(application_id),
            doc_type,
            str(file_id) if file_id is not None else "",
            content_sha256,
            anchored_at.isoformat(),
        ]
    )
    return sha256_text(material)


def _append(
    db: Session,
    *,
    application_id: int,
    doc_type: str,
    file_id: int | None,
    content_sha256: str,
) -> DocumentAnchor:
    """사슬 끝에 한 고리를 붙인다. 호출자가 커밋한다.

    락을 먼저 잡는다 — 잡기 전에 마지막 행을 읽으면 그 사이에 남이 끼어들어
    같은 `prev` 를 재료로 쓴 고리가 둘 생긴다. 그러면 사슬이 두 갈래가 된다.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _CHAIN_LOCK_KEY})

    last = db.scalar(select(DocumentAnchor).order_by(DocumentAnchor.seq.desc()).limit(1))
    seq = (last.seq + 1) if last else 1
    prev = last.chain_hash if last else None

    # 서버 시각으로 굳힌다. 재료에 들어갈 값이라 DB default(now())에 맡기면
    # 파이썬이 모르는 값으로 채워져 chain_hash 를 계산할 수 없다.
    anchored_at = db.scalar(select(func.now()))

    row = DocumentAnchor(
        seq=seq,
        application_id=application_id,
        doc_type=doc_type,
        file_id=file_id,
        content_sha256=content_sha256,
        prev_chain_hash=prev,
        anchored_at=anchored_at,
        chain_hash=compute_chain_hash(
            prev_chain_hash=prev,
            seq=seq,
            application_id=application_id,
            doc_type=doc_type,
            file_id=file_id,
            content_sha256=content_sha256,
            anchored_at=anchored_at,
        ),
    )
    db.add(row)
    db.flush()
    return row


def anchor_application(db: Session, application_id: int) -> list[DocumentAnchor]:
    """지원서 하나의 제출물을 앵커한다. 이미 앵커된 것은 건너뛴다.

    **여러 번 불러도 안전하다** — 재시도·백필이 사슬을 부풀리면 안 되기 때문이다.
    건너뛰는 판단은 DB 의 유일 제약과 같은 기준(파일은 `file_id`, 자기소개는
    지원서당 하나)으로 여기서 먼저 걸러 낸다.

    파일 하나가 실패해도 나머지는 앵커한다. S3 에서 못 읽는 파일 하나 때문에
    자기소개까지 지문이 안 남으면 손해가 크다.
    """
    application = db.get(Application, application_id)
    if application is None:
        return []

    existing = set(
        db.scalars(
            select(DocumentAnchor.doc_type).where(
                DocumentAnchor.application_id == application_id,
                DocumentAnchor.file_id.is_(None),
            )
        )
    )
    anchored_file_ids = set(
        db.scalars(select(DocumentAnchor.file_id).where(DocumentAnchor.file_id.isnot(None)))
    )

    made: list[DocumentAnchor] = []

    # 자기소개 — 빈 값은 앵커하지 않는다. 없는 문서의 지문은 의미가 없고,
    # 나중에 채워 넣은 것을 "바뀌었다"로 잡아 버리게 된다.
    if application.self_intro and "self_intro" not in existing:
        made.append(
            _append(
                db,
                application_id=application_id,
                doc_type="self_intro",
                file_id=None,
                content_sha256=sha256_text(application.self_intro),
            )
        )

    files = db.scalars(select(File).where(File.application_id == application_id)).all()
    for f in files:
        if f.id in anchored_file_ids:
            continue
        try:
            data = s3.read_object(f.s3_key)
        except Exception:
            logger.exception("앵커용 S3 읽기 실패: file_id=%s key=%s", f.id, f.s3_key)
            continue
        made.append(
            _append(
                db,
                application_id=application_id,
                doc_type=f.kind,
                file_id=f.id,
                content_sha256=sha256_bytes(data),
            )
        )

    if made:
        db.commit()
    return made


def anchor_application_bg(application_id: int) -> None:
    """FastAPI BackgroundTasks 용. 자체 DB 세션을 만들어 실행한다.

    제출 응답을 붙잡지 않는다 — 지문을 뜨려면 S3 에서 파일을 내려받아야 하고,
    그것 때문에 지원자가 제출 버튼 앞에서 기다릴 이유가 없다. 요약(M2)과 같은 처리다.
    """
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        anchor_application(db, application_id)
    except Exception:
        logger.exception("백그라운드 앵커 실패: application_id=%d", application_id)
        db.rollback()
    finally:
        db.close()


# ── 검증 ──────────────────────────────────────────────────────────────


def verify_anchor(db: Session, anchor: DocumentAnchor) -> dict:
    """고리 하나를 지금의 원본과 맞춰 본다.

    `status` 는 셋 중 하나다:
    - `ok`       — 원본이 제출 당시와 같다
    - `mismatch` — **원본이 바뀌었다.** 이 표가 잡으려던 것이 이것이다
    - `unreadable` — 원본을 읽을 수 없다(파일 삭제·S3 오류). 바뀐 것과 구분한다.
      "없어졌다"와 "바뀌었다"는 담당자가 해야 할 일이 다르다.
    """
    if anchor.doc_type == "self_intro":
        application = db.get(Application, anchor.application_id)
        current = application.self_intro if application else None
        if current is None:
            return {"status": "unreadable", "reason": "자기소개가 비어 있습니다"}
        actual = sha256_text(current)
    else:
        f = db.get(File, anchor.file_id) if anchor.file_id else None
        if f is None:
            return {"status": "unreadable", "reason": "파일 기록이 없습니다"}
        try:
            actual = sha256_bytes(s3.read_object(f.s3_key))
        except Exception as exc:
            logger.warning("검증용 S3 읽기 실패: file_id=%s (%s)", f.id, exc)
            return {"status": "unreadable", "reason": "파일을 읽을 수 없습니다"}

    if actual != anchor.content_sha256:
        return {"status": "mismatch", "reason": "제출 당시와 내용이 다릅니다"}
    return {"status": "ok", "reason": None}


def verify_chain(db: Session) -> dict:
    """사슬 전체를 처음부터 다시 계산해 이어지는지 본다.

    앞 고리의 지문이 맞는가(`prev_chain_hash`)와, 각 고리의 지문이 재료에서
    다시 나오는가(`chain_hash`)를 함께 본다. 한쪽만 보면 반쪽이다 —
    `prev` 만 보면 고리 내용이 바뀐 것을 놓치고, `chain_hash` 만 보면 순서가
    바뀐 것을 놓친다.

    첫 번째로 깨진 자리에서 멈춘다. 그 뒤는 전부 깨져 보이므로 세어 봐야
    도움이 되지 않고, 담당자가 봐야 할 것은 **어디서부터 어긋났는가** 하나다.
    """
    rows = db.scalars(select(DocumentAnchor).order_by(DocumentAnchor.seq)).all()

    prev_hash: str | None = None
    for i, row in enumerate(rows, start=1):
        if row.seq != i:
            return _broken(row, f"순번이 비어 있습니다 (기대 {i}, 실제 {row.seq})", len(rows))
        if row.prev_chain_hash != prev_hash:
            return _broken(row, "앞 고리와 이어지지 않습니다", len(rows))
        expected = compute_chain_hash(
            prev_chain_hash=row.prev_chain_hash,
            seq=row.seq,
            application_id=row.application_id,
            doc_type=row.doc_type,
            file_id=row.file_id,
            content_sha256=row.content_sha256,
            anchored_at=row.anchored_at,
        )
        if expected != row.chain_hash:
            return _broken(row, "고리 자체가 다시 계산되지 않습니다", len(rows))
        prev_hash = row.chain_hash

    return {"intact": True, "length": len(rows), "broken_at": None, "reason": None}


def _broken(row: DocumentAnchor, reason: str, length: int) -> dict:
    return {"intact": False, "length": length, "broken_at": row.seq, "reason": reason}
