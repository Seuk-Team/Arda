import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status as http
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import mail
from app.agent.summarizer import generate_summary_bg
from app.api.postings import auto_close
from app.db import get_db
from app.models import Application, JobPosting, StageHistory
from app.schemas.application import ApplicationCreate, ApplicationOut, PostingPublicOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/public", tags=["public"])


def _openable(db: Session, posting: JobPosting | None) -> JobPosting:
    """지원 가능한 공고인지 본다. 아니면 이유에 맞는 상태 코드로 막는다 (B4).

    **마감을 404 가 아니라 410 으로 주는 이유**: 404 는 "그런 공고 없음"이라
    지원자가 링크를 잘못 받았다고 생각한다. 410 Gone 이어야 "있었지만 끝났다"가
    전달된다. 지원자에게는 이 구분이 곧 "다시 확인해 보라" 와 "포기해도 된다" 다.

    `draft` 는 아직 공개한 적이 없으므로 404 가 맞다 — 존재를 알릴 이유가 없다.
    """
    if posting is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원할 수 없는 공고입니다")

    auto_close(db, posting)  # 마감일이 지났으면 여기서 닫힌다

    if posting.status == "closed":
        raise HTTPException(http.HTTP_410_GONE, "마감된 공고입니다")
    if posting.status != "open":
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원할 수 없는 공고입니다")
    return posting


# 이 경로를 `/postings/{posting_id}` 보다 먼저 선언한다 — 뒤에 두면 "by-token" 이
# posting_id 로 먼저 걸려 422 가 난다.
@router.get("/postings/by-token/{token}", response_model=PostingPublicOut)
def get_posting_by_token(token: str, db: Session = Depends(get_db)):
    """공개 링크 토큰으로 공고 조회 (B6)."""
    posting = db.scalar(select(JobPosting).where(JobPosting.public_token == token))
    return _openable(db, posting)


@router.get("/postings/{posting_id}", response_model=PostingPublicOut)
def get_posting(posting_id: int, db: Session = Depends(get_db)):
    return _openable(db, db.get(JobPosting, posting_id))


@router.post(
    "/postings/{posting_id}/applications",
    response_model=ApplicationOut,
    status_code=http.HTTP_201_CREATED,
)
def submit(posting_id: int, body: ApplicationCreate, bg: BackgroundTasks, db: Session = Depends(get_db)):
    # B4 — 마감된 공고에 제출하면 410. 조회와 같은 판정을 쓴다.
    _openable(db, db.get(JobPosting, posting_id))

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

    # C4 — 접수 확인 메일. 큐에만 넣고 즉시 반환한다.
    # 지원자가 제출 버튼을 누르고 SES 를 기다릴 이유가 없고, 큐가 죽었다고 해서
    # 이미 저장된 지원서(위에서 커밋했다)를 무를 수도 없다. 그래서 예외를 삼킨다.
    try:
        mail.enqueue(db, application_id=row.id, to_email=row.email, stage="applied")
    except Exception:
        logger.exception("확인 메일 큐 발행 실패 application_id=%s", row.id)
    try:
        # 큐 발행이 실패했어도 email_logs 행은 남긴다 — "보냈어야 할 메일"을
        # 나중에 셀 수 있어야 한다. change_stage 와 같은 처리다.
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("확인 메일 기록 저장 실패 application_id=%s", row.id)

    # M2: AI 요약 생성 (비동기). ANTHROPIC_API_KEY 미설정이면 조용히 건너뛴다.
    bg.add_task(generate_summary_bg, row.id)

    return ApplicationOut.model_validate(row)
