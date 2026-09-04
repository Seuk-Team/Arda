"""제출물 무결성 조회·앵커 (ADR-0028).

전부 **로그인 필요**다. 무결성 결과는 지원자에게 내려주지 않는다 — "당신 파일이
바뀌었습니다"를 지원자가 먼저 아는 상황은, 바꾼 것이 우리 쪽일 때 특히 곤란하다.
담당자가 먼저 보고 판단할 것이다.
"""

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import anchoring
from app.db import get_db
from app.deps import get_current_user
from app.models import Application, DocumentAnchor, File, User
from app.schemas.integrity import (
    AnchorItem,
    ApplicationIntegrityOut,
    ChainIntegrityOut,
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


@router.get("/integrity/chain", response_model=ChainIntegrityOut)
def get_chain(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """원장 전체가 이어지는지 본다.

    개별 문서 검증(`/applications/{id}/integrity`)은 "원본이 바뀌었나"를 보고,
    이쪽은 "**원장 자체가 손대졌나**"를 본다. 둘은 다른 질문이다 — 원본을 바꾸고
    앵커 행까지 같이 고쳐 놓으면 개별 검증은 통과하지만 사슬이 깨진다.
    """
    return ChainIntegrityOut(**anchoring.verify_chain(db))
