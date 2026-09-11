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

from app import chain, ots, s3
from app.models import Application, ChainPublication, DocumentAnchor, File

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



# ── 공개 체인에 못 박기 (ADR-0028 2·3단계) ────────────────────────────
#
# **못 박는 곳이 둘이다.** 폴리곤은 보여주는 쪽, OpenTimestamps 는 남기는 쪽.
# 올리는 값은 양쪽 다 **사슬 머리 하나**로 같아서 보내는 곳만 갈린다.
#
# 서명 위치도 갈린다:
#   폴리곤 — 개인키가 필요하다. 서버에 키를 두지 않기로 해서(팀장 검토 Q2)
#            **GitHub Actions 가 서명·전송하고 결과만 여기로 기록**한다
#            (`start_publication` → `record_result`).
#   OTS    — 개인키가 없다. 서버에서 그냥 돌린다 (`publish_ots`).


class NothingToPublish(Exception):
    """올릴 것이 없다. 원장이 비었거나, 그 네트워크에 이미 올린 머리다."""


def current_head(db: Session) -> DocumentAnchor | None:
    """지금 사슬 머리. **이 하나가 그 앞 전부를 덮는다.**"""
    return db.scalar(select(DocumentAnchor).order_by(DocumentAnchor.seq.desc()).limit(1))


def _head_or_raise(db: Session, network: str) -> DocumentAnchor:
    head = current_head(db)
    if head is None:
        raise NothingToPublish("원장이 비어 있습니다")

    already = db.scalar(
        select(ChainPublication).where(
            ChainPublication.network == network,
            ChainPublication.chain_hash == head.chain_hash,
            ChainPublication.status != "failed",
        )
    )
    if already is not None:
        raise NothingToPublish(
            f"{network} 에는 이미 올렸습니다 (seq={already.covered_through_seq})"
        )
    return head


def start_publication(db: Session, network: str) -> ChainPublication:
    """게시할 자리를 먼저 잡는다. **보내기 전에 행을 만든다.**

    반대로 하면 보내는 데 성공하고 기록에 실패했을 때 "체인에는 있는데 우리는
    모르는 거래"가 생긴다. 그건 나중에 사람이 탐색기를 뒤져야 찾는다.

    GitHub Actions 경로에서는 이걸 API 로 받아 가고, 서명·전송을 마친 뒤
    `record_result` 로 결과를 되돌려 준다.
    """
    head = _head_or_raise(db, network)
    row = ChainPublication(
        network=network,
        covered_through_seq=head.seq,
        chain_hash=head.chain_hash,
        status="pending",
    )
    db.add(row)
    db.commit()
    return row


def record_result(
    db: Session,
    publication_id: int,
    *,
    status: str,
    tx_hash: str | None = None,
    block_number: int | None = None,
    from_address: str | None = None,
    proof: str | None = None,
    error: str | None = None,
) -> ChainPublication:
    """밖에서 서명·전송한 결과를 기록한다 (GitHub Actions 경로).

    **서버는 여기서 아무것도 검증하지 못한다** — 키가 없어 서명을 확인할 수
    없기 때문이다. 그래도 상관없다. `tx_hash` 가 가리키는 체인의 값이 진실이고,
    이 표는 "어디를 보면 되는지"를 적어 둔 영수증일 뿐이다. 거짓으로 적어 넣어도
    탐색기에서 대조하면 드러난다.
    """
    row = db.get(ChainPublication, publication_id)
    if row is None:
        raise LookupError(f"게시 기록 {publication_id} 이 없습니다")

    row.status = status
    if tx_hash is not None:
        row.tx_hash = tx_hash
    if block_number is not None:
        row.block_number = block_number
    if from_address is not None:
        row.from_address = from_address
    if proof is not None:
        row.proof = proof
    if error is not None:
        row.error = error[:2000]
    if status == "confirmed":
        row.confirmed_at = db.scalar(select(func.now()))
    db.commit()
    return row


def publish_ots(db: Session) -> ChainPublication:
    """사슬 머리를 OpenTimestamps 에 도장 찍는다. **서버에서 직접 돈다.**

    개인키가 없어서 가능하다 — 캘린더에 해시만 던지고 증명을 받아 온다.
    돌아온 증명은 아직 `pending` 이다(비트코인 블록에 안 실림). 몇 시간 뒤
    `refresh_pending` 이 갱신해 `confirmed` 로 바꾼다.
    """
    row = start_publication(db, ots.NETWORK)
    try:
        proof = ots.stamp(row.chain_hash)
    except Exception as exc:
        row.status = "failed"
        row.error = f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
        logger.exception("OTS 도장 실패 seq=%s", row.covered_through_seq)
        raise

    row.proof = proof
    # 도장은 찍혔지만 비트코인 확정은 아직이다. 여기서 confirmed 로 적으면
    # 우리가 가진 것보다 강한 주장을 하게 된다.
    row.status = "confirmed" if ots.is_confirmed(proof) else "pending"
    if row.status == "confirmed":
        row.confirmed_at = db.scalar(select(func.now()))
    db.commit()
    return row


def publish_head(db: Session) -> ChainPublication:
    """폴리곤에 직접 게시한다 — **과도기·로컬 전용 경로.**

    운영에서는 GitHub Actions 가 서명한다(팀장 검토 Q2). 이 함수는 서버에
    `CHAIN_PRIVATE_KEY` 가 있을 때만 동작하고, 없으면 설정 오류로 막힌다.
    로컬에서 흐름을 끝까지 돌려 보거나 이관 전 과도기에 쓴다.
    """
    config = chain.load_config()
    if config is None:
        raise RuntimeError(chain.unavailable_reason() or "체인 설정이 없습니다")

    row = start_publication(db, config.network)
    try:
        sent = chain.publish_hash(config, row.chain_hash)
    except Exception as exc:
        row.status = "failed"
        row.error = f"{type(exc).__name__}: {exc}"[:2000]
        db.commit()
        logger.exception("체인 게시 실패 seq=%s", row.covered_through_seq)
        raise

    row.tx_hash = sent.tx_hash
    row.from_address = sent.from_address
    row.block_number = sent.block_number
    if sent.confirmed:
        row.status = "confirmed"
        row.confirmed_at = db.scalar(select(func.now()))
    db.commit()
    return row


def refresh_pending(db: Session) -> list[ChainPublication]:
    """확정을 못 본 게시를 다시 확인한다. 네트워크마다 확인 방법이 다르다.

    - 폴리곤: 거래 영수증을 다시 조회한다 (`chain.fetch_status`)
    - OTS: 캘린더에 다시 물어 증명을 갱신한다 (`ots.upgrade`)

    **보냈는데 확정을 못 본 것은 실패가 아니다.** 폴리곤은 블록이 아직 안 나온
    것이고, OTS 는 몇 시간이 정상이다.
    """
    pending = db.scalars(
        select(ChainPublication).where(ChainPublication.status == "pending")
    ).all()

    changed: list[ChainPublication] = []
    for row in pending:
        try:
            if row.network == ots.NETWORK:
                if not row.proof:
                    continue
                proof, confirmed = ots.upgrade(row.proof)
                if proof == row.proof and not confirmed:
                    continue  # 아직. 다음 번에 다시 본다
                row.proof = proof
                if confirmed:
                    row.status = "confirmed"
                    row.block_number = ots.bitcoin_height(proof)
                    row.confirmed_at = db.scalar(select(func.now()))
                changed.append(row)
            else:
                config = chain.load_config()
                if config is None or not row.tx_hash:
                    continue
                found = chain.fetch_status(config, row.tx_hash)
                if found is None:
                    continue
                row.block_number = found.block_number
                if found.confirmed:
                    row.status = "confirmed"
                    row.confirmed_at = db.scalar(select(func.now()))
                else:
                    row.status = "failed"
                    row.error = "체인이 거래를 되돌렸습니다 (status=0)"
                changed.append(row)
        except Exception:
            # 한 건이 실패해도 나머지는 확인한다.
            logger.exception("게시 상태 갱신 실패 id=%s", row.id)

    if changed:
        db.commit()
    return changed
