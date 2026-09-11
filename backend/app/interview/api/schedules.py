"""면접 일정 제안 API — 일정 자동화(ADR-0016)의 2단계.

배정된 면접관(E3)의 가용 시간에서 후보 슬롯을 뽑아 지원자에게 제안한다.
제안 생성은 사람(담당자)의 명시적 액션이다 — 시스템은 교집합 계산과
메일 왕복 제거만 한다. 지원자 쪽 조회·확정은 공개 라우트가 맡는다(3단계).
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared import mail
from app.db import get_db
from app.deps import get_current_user
from app.shared.labels import STAGE_LABEL_KR
from app.interview.schedule_service import NoCandidateSlots, build_proposal
from app.models import (
    Application,
    InterviewerAssignment,
    JobPosting,
    ScheduleProposal,
    ScheduleSlot,
    User,
)
from app.schemas.schedule import (
    ConfirmRequest,
    FaqRequest,
    FaqResponse,
    InterviewListOut,
    InterviewOut,
    ProposalCreate,
    ProposalOut,
    ProposalStatusOut,
    PublicSlotOut,
    SchedulePublicOut,
    SlotOut,
)
from app.adapter.outbound.pg.application_pg_repository import PgApplicationRepository
from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["schedules"])

PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "").rstrip("/")


@router.post(
    "/applications/{application_id}/schedule-proposals",
    response_model=ProposalOut,
    status_code=HTTPStatus.CREATED,
)
def create_proposal(
    application_id: int,
    body: ProposalCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """일정 제안 생성. 로그인한 사람이면 누구나 (ADR-0017).

    흐름: 배정 면접관의 가용 시간 → 후보 슬롯 → 제안 저장 → 제안 메일 큐 발행.
    재제안하면 기존 proposed 제안은 canceled 로 남는다(이력 보존, 라이브 제안은
    항상 최대 1건). 메일은 커밋 뒤에 발행한다 (mail.create_log 주석 참고).
    """
    application = PgApplicationRepository(db).get(application_id)
    if application is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    # 배정된 면접관(E3)이 재료다 — 없으면 슬롯을 만들 수 없다
    interviewer_ids = list(
        db.scalars(
            select(InterviewerAssignment.interviewer_id).where(
                InterviewerAssignment.application_id == application_id
            )
        )
    )
    if not interviewer_ids:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "배정된 면접관이 없습니다 — 먼저 면접관을 배정하세요 (E3)",
        )

    now = datetime.now(timezone.utc)

    try:
        proposal, slots, log = build_proposal(
            db, application, interviewer_ids,
            slot_minutes=body.slot_minutes, max_slots=body.max_slots,
            expires_at=body.expires_at, created_by=user.id,
            actor_kind="human", actor_id=user.id, now=now,
        )
    except NoCandidateSlots as e:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, str(e))
    db.commit()

    # 커밋 뒤 발행 — 큐가 죽어도 제안은 이미 성공이다. 행은 queued 로 남는다
    mail_queued = True
    try:
        mail.publish(log.id)
    except Exception:
        mail_queued = False
        logger.exception("제안 메일 큐 발행 실패 email_log_id=%s", log.id)

    # 담당자 화면 표시용 면접관 이름
    names = dict(
        db.execute(
            select(User.id, User.name).where(User.id.in_(interviewer_ids))
        ).all()
    )
    return ProposalOut(
        id=proposal.id,
        application_id=application_id,
        token=proposal.token,
        status=proposal.status,
        expires_at=proposal.expires_at,
        url=f"{PUBLIC_APP_BASE_URL}/schedule/{proposal.token}",
        slots=[
            SlotOut.model_validate(s).model_copy(
                update={"interviewer_name": names.get(s.interviewer_id)}
            )
            for s in slots
        ],
        mail_queued=mail_queued,
        created_at=proposal.created_at,
    )



@router.get(
    "/applications/{application_id}/schedule-proposals",
    response_model=ProposalStatusOut,
)
def get_latest_proposal(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이 지원자의 최신 일정 제안 상태. 대시보드·상세 패널의 칩 용도.

    조회는 로그인한 사람 전체에게 열려 있다 (ADR-0017).
    제안이 하나도 없으면 404 — 화면은 "일정 없음"으로 그린다.
    """
    if PgApplicationRepository(db).get(application_id) is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")

    proposal = db.scalar(
        select(ScheduleProposal)
        .where(ScheduleProposal.application_id == application_id)
        .order_by(ScheduleProposal.created_at.desc())
        .limit(1)
    )
    if proposal is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "일정 제안이 없습니다")

    # 조회 시점 만료 판정 — 공개 라우트와 같은 규칙 (스케줄러 없음)
    now = datetime.now(timezone.utc)
    if (
        proposal.status == "proposed"
        and proposal.expires_at is not None
        and proposal.expires_at <= now
    ):
        proposal.status = "expired"
        proposal.updated_at = now
        db.commit()

    confirmed_slot = None
    if proposal.status == "confirmed" and proposal.confirmed_slot_id is not None:
        confirmed_slot = db.get(ScheduleSlot, proposal.confirmed_slot_id)

    return ProposalStatusOut(
        status=proposal.status,
        confirmed_slot=(
            PublicSlotOut.model_validate(confirmed_slot) if confirmed_slot else None
        ),
        expires_at=proposal.expires_at,
        created_at=proposal.created_at,
    )


@router.get("/schedules", response_model=InterviewListOut)
def list_confirmed_interviews(
    from_at: datetime | None = Query(None, alias="from", description="이 시각 이후 시작분만"),
    to_at: datetime | None = Query(None, alias="to", description="이 시각 이전 시작분만"),
    mine: bool = Query(False, description="내가 면접관인 건만"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """확정된 면접 목록 (ADR-0016). 면접 일정 화면의 데이터 소스.

    역할 분기가 없다 — 로그인한 사람은 전체를 보고, mine=true 로 자기가
    면접관인 건만 좁힌다 (ADR-0017). 좁히는 것은 이제 필터이지 권한이 아니다.
    """
    query = (
        select(ScheduleSlot, Application, JobPosting, User)
        .join(ScheduleProposal, ScheduleProposal.confirmed_slot_id == ScheduleSlot.id)
        .join(Application, Application.id == ScheduleProposal.application_id)
        .join(JobPosting, JobPosting.id == Application.job_posting_id)
        .join(User, User.id == ScheduleSlot.interviewer_id)
        .where(ScheduleProposal.status == "confirmed")
        .order_by(ScheduleSlot.start_at)
    )
    if from_at is not None:
        query = query.where(ScheduleSlot.start_at >= from_at)
    if to_at is not None:
        query = query.where(ScheduleSlot.start_at < to_at)
    if mine:
        query = query.where(ScheduleSlot.interviewer_id == user.id)

    rows = db.execute(query).all()
    items = [
        InterviewOut(
            proposal_id=slot.proposal_id,
            application_id=application.id,
            applicant_name=application.name,
            posting_title=posting.title,
            interviewer_id=interviewer.id,
            interviewer_name=interviewer.name,
            start_at=slot.start_at,
            end_at=slot.end_at,
        )
        for slot, application, posting, interviewer in rows
    ]
    return InterviewListOut(items=items, count=len(items))

# ── 공개 라우트 — 지원자용 (토큰 접근, 로그인 없음) ──────────────────
#
# 공고 쪽 공개 경로는 api/public.py 에 있지만, 일정 로직은 이 파일에 모은다 —
# 제안 생성과 확정이 같은 규칙(겹침 검증·상태 전이)을 공유하기 때문이다.


def _get_proposal_by_token(db: Session, token: str) -> ScheduleProposal:
    """토큰으로 제안을 찾고 조회 시점 판정을 한다 (B4 마감과 같은 방식).

    - 없는 토큰 → 404
    - canceled(재제안으로 대체된 옛 링크) → 410 Gone. 새 링크가 메일로 나갔다 —
      "있었지만 끝났다"를 알려야 지원자가 옛 메일을 붙잡고 헤매지 않는다.
    - proposed 인데 기한이 지남 → expired 로 바꿔 저장 (스케줄러 없음)
    """
    proposal = db.scalar(
        select(ScheduleProposal).where(ScheduleProposal.token == token)
    )
    if proposal is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "유효하지 않은 링크입니다")
    if proposal.status == "canceled":
        raise HTTPException(
            HTTPStatus.GONE, "이 일정 제안은 더 이상 유효하지 않습니다 — 최신 안내 메일을 확인해 주세요"
        )

    now = datetime.now(timezone.utc)
    if (
        proposal.status == "proposed"
        and proposal.expires_at is not None
        and proposal.expires_at <= now
    ):
        proposal.status = "expired"
        proposal.updated_at = now
        db.commit()

    return proposal


@router.get("/public/schedule/{token}", response_model=SchedulePublicOut)
def get_schedule_public(token: str, db: Session = Depends(get_db)):
    """지원자용 일정·전형 현황 조회. 공개 — 토큰이 곧 인증이다.

    expired 도 200 으로 내려준다 — 지원자가 "기한이 지났다"와 자기 전형 현황을
    봐야 하기 때문이다(빈 화면보다 낫다). confirmed 는 확정 시각 재확인 용도로
    링크가 계속 살아 있다 — "24시간 언제든 확인"이 이 기능의 요지다.
    """
    proposal = _get_proposal_by_token(db, token)
    application = PgApplicationRepository(db).get(proposal.application_id)
    posting = PgHiringRepository(db).get_posting(application.job_posting_id)

    confirmed_slot = None
    if proposal.status == "confirmed" and proposal.confirmed_slot_id is not None:
        confirmed_slot = db.get(ScheduleSlot, proposal.confirmed_slot_id)

    return SchedulePublicOut(
        status=proposal.status,
        applicant_name=application.name,
        posting_title=posting.title if posting else "",
        current_stage=application.current_stage,
        expires_at=proposal.expires_at,
        slots=[
            PublicSlotOut.model_validate(s)
            for s in sorted(proposal.slots, key=lambda s: s.start_at)
        ],
        confirmed_slot=(
            PublicSlotOut.model_validate(confirmed_slot) if confirmed_slot else None
        ),
    )


@router.post("/public/schedule/{token}/confirm", response_model=SchedulePublicOut)
def confirm_schedule(token: str, body: ConfirmRequest, db: Session = Depends(get_db)):
    """슬롯 선택 → 즉시 확정. 공개.

    지원자의 슬롯 선택은 지원자 본인의 결정이므로 담당자 승인 없이 즉시 확정이다
    (ADR-0016). 확정 통보 메일은 워커가 confirmed 상태를 보고 확정 시각을 싣는다.
    """
    proposal = _get_proposal_by_token(db, token)

    # 같은 제안에 확정이 두 번 붙는 것을 막는다 — 더블클릭·중복 탭이 정상 사용이다
    db.refresh(proposal, with_for_update=True)

    if proposal.status == "confirmed":
        raise HTTPException(HTTPStatus.CONFLICT, "이미 확정된 일정입니다")
    if proposal.status == "expired":
        raise HTTPException(
            HTTPStatus.CONFLICT, "선택 기한이 지났습니다 — 담당자에게 문의해 주세요"
        )

    slot = db.get(ScheduleSlot, body.slot_id)
    if slot is None or slot.proposal_id != proposal.id:
        raise HTTPException(HTTPStatus.NOT_FOUND, "슬롯을 찾을 수 없습니다")

    # 확정 시점 겹침 재검증 — 제안이 나간 뒤 같은 면접관의 다른 면접이 먼저
    # 확정됐을 수 있다 (슬롯은 생성 시점 스냅샷이다, models.py 참고)
    clash = db.scalar(
        select(ScheduleSlot.id)
        .join(ScheduleProposal, ScheduleProposal.confirmed_slot_id == ScheduleSlot.id)
        .where(ScheduleProposal.status == "confirmed")
        .where(ScheduleSlot.interviewer_id == slot.interviewer_id)
        .where(ScheduleSlot.start_at < slot.end_at)
        .where(ScheduleSlot.end_at > slot.start_at)
        .limit(1)
    )
    if clash is not None:
        raise HTTPException(
            HTTPStatus.CONFLICT,
            "그 사이 마감된 시간입니다 — 다른 시간을 선택해 주세요",
        )

    now = datetime.now(timezone.utc)
    proposal.status = "confirmed"
    proposal.confirmed_slot_id = slot.id
    proposal.updated_at = now

    application = PgApplicationRepository(db).get(proposal.application_id)
    # 확정 통보 — 워커가 confirmed 를 보고 {면접일시}에 확정 시각(KST)을 싣는다.
    # 주체는 system 이다(기본값): 이 발송을 일으킨 것은 지원자 본인의 선택이고,
    # 담당자도 아르도 개입하지 않았다. 담당자 이름으로 서명하면 거짓이다 (G4).
    log = mail.create_log(
        db,
        application_id=application.id,
        to_email=application.email,
        stage="interview",
    )
    db.commit()
    try:
        mail.publish(log.id)
    except Exception:
        # 확정은 이미 저장됐다 — 메일이 늦는 것이 확정을 무르는 것보다 낫다
        logger.exception("확정 통보 메일 큐 발행 실패 email_log_id=%s", log.id)

    posting = PgHiringRepository(db).get_posting(application.job_posting_id)
    return SchedulePublicOut(
        status="confirmed",
        applicant_name=application.name,
        posting_title=posting.title if posting else "",
        current_stage=application.current_stage,
        expires_at=proposal.expires_at,
        slots=[
            PublicSlotOut.model_validate(s)
            for s in sorted(proposal.slots, key=lambda s: s.start_at)
        ],
        confirmed_slot=PublicSlotOut.model_validate(slot),
    )


@router.post("/public/schedule/{token}/faq", response_model=FaqResponse)
def public_faq(token: str, body: FaqRequest, db: Session = Depends(get_db)):
    """지원자용 아르 채팅 — 공고 내용 기반 FAQ 응답 (공개, 토큰 인증).

    담당자용 아르(POST /agent/chat)와는 완전히 별개다:
    - 도구 없음, 대화 이력 없음, stateless — 한 번의 질문 → 한 번의 답변
    - 답변 범위·차단 주제는 프롬프트(faq_answer.v1.md)가 정한다
      (연봉·평가·다른 지원자·회사 내부 프로세스는 답하지 않는다)

    invalid/replaced 링크는 여기서도 막는다 — 만료된 링크로 챗봇만 계속 쓰지
    못하게. expired 는 통과시킨다 (지원자가 상태 확인을 위해 페이지에 남아 있고,
    아직 공고 자체에는 지원자다).
    """
    from app.agent.faq import answer_question

    proposal = _get_proposal_by_token(db, token)
    application = PgApplicationRepository(db).get(proposal.application_id)
    posting = PgHiringRepository(db).get_posting(application.job_posting_id) if application else None
    if posting is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "공고를 찾을 수 없습니다")

    try:
        answer, _cost, _model = answer_question(
            posting,
            body.question,
            applicant_context=_build_applicant_context(db, application, proposal),
        )
    except Exception:
        # 백엔드 미설정·모델 오류 등. 지원자에게 원문 노출은 하지 않고 안내로 감싼다.
        logger.exception("FAQ 응답 생성 실패 posting_id=%s", posting.id)
        raise HTTPException(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "지금 답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.",
        )

    return FaqResponse(answer=answer)


def _kst(dt: datetime) -> str:
    """UTC 저장값을 지원자가 보는 한국 시각 표기로 (YYYY.MM.DD (요일) HH:MM)."""
    kst = dt.astimezone(timezone(timedelta(hours=9)))
    day_kr = "월화수목금토일"[kst.weekday()]
    return f"{kst.strftime('%Y.%m.%d')} ({day_kr}) {kst.strftime('%H:%M')}"


def _build_applicant_context(
    db: Session, application: Application, proposal: ScheduleProposal
) -> str:
    """지원자 본인의 상태를 자연어 요약으로 — 아르가 개인 문의에 답할 근거.

    화면(SchedulePublicOut)에 뜨는 것과 같은 사실만 담는다. 담당자만 아는 것
    (평가·메모·다른 지원자)은 절대 포함하지 않는다.
    """
    lines = [f"- 현재 전형 단계: {STAGE_LABEL_KR.get(application.current_stage, application.current_stage)}"]

    if proposal.status == "confirmed" and proposal.confirmed_slot_id is not None:
        slot = db.get(ScheduleSlot, proposal.confirmed_slot_id)
        if slot is not None:
            lines.append(f"- 다음 일정: 면접 확정 — {_kst(slot.start_at)} ~ {_kst(slot.end_at)[-5:]}")
    elif proposal.status == "proposed":
        lines.append("- 다음 일정: 면접 시간 선택 대기 중 (지원자가 이 페이지에서 슬롯을 선택하면 확정)")
        if proposal.expires_at is not None:
            lines.append(f"- 선택 기한: {_kst(proposal.expires_at)} 까지")
    elif proposal.status == "expired":
        lines.append("- 다음 일정: 면접 선택 기한 지남 — 담당자에게 문의해야 재제안 가능")

    return "\n".join(lines)
