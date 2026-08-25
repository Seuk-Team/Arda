from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status as http
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent.summarizer import generate_summary_bg
from app.db import get_db
from app.models import Application, JobPosting, StageHistory
from app.schemas.application import ApplicationCreate, ApplicationOut, PostingPublicOut

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.get("/postings/{posting_id}", response_model=PostingPublicOut)
def get_posting(posting_id: int, db: Session = Depends(get_db)):
    posting = db.get(JobPosting, posting_id)
    if posting is None or posting.status != "open":
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원할 수 없는 공고입니다")
    return posting


@router.post(
    "/postings/{posting_id}/applications",
    response_model=ApplicationOut,
    status_code=http.HTTP_201_CREATED,
)
def submit(posting_id: int, body: ApplicationCreate, bg: BackgroundTasks, db: Session = Depends(get_db)):
    posting = db.get(JobPosting, posting_id)
    if posting is None or posting.status != "open":
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원할 수 없는 공고입니다")

    row = Application(
        job_posting_id=posting_id,
        source="form",
        current_stage="applied",
        privacy_agreed_at=func.now(),  # 서버 시각. 클라이언트 값을 믿지 않는다
        **body.model_dump(exclude={"privacy_agreed"}),
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:  # C6 — UNIQUE(job_posting_id, email)
        db.rollback()
        raise HTTPException(http.HTTP_409_CONFLICT, "이미 이 공고에 지원했습니다")

    # D5 — 접수도 이력이다. 시스템이 한 것이므로 changed_by 는 NULL
    db.add(StageHistory(application_id=row.id, from_stage=None, to_stage="applied"))
    db.commit()

    # M2: AI 요약 생성 (비동기). ANTHROPIC_API_KEY 미설정이면 조용히 건너뛴다.
    bg.add_task(generate_summary_bg, row.id)

    return ApplicationOut.model_validate(row)
