"""AI 면접 API — 세션 생성과 지원자 공개 접근 (ADR-0026).

설계는 docs/02_tasks/AI면접-설계.md §5 의 2·3번.

지원자는 로그인이 없으므로 일정 제안(ADR-0016)과 **같은 토큰 공개 접근 패턴**을 쓴다.
만료도 같은 방식이다 — 스케줄러 없이 조회 시점에 판정한다(B4 마감과 동일).

**질문은 아직 자동 생성하지 않는다.** 설계 §5 의 5번에서 붙인다. 그때까지는
담당자가 넣은 질문 목록으로 돈다 — 그래야 뼈대가 먼저 관통된다.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import (
    Application,
    InterviewSession,
    InterviewTurn,
    JobPosting,
    User,
)
from app.schemas.interview import (
    ConsentRequest,
    InterviewPublicOut,
    SessionCreate,
    SessionDetailOut,
    SessionOut,
)

router = APIRouter(prefix="/api/v1", tags=["interviews"])

PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "").rstrip("/")

# 링크 기본 유효 기간. 일정 제안과 같은 감각으로 짧게 둔다 —
# 오래 열어 두면 그만큼 오래 남의 손에 링크가 굴러다닌다.
DEFAULT_EXPIRES_DAYS = 7


def _public_url(token: str) -> str:
    """지원자에게 줄 주소. **서버가 조립한다.**

    화면이 조립하게 두면 메일 미리보기와 실제 발송이 갈리는 것과 같은 일이 생긴다.
    `PUBLIC_APP_BASE_URL` 이 비면 상대 경로로 준다(일정 제안과 같은 처리).
    """
    return f"{PUBLIC_APP_BASE_URL}/interview/{token}"


def _to_out(session: InterviewSession) -> SessionOut:
    return SessionOut(
        id=session.id,
        application_id=session.application_id,
        status=session.status,
        token=session.token,
        url=_public_url(session.token),
        expires_at=session.expires_at,
        consented_at=session.consented_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
        created_at=session.created_at,
    )


# ── 담당자용 ──────────────────────────────────────────────────────


@router.post(
    "/applications/{application_id}/interview-sessions",
    response_model=SessionOut,
    status_code=HTTPStatus.CREATED,
)
def create_session(
    application_id: int,
    body: SessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI 면접 세션 생성 + 공개 링크 발급.

    **재생성하지 않고 매번 새 행을 만든다.** 옛 세션은 그대로 남는다 —
    이력이 사라지지 않는 편이 낫다(stage_history·schedule_proposals 와 같은 철학).
    그래서 링크를 다시 뽑아도 **이전 링크가 죽지 않는다** — 공고 public-link 와 다른 점이다.
    """
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    days = body.expires_in_days or DEFAULT_EXPIRES_DAYS
    session = InterviewSession(
        application_id=application_id,
        # public_token(B6)과 같은 근거 — 128비트라 추측으로 맞힐 수 없다
        token=secrets.token_urlsafe(16),
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=days),
        created_by=user.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _to_out(session)


@router.get(
    "/applications/{application_id}/interview-sessions",
    response_model=list[SessionOut],
)
def list_sessions(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이 지원자의 면접 세션 목록. 최신 먼저."""
    rows = db.scalars(
        select(InterviewSession)
        .where(InterviewSession.application_id == application_id)
        .order_by(InterviewSession.created_at.desc())
    ).all()
    return [_to_out(s) for s in rows]


@router.get("/interview-sessions/{session_id}", response_model=SessionDetailOut)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """전사와 대조 결과까지 포함한 상세."""
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "면접 세션을 찾을 수 없습니다")

    base = _to_out(session)
    return SessionDetailOut(
        **base.model_dump(),
        turns=sorted(session.turns, key=lambda t: t.seq),
        findings=list(session.findings),
    )


# ── 공개 라우트 — 지원자용 (토큰 접근, 로그인 없음) ────────────────


def _get_by_token(db: Session, token: str) -> InterviewSession:
    """토큰으로 찾고 조회 시점에 만료를 판정한다 (B4·일정 제안과 같은 방식).

    **만료를 200 으로 내려준다** — 지원자가 "기한이 지났다"를 보는 편이
    빈 화면보다 낫다. 일정 제안 공개 조회와 같은 판단이다.
    """
    session = db.scalar(
        select(InterviewSession).where(InterviewSession.token == token)
    )
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "유효하지 않은 링크입니다")

    now = datetime.now(timezone.utc)
    if (
        session.status in ("pending", "in_progress")
        and session.expires_at is not None
        and session.expires_at <= now
    ):
        session.status = "expired"
        db.commit()

    return session


@router.get("/public/interview/{token}", response_model=InterviewPublicOut)
def get_interview_public(token: str, db: Session = Depends(get_db)):
    """지원자용 조회. 공개 — 토큰이 곧 인증이다.

    **담당자 이름·평가·다른 지원자는 내려주지 않는다.** 지원자에게 필요한 것은
    자기가 어느 면접에 와 있는지와 지금 뭘 하면 되는지뿐이다.
    """
    session = _get_by_token(db, token)
    application = db.get(Application, session.application_id)
    posting = db.get(JobPosting, application.job_posting_id) if application else None

    current = None
    if session.status == "in_progress" and session.turns:
        last = max(session.turns, key=lambda t: t.seq)
        # 아직 답 안 한 질문이 현재 질문이다
        if last.transcript is None:
            current = last

    return InterviewPublicOut(
        status=session.status,
        applicant_name=application.name if application else "",
        posting_title=posting.title if posting else "",
        expires_at=session.expires_at,
        consent_required=session.consented_at is None,
        current_question=current.question if current else None,
        question_seq=current.seq if current else None,
    )


@router.post("/public/interview/{token}/consent", response_model=InterviewPublicOut)
def give_consent(token: str, body: ConsentRequest, db: Session = Depends(get_db)):
    """녹음·전사·보관 동의. **면접 시작의 선행 조건이다.**

    지원 폼에서 받은 개인정보 동의와 별개다 — 그때는 녹음이 없었다.
    동의하지 않으면 시작할 수 없고, 그 사실을 화면이 알려 준다.
    """
    session = _get_by_token(db, token)
    if session.status != "pending":
        raise HTTPException(
            HTTPStatus.CONFLICT, "이미 시작했거나 끝난 면접입니다"
        )
    if not body.agreed:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "녹음·전사에 동의해야 면접을 시작할 수 있습니다",
        )

    session.consented_at = datetime.now(timezone.utc)
    db.commit()
    return get_interview_public(token, db)


@router.post("/public/interview/{token}/start", response_model=InterviewPublicOut)
def start_interview(token: str, db: Session = Depends(get_db)):
    """면접 시작. **동의가 없으면 거절한다.**

    질문은 아직 자동 생성하지 않는다(설계 §5 의 5번). 담당자가 미리 넣어 둔
    질문이 없으면 시작할 수 없다 — 빈 면접을 여는 것보다 낫다.
    """
    session = _get_by_token(db, token)

    if session.status == "expired":
        raise HTTPException(HTTPStatus.GONE, "링크 유효 기간이 지났습니다")
    if session.status != "pending":
        raise HTTPException(HTTPStatus.CONFLICT, "이미 시작했거나 끝난 면접입니다")
    if session.consented_at is None:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "녹음·전사 동의가 필요합니다",
        )

    first = db.scalar(
        select(InterviewTurn)
        .where(InterviewTurn.session_id == session.id)
        .order_by(InterviewTurn.seq)
    )
    if first is None:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "준비된 질문이 없습니다 — 담당자에게 문의해 주세요",
        )

    session.status = "in_progress"
    session.started_at = datetime.now(timezone.utc)
    db.commit()
    return get_interview_public(token, db)
