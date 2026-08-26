from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import Application, JobPosting, User
from app.schemas.posting import PostingCreate, PostingOut, PostingUpdate

router = APIRouter(prefix="/api/v1/postings", tags=["postings"])

# 공고를 만드는 것은 recruiter 이상 (02-api.md).
require_recruiter = require_roles("admin", "recruiter")


def _get_or_404(db: Session, posting_id: int) -> JobPosting:
    posting = db.get(JobPosting, posting_id)
    if posting is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "공고를 찾을 수 없습니다")
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
    return [
        PostingOut.model_validate(p).model_copy(update={"application_count": n})
        for p, n in rows
    ]


@router.post("", response_model=PostingOut, status_code=http.HTTP_201_CREATED)
def create_posting(
    body: PostingCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_recruiter),
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
    return PostingOut.model_validate(_get_or_404(db, posting_id))


@router.patch("/{posting_id}", response_model=PostingOut)
def update_posting(
    posting_id: int,
    body: PostingUpdate,
    db: Session = Depends(get_db),
    # 생성이 recruiter+ 인데 수정이 아무나면 막는 의미가 없다. #59 로 물어
    # 팀장이 recruiter+ 로 확정했고 02-api.md 24행에 반영했다.
    user: User = Depends(require_recruiter),
):
    posting = _get_or_404(db, posting_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(posting, field, value)
    db.commit()
    return PostingOut.model_validate(posting)


@router.delete("/{posting_id}", status_code=http.HTTP_204_NO_CONTENT)
def delete_posting(
    posting_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_recruiter),  # #59 — 수정과 같은 이유
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
