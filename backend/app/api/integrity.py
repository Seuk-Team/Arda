"""제출물 무결성 조회·앵커 (ADR-0028).

전부 **로그인 필요**다. 무결성 결과는 지원자에게 내려주지 않는다 — "당신 파일이
바뀌었습니다"를 지원자가 먼저 아는 상황은, 바꾼 것이 우리 쪽일 때 특히 곤란하다.
담당자가 먼저 보고 판단할 것이다.
"""

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import anchoring, chain, ots
from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import Application, ChainPublication, DocumentAnchor, File, User
from app.schemas.integrity import (
    AnchorItem,
    ApplicationIntegrityOut,
    ChainIntegrityOut,
    PublicationOut,
    PublicationResultIn,
)

router = APIRouter(prefix="/api/v1", tags=["integrity"])


def _get_or_404(db: Session, application_id: int) -> Application:
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")
    return application


def _build(db: Session, application_id: int) -> ApplicationIntegrityOut:
    anchors = db.scalars(
        select(DocumentAnchor)
        .where(DocumentAnchor.application_id == application_id)
        .order_by(DocumentAnchor.seq)
    ).all()

    items: list[AnchorItem] = []
    for anchor in anchors:
        result = anchoring.verify_anchor(db, anchor)
        filename = None
        if anchor.file_id:
            f = db.get(File, anchor.file_id)
            filename = f.filename if f else None
        items.append(
            AnchorItem(
                seq=anchor.seq,
                doc_type=anchor.doc_type,
                file_id=anchor.file_id,
                filename=filename,
                content_sha256=anchor.content_sha256,
                chain_hash=anchor.chain_hash,
                anchored_at=anchor.anchored_at,
                status=result["status"],
                reason=result["reason"],
            )
        )

    # 나쁜 쪽이 이긴다 — 하나라도 어긋나면 전체가 어긋난 것이다.
    if not items:
        verdict = "none"
    elif any(i.status == "mismatch" for i in items):
        verdict = "mismatch"
    elif any(i.status == "unreadable" for i in items):
        verdict = "unreadable"
    else:
        verdict = "ok"

    return ApplicationIntegrityOut(
        application_id=application_id,
        anchored=bool(items),
        verdict=verdict,
        items=items,
    )


@router.get(
    "/applications/{application_id}/integrity",
    response_model=ApplicationIntegrityOut,
)
def get_integrity(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """제출물이 제출 당시 그대로인지 본다.

    **볼 때마다 원본을 다시 읽어 지문을 새로 뜬다.** 저장된 결과를 돌려주면
    "언제 검사한 값인가"가 흐려지고, 검사 이후에 바뀐 것을 놓친다.
    첨부가 있으면 S3 를 읽으므로 목록 화면에서 N 번 부를 API 가 아니다 —
    상세에서 한 번 부르는 자리다.
    """
    _get_or_404(db, application_id)
    return _build(db, application_id)


@router.post(
    "/applications/{application_id}/integrity/anchor",
    response_model=ApplicationIntegrityOut,
    status_code=http.HTTP_201_CREATED,
)
def create_anchor(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """아직 앵커가 없는 제출물의 지문을 뜬다 (백필).

    ADR-0028 이전에 접수된 지원서에는 앵커가 없다. 그것들을 사후에 넣기 위한
    자리다. **이미 앵커된 문서는 건드리지 않는다** — 여러 번 눌러도 사슬이
    부풀지 않는다.

    ⚠️ 사후 앵커는 **"이 시각에 이 내용이었다"까지만** 증명한다. 접수 시점의
    내용이었다는 증명은 아니다. 그 사이에 이미 바뀌었을 수 있기 때문이다.
    `anchored_at` 이 `applications.created_at` 보다 한참 뒤인 행이 그것이다.
    """
    _get_or_404(db, application_id)
    anchoring.anchor_application(db, application_id)
    return _build(db, application_id)


def _publication_out(row: ChainPublication) -> PublicationOut:
    """게시 기록 하나를 응답 모양으로. 탐색기 링크는 네트워크마다 다르다."""
    out = PublicationOut.model_validate(row)
    url = None
    if row.network == ots.NETWORK:
        # OTS 는 거래가 아니라 **비트코인 블록**을 가리킨다. 확정 전에는 링크가 없다.
        if row.proof:
            try:
                url = ots.explorer_url(row.proof)
            except Exception:  # 증명이 깨져 있어도 목록 조회가 죽으면 안 된다
                url = None
    elif row.tx_hash:
        url = chain.explorer_url(row.network, row.tx_hash)
    return out.model_copy(update={"explorer_url": url})


@router.get("/integrity/chain", response_model=ChainIntegrityOut)
def get_chain(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """원장 전체가 이어지는지 + 공개 체인에 못 박혔는지 본다.

    개별 문서 검증(`/applications/{id}/integrity`)은 "원본이 바뀌었나"를 보고,
    이쪽은 "**원장 자체가 손대졌나**"를 본다. 둘은 다른 질문이다 — 원본을 바꾸고
    앵커 행까지 같이 고쳐 놓으면 개별 검증은 통과하지만 사슬이 깨진다.

    `published` 까지 있어야 세 번째 질문에 답이 된다 — "**그걸 우리가 아니라
    누가 확인해 줄 수 있나.**"
    """
    result = anchoring.verify_chain(db)

    last = db.scalar(
        select(ChainPublication)
        .where(ChainPublication.status == "confirmed")
        .order_by(ChainPublication.covered_through_seq.desc())
        .limit(1)
    )
    if last is not None:
        result["published"] = _publication_out(last)
        result["unpublished_count"] = max(0, result["length"] - last.covered_through_seq)
    else:
        result["unpublished_count"] = result["length"]

    return ChainIntegrityOut(**result)


@router.get("/integrity/publications", response_model=list[PublicationOut])
def list_publications(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """못 박은 기록 목록. 최신순."""
    rows = db.scalars(
        select(ChainPublication).order_by(ChainPublication.id.desc()).limit(50)
    ).all()
    return [_publication_out(r) for r in rows]


@router.post(
    "/integrity/publish",
    response_model=PublicationOut,
    status_code=http.HTTP_201_CREATED,
)
def publish(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    """지금 사슬 머리를 공개 체인에 올린다. **admin 만.**

    돈(가스)이 나가고 되돌릴 수 없는 바깥 행위라 조회와 같은 권한에 두지 않는다.
    지금은 테스트넷이라 값이 0 이지만, 메인넷으로 갈아탈 때 권한을 새로 짜는 일이
    없도록 처음부터 좁혀 둔다.

    상태 코드로 사유를 가른다 — 09/02 에 "왜 안 되는지 모르겠다"로 시간을 쓴 적이
    있어서다:
    - **503** 설정이 없다 (`CHAIN_RPC_URL`·`CHAIN_PRIVATE_KEY`)
    - **409** 올릴 것이 없다 (원장이 비었거나 지난번 이후 새 고리가 없다)
    - **502** 체인에 보내다 실패했다. 기록은 `failed` 로 남는다
    """
    reason = chain.unavailable_reason()
    if reason:
        raise HTTPException(
            http.HTTP_503_SERVICE_UNAVAILABLE, f"체인에 올릴 수 없습니다: {reason}"
        )

    try:
        row = anchoring.publish_head(db)
    except anchoring.NothingToPublish as exc:
        raise HTTPException(http.HTTP_409_CONFLICT, str(exc))
    except Exception as exc:
        raise HTTPException(
            http.HTTP_502_BAD_GATEWAY,
            f"체인에 보내지 못했습니다: {type(exc).__name__}",
        )

    return _publication_out(row)


@router.post(
    "/integrity/publish/ots",
    response_model=PublicationOut,
    status_code=http.HTTP_201_CREATED,
)
def publish_ots(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    """사슬 머리를 OpenTimestamps(비트코인)에 도장 찍는다. **admin 만.**

    **폴리곤과 달리 개인키가 없어서 서버에서 직접 돈다.** 캘린더에 해시만 던지고
    증명을 받아 오기 때문이다 — 그래서 키를 밖으로 빼야 하는 이유(팀장 검토 Q2)가
    여기에는 해당하지 않는다.

    돌아온 증명은 대개 **`pending`** 이다. 비트코인 블록에 아직 안 실렸다는 뜻이고
    몇 시간이 정상이다. `POST /integrity/publications/refresh` 가 나중에 갱신한다.
    여기서 바로 `confirmed` 로 적으면 우리가 가진 것보다 강한 주장이 된다.
    """
    try:
        row = anchoring.publish_ots(db)
    except anchoring.NothingToPublish as exc:
        raise HTTPException(http.HTTP_409_CONFLICT, str(exc))
    except Exception as exc:
        raise HTTPException(
            http.HTTP_502_BAD_GATEWAY,
            f"OTS 도장을 찍지 못했습니다: {type(exc).__name__}",
        )
    return _publication_out(row)


@router.post(
    "/integrity/publications/start",
    response_model=PublicationOut,
    status_code=http.HTTP_201_CREATED,
)
def start_publication(
    network: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    """게시할 자리를 잡고 **무엇을 올려야 하는지** 알려준다 (GitHub Actions 용).

    폴리곤 서명은 서버가 하지 않는다 — 개인키를 서버에 두지 않기로 했다
    (팀장 검토 Q2). 대신 Actions 가 이 경로로 **사슬 머리와 게시 id** 를 받아
    가서 스스로 서명·전송하고, `POST .../{id}/result` 로 결과를 되돌려 준다.

    **행을 먼저 만든다.** 보낸 뒤에 기록하면, 보내는 데 성공하고 기록에 실패했을
    때 "체인에는 있는데 우리는 모르는 거래"가 생긴다.

    올릴 것이 없으면 **409** 다 — 원장이 비었거나 그 네트워크에 이미 올린 머리다.
    """
    try:
        row = anchoring.start_publication(db, network)
    except anchoring.NothingToPublish as exc:
        raise HTTPException(http.HTTP_409_CONFLICT, str(exc))
    return _publication_out(row)


@router.post(
    "/integrity/publications/{publication_id}/result",
    response_model=PublicationOut,
)
def record_result(
    publication_id: int,
    body: PublicationResultIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    """밖에서 서명·전송한 결과를 기록한다 (GitHub Actions 용).

    **서버는 이 값을 검증하지 못한다.** 키가 없어 서명을 확인할 수 없기
    때문이다. 그래도 상관없다 — `tx_hash` 가 가리키는 체인의 값이 진실이고,
    이 기록은 "어디를 보면 되는지"를 적어 둔 영수증이다. 거짓으로 적어 넣어도
    탐색기에서 대조하면 드러난다.
    """
    try:
        row = anchoring.record_result(
            db, publication_id, **body.model_dump(exclude_none=True)
        )
    except LookupError as exc:
        raise HTTPException(http.HTTP_404_NOT_FOUND, str(exc))
    return _publication_out(row)


@router.post("/integrity/publications/refresh", response_model=list[PublicationOut])
def refresh(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """확정을 못 본 거래들을 다시 확인한다.

    보냈는데 영수증을 못 받은 것은 실패가 아니라 **블록이 아직 안 나온 것**이다.
    여기서 뒤늦게 `confirmed` 로 바뀐다. 바뀐 것만 돌려준다.
    """
    return [_publication_out(r) for r in anchoring.refresh_pending(db)]
