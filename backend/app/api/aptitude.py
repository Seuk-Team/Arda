"""사전 성향 설문 API — 발송·공개 응답·담당자 조회 (ADR-0027).

토큰 공개 접근·조회 시점 만료 판정은 AI 면접(interviews.py)과 같은 패턴이다.
발송은 접수 후·서류검토 전이 원칙이고, 응답은 서류검토 참고자료가 된다.

**미응답은 아무것도 막지 않는다** — 서류검토는 그대로 진행되고, 정렬·필터에
응답 여부를 끼워 넣지 않는다 (ADR-0027 결정 4). 이 라우터는 발송·조회·제출만
안다. 단계 이동·평가 어디에도 손대지 않는다.
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.agent.aptitude import compute_stats, generate_aptitude_summary_bg
from app.aptitude_questions import (
    LIKERT_LABELS,
    QUESTION_KEYS,
    QUESTIONS,
    QUESTIONS_BY_KEY,
)
from app.db import get_db
from app.deps import get_current_user
from app.models import Application, AptitudeAnswer, AptitudeSession, JobPosting, User
from app.schemas.aptitude import (
    AnswerOut,
    AptitudeDetailOut,
    AptitudePublicOut,
    BulkSendOut,
    CategoryStatOut,
    PublicQuestionOut,
    SessionOut,
    SubmitRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["aptitude"])

PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "").rstrip("/")

# 링크 기본 유효 기간 — AI 면접·일정 제안과 같은 7일 (ADR-0027 미결 표의 기본안)
DEFAULT_EXPIRES_DAYS = 7

# 발송 대상 단계 — 서류검토 전·중. 이후 단계는 목적(서류검토 참고)이 지났다.
# 개별 재발송도 같은 제한을 받는다 — 원칙이 버튼에 따라 달라지면 원칙이 아니다.
SENDABLE_STAGES = ("applied", "screening")


def _public_url(token: str) -> str:
    """지원자에게 줄 주소. 서버가 조립한다 (interviews._public_url 과 같은 이유)."""
    return f"{PUBLIC_APP_BASE_URL}/aptitude/{token}"


def _to_out(session: AptitudeSession) -> SessionOut:
    return SessionOut(
        id=session.id,
        application_id=session.application_id,
        status=session.status,
        token=session.token,
        url=_public_url(session.token),
        expires_at=session.expires_at,
        submitted_at=session.submitted_at,
        created_at=session.created_at,
    )


def _new_session(db: Session, application_id: int, user_id: int) -> AptitudeSession:
    session = AptitudeSession(
        application_id=application_id,
        # public_token(B6)·AI 면접과 같은 근거 — 128비트라 추측으로 맞힐 수 없다
        token=secrets.token_urlsafe(16),
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(days=DEFAULT_EXPIRES_DAYS),
        created_by=user_id,
    )
    db.add(session)
    db.flush()
    return session


def _mail_log(
    db: Session,
    application: Application,
    posting: JobPosting,
    session: AptitudeSession,
    actor: User,
) -> int:
    """설문 링크 메일을 email_logs 에 queued 로 쌓는다. **커밋·발행은 호출부가.**

    문구는 mail._TEMPLATES 에 넣지 않았다 — 저긴 단계 메일이고 여긴 링크가
    필요해 변수 집합이 다르다. 본문을 행에 실어 두는 create_custom_log 경로가
    정확히 이 용도다 (보낸 그대로가 감사 기록으로 남는다).
    """
    kst = timezone(timedelta(hours=9))
    expires_str = (
        session.expires_at.astimezone(kst).strftime("%m월 %d일")
        if session.expires_at
        else "별도 안내"
    )
    signature = mail.build_signature(
        "custom", actor_kind="human", actor_name=actor.name
    )
    subject = f"[{mail.COMPANY_NAME}] {posting.title} 사전 성향 설문 요청"
    body = f"""{application.name} 님, 안녕하세요.

{mail.COMPANY_NAME} {posting.title} 포지션 지원과 관련해, 서류 검토에 참고할 사전 성향 설문을 요청드립니다.
문항은 {len(QUESTIONS)}개이며 3분 정도 걸립니다.

{_public_url(session.token)}

이 설문은 선택 사항이며, 응답하지 않으셔도 전형 진행에 불이익이 없습니다.
링크는 {expires_str}까지 유효합니다.

{signature}"""

    log = mail.create_custom_log(
        db,
        application_id=application.id,
        to_email=application.email,
        subject=subject,
        body=body,
        actor_kind="human",
        actor_id=actor.id,
    )
    return log.id


def _publish_all(log_ids: list[int]) -> None:
    """커밋 뒤 발행 — 실패해도 행은 queued 로 남는다 (emails.py 와 같은 처리)."""
    for log_id in log_ids:
        try:
            mail.publish(log_id)
        except Exception:
            logger.exception("설문 메일 큐 발행 실패 email_log_id=%s", log_id)


# ── 담당자용 ──────────────────────────────────────────────────────


@router.post("/postings/{posting_id}/aptitude/send", response_model=BulkSendOut)
def bulk_send(
    posting_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """공고 단위 일괄 발송 — "아직 안 받은 전원에게".

    한 번이라도 발송된 지원자는 건너뛴다(만료 재발송은 개별 버튼으로).
    accepted/rejected 등 지난 단계도 건너뛰고, **몇 건이 왜 빠졌는지 숫자로
    돌려준다** — 조용히 빼면 담당자가 빠진 사람을 찾을 방법이 없다.
    """
    posting = db.get(JobPosting, posting_id)
    if posting is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "공고를 찾을 수 없습니다")

    applications = db.scalars(
        select(Application).where(Application.job_posting_id == posting_id)
    ).all()
    already = set(
        db.scalars(
            select(AptitudeSession.application_id).where(
                AptitudeSession.application_id.in_(
                    [a.id for a in applications] or [0]
                )
            )
        )
    )

    sent, skipped_sent, skipped_stage = 0, 0, 0
    log_ids: list[int] = []
    for application in applications:
        if application.id in already:
            skipped_sent += 1
            continue
        if application.current_stage not in SENDABLE_STAGES:
            skipped_stage += 1
            continue
        session = _new_session(db, application.id, user.id)
        log_ids.append(_mail_log(db, application, posting, session, user))
        sent += 1

    db.commit()
    _publish_all(log_ids)
    return BulkSendOut(
        sent=sent, skipped_already_sent=skipped_sent, skipped_stage=skipped_stage
    )


@router.post(
    "/applications/{application_id}/aptitude/send",
    response_model=SessionOut,
    status_code=HTTPStatus.CREATED,
)
def send_one(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """개별 발송·재발송. **매번 새 행** — 옛 링크는 죽지 않는다 (AI 면접과 같은 철학).

    만료된 지원자에게 다시 보낼 때 이 경로를 쓴다. 단계 제한은 일괄 발송과
    같다 — 서류검토가 지난 지원자에게 보내는 것은 목적(ADR-0027)이 아니다.
    """
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")
    if application.current_stage not in SENDABLE_STAGES:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "접수·서류검토 단계에서만 발송할 수 있습니다",
        )
    posting = db.get(JobPosting, application.job_posting_id)

    session = _new_session(db, application.id, user.id)
    log_id = _mail_log(db, application, posting, session, user)
    db.commit()
    _publish_all([log_id])
    db.refresh(session)
    return _to_out(session)


@router.get(
    "/applications/{application_id}/aptitude", response_model=AptitudeDetailOut
)
def get_detail(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """지원자 상세 패널용 — 최신 세션의 응답·통계·요약.

    응답 원문과 통계를 요약과 나란히 준다. 요약이 원문을 왜곡하면 대조로
    드러나야 한다 (ADR-0027). 세션이 없으면 status='none' 뿐이다 —
    미응답 표시는 화면이 하고, 여기서 불이익 요소를 만들지 않는다.
    """
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    session = db.scalar(
        select(AptitudeSession)
        .where(AptitudeSession.application_id == application_id)
        .order_by(AptitudeSession.created_at.desc(), AptitudeSession.id.desc())
    )
    if session is None:
        return AptitudeDetailOut(status="none")

    _judge_expiry(db, session)

    answers = [AnswerOut.model_validate(a) for a in session.answers]
    stats = [CategoryStatOut(**s) for s in compute_stats(list(session.answers))]
    return AptitudeDetailOut(
        status=session.status,
        url=_public_url(session.token),
        expires_at=session.expires_at,
        submitted_at=session.submitted_at,
        answers=answers,
        stats=stats,
        ai_summary=session.ai_summary,
        ai_summary_model=session.ai_summary_model,
    )


# ── 공개 라우트 — 지원자용 (토큰 접근, 로그인 없음) ────────────────


def _judge_expiry(db: Session, session: AptitudeSession) -> None:
    """조회 시점 만료 판정 (B4·일정 제안·AI 면접과 같은 방식)."""
    now = datetime.now(timezone.utc)
    if (
        session.status == "pending"
        and session.expires_at is not None
        and session.expires_at <= now
    ):
        session.status = "expired"
        db.commit()


def _get_by_token(db: Session, token: str) -> AptitudeSession:
    session = db.scalar(select(AptitudeSession).where(AptitudeSession.token == token))
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "유효하지 않은 링크입니다")
    _judge_expiry(db, session)
    return session


@router.get("/public/aptitude/{token}", response_model=AptitudePublicOut)
def get_public(token: str, db: Session = Depends(get_db)):
    """지원자용 조회. 공개 — 토큰이 곧 인증이다.

    **담당자·평가·다른 지원자를 내려주지 않는다** (AI 면접과 같은 규칙).
    문항은 pending 일 때만 — 제출이 끝난 설문의 문항을 다시 보여 줄 이유가 없다.
    """
    session = _get_by_token(db, token)
    application = db.get(Application, session.application_id)
    posting = db.get(JobPosting, application.job_posting_id) if application else None

    questions: list[PublicQuestionOut] = []
    labels: dict[int, str] = {}
    if session.status == "pending":
        questions = [
            PublicQuestionOut(key=q["key"], text=q["text"]) for q in QUESTIONS
        ]
        labels = LIKERT_LABELS

    return AptitudePublicOut(
        status=session.status,
        applicant_name=application.name if application else "",
        posting_title=posting.title if posting else "",
        expires_at=session.expires_at,
        questions=questions,
        likert_labels=labels,
    )


@router.post("/public/aptitude/{token}/submit", response_model=AptitudePublicOut)
def submit(
    token: str,
    body: SubmitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """응답 제출. 공개. **전 문항 필수, 재제출 불가** — 다시 받으려면 재발송이다.

    문항 문구를 응답 시점 그대로 스냅샷해 둔다(question_text) — 상수가 나중에
    바뀌어도 지원자가 실제로 본 문장이 남는다. 저장이 끝나면 백그라운드로
    관찰 요약을 만든다 — 요약 실패는 제출 성공에 영향을 주지 않는다.
    """
    session = _get_by_token(db, token)

    if session.status == "expired":
        raise HTTPException(HTTPStatus.GONE, "링크 유효 기간이 지났습니다")
    if session.status != "pending":
        raise HTTPException(HTTPStatus.CONFLICT, "이미 제출된 설문입니다")

    keys = [a.key for a in body.answers]
    unknown = sorted(set(keys) - set(QUESTION_KEYS))
    missing = sorted(set(QUESTION_KEYS) - set(keys))
    if unknown or missing or len(keys) != len(set(keys)):
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            f"전 문항에 한 번씩 응답해야 합니다 (누락 {missing}, 알 수 없음 {unknown})",
        )

    for answer in body.answers:
        db.add(
            AptitudeAnswer(
                session_id=session.id,
                question_key=answer.key,
                question_text=QUESTIONS_BY_KEY[answer.key]["text"],
                value=answer.value,
            )
        )
    session.status = "done"
    session.submitted_at = datetime.now(timezone.utc)
    db.commit()

    background_tasks.add_task(generate_aptitude_summary_bg, session.id)
    return get_public(token, db)
