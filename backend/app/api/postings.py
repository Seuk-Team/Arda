import os
import secrets
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Application, JobPosting, User
from app.schemas.posting import PostingCreate, PostingOut, PostingUpdate, PublicLinkOut

router = APIRouter(prefix="/api/v1/postings", tags=["postings"])

# 지원 폼이 열리는 곳. 비어 있으면 상대 경로로 준다 — 로컬·CI 에서 호스트를 모른다.
PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "").rstrip("/")


def _get_or_404(db: Session, posting_id: int) -> JobPosting:
    posting = db.get(JobPosting, posting_id)
    if posting is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "공고를 찾을 수 없습니다")
    return posting


def _expire(posting: JobPosting) -> bool:
    """마감일이 지난 열린 공고를 닫는다. 바꿨으면 True — 커밋은 호출부가 한다."""
    if posting.deadline and posting.status == "open" and posting.deadline < date.today():
        posting.status = "closed"
        return True
    return False


def auto_close(db: Session, posting: JobPosting) -> JobPosting:
    """마감일이 지났으면 조회하는 김에 닫는다 (B4).

    **스케줄러를 따로 띄우지 않는 이유**: 배치 프로세스가 하나 늘면 배포·감시할
    것이 하나 더 는다. 그런데 "마감된 공고"가 문제가 되는 순간은 누군가 그 공고를
    볼 때뿐이다. 아무도 안 보는 동안 상태가 늦게 바뀌어도 관측되지 않는다.
    그래서 조회 시점에 판정한다.

    `public.py` 도 이 함수를 쓴다 — 담당자 화면과 지원자 화면이 서로 다른 상태를
    보면 안 된다.
    """
    if _expire(posting):
        db.commit()
    return posting


@router.get("", response_model=list[PostingOut])
def list_postings(
    db: Session = Depends(get_db),
    # 02-api.md 6행: "공개로 표시된 것 외에는 전부 로그인 필요". 이 경로에는 공개 표시가
    # 없는데 토큰 검사가 빠져 있어 draft 공고가 그대로 나갔다 (#97).
    # 역할은 제한하지 않는다 — 면접관도 어떤 공고가 있는지는 봐야 한다.
    user: User = Depends(get_current_user),
):
    # B3 지원자 수 — 컬럼을 두지 않고 LEFT JOIN 집계로 낸다
    rows = db.execute(
        select(JobPosting, func.count(Application.id))
        .outerjoin(Application, Application.job_posting_id == JobPosting.id)
        .group_by(JobPosting.id)
        .order_by(JobPosting.created_at.desc())
    ).all()
    # B4 — 목록도 조회 지점이다. 행마다 커밋하지 않고 한 번에 모아 커밋한다.
    if any([_expire(p) for p, _ in rows]):
        db.commit()
    return [
        PostingOut.model_validate(p).model_copy(update={"application_count": n})
        for p, n in rows
    ]


@router.post("", response_model=PostingOut, status_code=http.HTTP_201_CREATED)
def create_posting(
    body: PostingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    posting = JobPosting(**body.model_dump(), created_by=user.id)
    db.add(posting)
    db.commit()
    return PostingOut.model_validate(posting)


@router.get("/{posting_id}", response_model=PostingOut)
def get_posting(
    posting_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),  # #97 — 목록과 같은 이유
):
    return PostingOut.model_validate(auto_close(db, _get_or_404(db, posting_id)))


@router.patch("/{posting_id}", response_model=PostingOut)
def update_posting(
    posting_id: int,
    body: PostingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    posting = _get_or_404(db, posting_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(posting, field, value)
    db.commit()
    return PostingOut.model_validate(posting)


@router.post(
    "/{posting_id}/public-link",
    response_model=PublicLinkOut,
    status_code=http.HTTP_201_CREATED,
)
def issue_public_link(
    posting_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """공개 지원 링크 발급·재발급 (B6).

    **순번을 쓰지 않는 이유**: 주소가 `/public/postings/1` 이면 숫자만 바꿔
    남의 공고가 열린다. 아직 공개하지 않은 `draft` 공고까지 훑을 수 있다.
    `secrets.token_urlsafe(16)` 은 128비트라 추측으로 맞힐 수 없다.

    재발급하면 컬럼을 덮어쓰므로 **이전 토큰은 그 순간 무효**가 된다. 링크가
    엉뚱한 곳에 돌아다닐 때 담당자가 끊을 수 있는 수단이다.
    """
    posting = _get_or_404(db, posting_id)
    posting.public_token = secrets.token_urlsafe(16)
    db.commit()
    return PublicLinkOut(
        public_token=posting.public_token,
        url=f"{PUBLIC_APP_BASE_URL}/apply/{posting.public_token}",
    )


@router.delete("/{posting_id}", status_code=http.HTTP_204_NO_CONTENT)
def delete_posting(
    posting_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    posting = _get_or_404(db, posting_id)

    # 지원서가 딸린 공고는 지우지 않는다. applications.job_posting_id 에 ondelete 규칙이
    # 없어 그대로 두면 커밋 시 FK 위반으로 500 이 난다. 함께 지우려면 스키마 변경이라
    # 전원 합의가 필요하므로(01-erd.md), 여기서는 막고 409 로 알린다.
    linked = db.scalar(
        select(func.count())
        .select_from(Application)
        .where(Application.job_posting_id == posting_id)
    )
    if linked:
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            f"지원서 {linked}건이 있는 공고는 삭제할 수 없습니다. 먼저 공고를 마감하세요.",
        )

    db.delete(posting)
    db.commit()
