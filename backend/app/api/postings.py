from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Application, JobPosting
from app.schemas.posting import PostingCreate, PostingOut, PostingUpdate

router = APIRouter(prefix="/api/v1/postings", tags=["postings"])


def _get_or_404(db: Session, posting_id: int) -> JobPosting:
    posting = db.get(JobPosting, posting_id)
    if posting is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "공고를 찾을 수 없습니다")
    return posting


@router.get("", response_model=list[PostingOut])
def list_postings(db: Session = Depends(get_db)):
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
def create_posting(body: PostingCreate, db: Session = Depends(get_db)):
    posting = JobPosting(**body.model_dump())
    # TODO(A1): created_by 를 토큰의 사용자로 채운다. 인증은 팀장 담당
    db.add(posting)
    db.commit()
    return PostingOut.model_validate(posting)


@router.get("/{posting_id}", response_model=PostingOut)
def get_posting(posting_id: int, db: Session = Depends(get_db)):
    return PostingOut.model_validate(_get_or_404(db, posting_id))


@router.patch("/{posting_id}", response_model=PostingOut)
def update_posting(posting_id: int, body: PostingUpdate, db: Session = Depends(get_db)):
    posting = _get_or_404(db, posting_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(posting, field, value)
    db.commit()
    return PostingOut.model_validate(posting)


@router.delete("/{posting_id}", status_code=http.HTTP_204_NO_CONTENT)
def delete_posting(posting_id: int, db: Session = Depends(get_db)):
    db.delete(_get_or_404(db, posting_id))
    db.commit()
