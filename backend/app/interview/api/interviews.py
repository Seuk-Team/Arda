"""AI 면접 API — 세션 생성과 지원자 공개 접근 (ADR-0026).

설계는 docs/02_tasks/AI면접-설계.md §5 의 2·3번.

지원자는 로그인이 없으므로 일정 제안(ADR-0016)과 **같은 토큰 공개 접근 패턴**을 쓴다.
만료도 같은 방식이다 — 스케줄러 없이 조회 시점에 판정한다(B4 마감과 동일).

**질문은 아직 자동 생성하지 않는다.** 설계 §5 의 5번에서 붙인다. 그때까지는
담당자가 넣은 질문 목록으로 돈다 — 그래야 뼈대가 먼저 관통된다.
"""

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared import mail, s3
from app.interview import lie_analysis, pacing as interview_pacing

# 방 저장소(`_ROOMS`)가 RTC 라우터에 있어 여기서 가져온다 — 세션을 지울 때 그 방을
# 닫아야 하기 때문이다. 라우터→라우터 import 라 좋은 모양은 아니고, 방 저장소를
# `interview/rtc_service.py` 로 옮기는 것이 다음 정리 대상이다 (2026-09-12 감사).
from app.interview.api.interview_rtc import close_room_from_thread
from app.shared.api.files import _extract_ext, validate_audio_upload
from app.shared.s3 import EXPIRES_IN
from app.db import get_db
from app.deps import get_current_user
from app.hiring.company import name_for
from app.models import (
    Application,
    InterviewSession,
    InterviewTurn,
    JobPosting,
    User,
)
from app.schemas.interview import (
    ActiveSessionOut,
    AnswerRequest,
    AudioUploadRequest,
    AudioUploadResponse,
    ConsentRequest,
    InterviewPublicOut,
    PacingHintOut,
    QuestionsSet,
    RetranscribeOut,
    SessionCreate,
    SessionDetailOut,
    SessionOut,
)
from app.adapter.outbound.pg.application_pg_repository import PgApplicationRepository
from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository
from app.adapter.outbound.pg.interview_pg_repository import PgInterviewRepository

router = APIRouter(prefix="/api/v1", tags=["interviews"])

logger = logging.getLogger(__name__)

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


# 앱 내려받는 곳. **비어 있으면 메일에서 그 줄을 뺀다** — 없는 주소를 적어 두면
# 지원자가 눌러 보고 막힌다. 스토어에 올리기 전까지는 비워 둔다 (2026-09-18).
APP_DOWNLOAD_URL = os.getenv("APP_DOWNLOAD_URL", "").strip()


def queue_interview_mail(
    db: Session,
    application: Application,
    posting: JobPosting,
    session: InterviewSession,
    *,
    actor_kind: str,
    actor_name: str | None,
    actor_id: int | None,
) -> int:
    """AI 면접 링크 메일을 `email_logs` 에 queued 로 쌓는다. **커밋·발행은 호출부가.**

    2026-09-18 신설. 전에는 링크가 메일로 나가지 않아 담당자가 「링크 복사」로 따로
    전달해야 했다 — 인적성 설문은 자동으로 나가는데 면접만 손으로 나가고 있었다.

    문구는 `mail._TEMPLATES` 가 아니라 본문을 행에 실어 두는 `create_custom_log` 로
    간다 — 설문 메일과 같은 이유다(링크가 있어 변수 집합이 다르고, 보낸 그대로가
    감사 기록으로 남는다).

    **웹 링크를 먼저 준다.** 앱을 깔지 않아도 그 링크로 바로 면접을 볼 수 있고, 앱을
    쓰는 지원자는 이메일·생년월일로 로그인하면 같은 면접이 목록에 뜬다.
    """
    kst = timezone(timedelta(hours=9))
    expires_str = (
        session.expires_at.astimezone(kst).strftime("%m월 %d일 %H시")
        if session.expires_at
        else "별도 안내"
    )
    # 회사명은 DB(company_profile) 가 먼저다 — 환경변수를 바로 읽으면 같은 지원자에게
    # 단계 메일은 [코드브릿지], 이 메일만 [Seuk] 로 간다 (#323 이 설문·수동 메일에서
    # 고친 것과 같은 자리. 면접 링크 메일은 그 뒤에 들어와 빠져 있었다).
    company_name = name_for(db)
    signature = mail.build_signature(
        "custom", actor_kind=actor_kind, actor_name=actor_name, company_name=company_name
    )
    subject = f"[{company_name}] {posting.title} AI 면접 안내"
    app_line = (
        f"앱으로 보시려면: {APP_DOWNLOAD_URL} 에서 앱을 내려받아 "
        "이메일과 생년월일로 로그인하시면 같은 면접이 목록에 있습니다.\n"
        if APP_DOWNLOAD_URL
        else "앱을 이미 설치하셨다면 이메일과 생년월일로 로그인해 「면접」 탭에서도 같은 면접을 보실 수 있습니다.\n"
    )
    body = f"""{application.name} 님, 안녕하세요.

{company_name} {posting.title} 포지션 지원과 관련해 AI 면접을 안내드립니다.
아래 링크를 열어 안내에 따라 진행해 주세요. 카메라와 마이크를 사용합니다.

{_public_url(session.token)}

{app_line}
조용한 곳에서 얼굴이 잘 보이게 앉아 주시고, 질문마다 답변이 끝나면 [답변 완료]를 눌러 주세요.
링크는 {expires_str}까지 유효합니다.

{signature}"""

    log = mail.create_custom_log(
        db,
        application_id=application.id,
        to_email=application.email,
        subject=subject,
        body=body,
        actor_kind=actor_kind,
        actor_id=actor_id,
    )
    return log.id


def _publish_mail(log_id: int) -> None:
    """커밋 뒤 발행 — 실패해도 행은 queued 로 남는다 (aptitude._publish_all 과 같은 처리)."""
    try:
        mail.publish(log_id)
    except Exception:
        logger.exception("면접 링크 메일 발행 실패 email_log_id=%s", log_id)


def _send_interview_mail(
    db: Session, session: InterviewSession, user: User
) -> int | None:
    """링크 메일을 쌓고 id 를 돌려준다. 지원자·공고를 못 찾으면 None(면접은 그대로)."""
    application = PgApplicationRepository(db).get(session.application_id)
    if application is None:
        return None
    posting = PgHiringRepository(db).get_posting(application.job_posting_id)
    if posting is None:
        return None
    return queue_interview_mail(
        db, application, posting, session,
        actor_kind="human", actor_name=user.name, actor_id=user.id,
    )


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


# 세션 라이프사이클 도메인 서비스 (ADR-0035 Phase 4). 옛 이름은 별칭으로 유지 —
# 테스트가 `app.interview.api.interviews._generate_followup_bg` 를 patch 하는 것이
# 있어서 지금 지우면 깨진다. 새 테스트는 `session_service` 쪽으로.
from app.interview.session_service import (
    LATE_ANSWER_GRACE,
    add_default_questions as _add_default_questions,
    generate_followup_bg as _generate_followup_bg,
    remember_audio_key as _remember_audio_key,
    retranscribe_session as _retranscribe_session,
    seed_questions_bg as _seed_questions_bg,
    transcribe_answer as _transcribe_answer,
)


@router.post(
    "/applications/{application_id}/interview-sessions",
    response_model=SessionOut,
    status_code=HTTPStatus.CREATED,
)
def create_session(
    application_id: int,
    body: SessionCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """AI 면접 세션 생성 + 공개 링크 발급.

    **재생성하지 않고 매번 새 행을 만든다.** 옛 세션은 그대로 남는다 —
    이력이 사라지지 않는 편이 낫다(stage_history·schedule_proposals 와 같은 철학).
    그래서 링크를 다시 뽑아도 **이전 링크가 죽지 않는다** — 공고 public-link 와 다른 점이다.

    **질문은 뒤에서 자동으로 뽑는다** (2026-09-10, 팀장 결정). 자기소개서·이력서에서
    꼬리 질문 최대 4개. 담당자는 여전히 편집기로 덮어쓸 수 있다.

    **폴백 3개는 세션과 같은 커밋에 먼저 넣는다** (2026-09-17). 만들자마자
    「시작」 해도 422 가 나지 않는다 — 그 면접은 폴백으로 진행되고, 아직 시작 전이면
    뒤의 생성이 맞춤 질문으로 바꿔 넣는다(`seed_questions_bg`).

    **링크 메일이 같이 나간다** (2026-09-18, 팀 논의). 인적성 설문은 자동으로 나가는데
    면접 링크만 담당자가 「링크 복사」로 손수 전달하고 있었다. 메일 없이 링크만 뽑고
    싶으면 `notify: false` — 그때는 화면의 「메일 보내기」로 나중에 보낸다.
    """
    application = PgApplicationRepository(db).get(application_id)
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
    db.flush()
    _add_default_questions(db, session.id)
    log_id = _send_interview_mail(db, session, user) if body.notify else None
    db.commit()
    db.refresh(session)

    # 발행은 커밋 뒤에 — 실패해도 행은 queued 로 남아 나중에 쓸어 담긴다(mail_smtp).
    if log_id is not None:
        _publish_mail(log_id)

    # 자동 질문 생성 — 백그라운드로. 담당자를 응답 앞에 세워 두지 않는다.
    background.add_task(_seed_questions_bg, session.id)

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


@router.post(
    "/interview-sessions/{session_id}/send",
    response_model=SessionOut,
    status_code=HTTPStatus.CREATED,
)
def send_interview_link(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """링크 메일을 (다시) 보낸다 — **같은 세션·같은 링크** (2026-09-18).

    설문(`aptitude/send`)은 보낼 때마다 새 세션을 만들지만 면접은 그러면 안 된다:
    앱이 끝나지 않은 세션 중 **가장 먼저 만든 것**으로 들어가므로, 재발송마다 방이
    하나씩 늘면 담당자와 지원자가 다른 방을 본다(2026-09-10 실측). 그래서 여기서는
    메일만 다시 쌓는다 — 옛 메일의 링크도 그대로 살아 있다.

    끝난 면접(410 은 만료)은 보내 봐야 들어갈 수 없으므로 막는다.
    """
    session = PgInterviewRepository(db).get_session(session_id)
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "면접을 찾을 수 없습니다")
    if session.expires_at is not None and session.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(HTTPStatus.GONE, "링크 유효 기간이 지났습니다 — 새로 만들어 주세요")
    if session.status in ("done", "expired"):
        raise HTTPException(HTTPStatus.CONFLICT, "이미 끝난 면접입니다 — 새로 만들어 주세요")

    log_id = _send_interview_mail(db, session, user)
    if log_id is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자 또는 공고를 찾을 수 없습니다")
    db.commit()
    _publish_mail(log_id)
    db.refresh(session)
    return _to_out(session)


@router.delete(
    "/interview-sessions/{session_id}", status_code=HTTPStatus.NO_CONTENT
)
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """세션 하나를 지운다. **끝난 것도 지울 수 있다.**

    담당자가 옛 세션 (잘못 만든 것 · 시연 리허설용 · 만들어 두고 안 쓴 것) 을 지울
    자리 (2026-09-10, 팀장 요청). 자식 표 (interview_turns · interview_findings) 는
    수동 CASCADE — FK 에 ondelete 를 안 걸어 뒀기 때문이다.

    **`in_progress` 는 허용한다.** 오늘 사고 났던 세션(23 스타일) 도 지울 수 있어야
    담당자 UI 로 정리할 수 있다. 지원자가 그 순간에 접속 중이었어도 방을 닫힐
    뿐이라 되돌릴 수 없는 손해는 없다.
    """
    from app.models import InterviewFinding

    session = PgInterviewRepository(db).get_session(session_id)
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "면접 세션을 찾을 수 없습니다")

    # 자식 먼저 — FK ondelete 가 없어 순서를 지켜야 한다
    db.execute(
        InterviewFinding.__table__.delete().where(
            InterviewFinding.session_id == session_id
        )
    )
    db.execute(
        InterviewTurn.__table__.delete().where(
            InterviewTurn.session_id == session_id
        )
    )
    token = session.token
    db.delete(session)
    db.commit()

    # **붙어 있던 방을 실제로 닫는다** (2026-09-12). 위 독스트링이 오래전부터
    # "방이 닫힐 뿐" 이라고 적어 뒀는데 닫는 코드가 없었다 — 지운 세션의 방에
    # 담당자가 그대로 앉아 있었고, 지원자는 새로 만든 세션의 방으로 들어가
    # 서로를 못 봤다 (09-12 시연 테스트에서 실제로 그랬다). 방 키가 세션
    # 토큰이라 두 방은 완전히 별개다.
    #
    # 실패해도 삭제는 이미 끝났다 — 방이 없으면 그냥 False 다.
    #
    # TODO: `_ROOMS` 는 RTC 라우터 안에 있어 라우터→라우터 import 가 된다.
    # 방 저장소를 `interview/rtc_service.py` 로 옮기는 것이 다음 정리 대상이다.
    close_room_from_thread(
        token,
        code="session_deleted",
        message="이 면접 세션이 삭제됐습니다. 목록에서 새 세션을 만들어 주세요",
    )


@router.post(
    "/interview-sessions/{session_id}/retranscribe", response_model=RetranscribeOut
)
def retranscribe_answers(
    session_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """답이 비어 있거나 `[전사 …]` 로 남은 회차를 음성으로 다시 채운다. **담당자용.**

    2026-09-15 세션 75 에서 전사가 상한(180초)을 넘겨 답변이 `[전사 지연 · 발화
    43.9초]` 로 저장됐다. 지원자는 화면이 안 넘어가니 [답변 완료] 를 연타했고 뒤
    문항까지 빈 답변으로 소진됐다 ([ADR-0038](../../../docs/03_decision/0038-실시간-전사-OpenAI-API.md)).
    **전사 속도는 그 ADR 로 풀렸지만 이미 빈 채로 남은 답변을 되살릴 길이 없었다.**
    이 경로가 그 길이다.

    **멀쩡한 답변은 건드리지 않는다** — 몇 번을 눌러도 안전하고, 실패한 회차만
    다시 시도한다. 되살릴 수 있는 것은 음성이 S3 에 남은 회차뿐이라 그렇지 않은
    회차는 `no_audio` 로 그대로 돌려준다 (실시간 소켓 경로가 그렇다).

    하나라도 채워지면 **채점과 서류 대조를 다시 돌린다** — 빈 답변으로 매긴 점수가
    그대로 남으면 담당자가 그 점수를 보고 판단한다.
    """
    session = db.get(InterviewSession, session_id)
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "면접 세션을 찾을 수 없습니다")

    result = _retranscribe_session(db, session_id)

    if result["filled"]:
        from app.agent.interview_findings import generate_turn_findings_bg
        from app.interview.scoring import score_interview_bg

        background.add_task(score_interview_bg, session.id)
        for turn in db.scalars(
            select(InterviewTurn).where(
                InterviewTurn.session_id == session.id,
                InterviewTurn.seq.in_(result["filled"]),
            )
        ).all():
            background.add_task(generate_turn_findings_bg, session.id, turn.id)

    return RetranscribeOut(**result)


@router.post("/interview-turns/{turn_id}/analyze")
def analyze_turn(
    turn_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이 회차의 녹화를 진위 분석 서비스에 넘긴다 (ADR-0029). **담당자용.**

    **설정이 없으면 503 이다.** `LIE_SERVICE_URL` 을 안 넣으면 이 기능은 꺼져
    있다 — ADR-0029 결정 5 가 "「정하지 못한 것」 ①②③ 이 정해지기 전에는 운영에
    붙이지 않는다"고 정했다. 체인이 `CHAIN_RPC_URL` 없이 꺼져 있는 것과 같다.

    **결과를 저장하지 않는다.** 담을 표를 아직 정하지 않았고(ADR-0029 「결과」),
    스키마가 정해지기 전에 값이 쌓이면 그 값이 근거처럼 쓰이기 시작한다.

    지원자가 영상으로 답했을 때만 쓸 수 있다 — 음성만 있는 회차는 분석할 얼굴이
    없어서 서비스가 `{"error": ...}` 를 돌려준다.
    """
    reason = lie_analysis.unavailable_reason()
    if reason:
        raise HTTPException(
            HTTPStatus.SERVICE_UNAVAILABLE, f"진위 분석을 쓸 수 없습니다: {reason}"
        )

    turn = db.get(InterviewTurn, turn_id)
    if turn is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "면접 회차를 찾을 수 없습니다")
    if not turn.audio_s3_key:
        raise HTTPException(
            HTTPStatus.CONFLICT, "이 회차에는 녹화가 없습니다"
        )

    try:
        blob = s3.read_object(turn.audio_s3_key)
    except Exception as exc:
        raise HTTPException(
            HTTPStatus.BAD_GATEWAY, f"녹화를 읽지 못했습니다 ({type(exc).__name__})"
        )

    try:
        return lie_analysis.analyze(blob, filename=turn.audio_s3_key.rsplit("/", 1)[-1])
    except Exception as exc:
        raise HTTPException(
            HTTPStatus.BAD_GATEWAY, f"분석하지 못했습니다 ({type(exc).__name__})"
        )


@router.get("/interview-sessions/active", response_model=list[ActiveSessionOut])
def list_active_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """지금 진행 중인 면접들. **대시보드가 바로 들어가는 데 쓴다.**

    이게 없으면 담당자는 지원자 목록 → 상세 → 세션 → 링크 넷을 거쳐야 실시간
    분석 화면에 닿는다. 면접이 시작되는 순간에 그걸 찾아 들어갈 수는 없다.

    **`in_progress` 만 낸다.** 아직 시작 안 한 것(pending)은 지금 볼 것이 없고,
    끝난 것은 들어가도 방이 안 열린다(`session_closed`).

    이 경로는 `/interview-sessions/{session_id}` **위에 둔다** — 아래 두면
    `active` 가 session_id 로 읽혀 422 가 난다.
    """
    rows = db.scalars(
        select(InterviewSession)
        .where(InterviewSession.status == "in_progress")
        .order_by(InterviewSession.started_at.desc())
    ).all()
    if not rows:
        return []

    apps = {
        a.id: a
        for a in db.scalars(
            select(Application).where(
                Application.id.in_([r.application_id for r in rows])
            )
        ).all()
    }
    titles = {
        p.id: p.title
        for p in db.scalars(
            select(JobPosting).where(
                JobPosting.id.in_({a.job_posting_id for a in apps.values()})
            )
        ).all()
    }
    return [
        ActiveSessionOut(
            id=r.id,
            application_id=r.application_id,
            applicant_name=apps[r.application_id].name if r.application_id in apps else "",
            posting_title=titles.get(
                apps[r.application_id].job_posting_id if r.application_id in apps else 0,
                "",
            ),
            started_at=r.started_at,
        )
        for r in rows
    ]


@router.get("/interview-sessions/{session_id}", response_model=SessionDetailOut)
def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """전사와 대조 결과까지 포함한 상세."""
    from app.agent.interview_findings import findings_on

    session = PgInterviewRepository(db).get_session(session_id)
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "면접 세션을 찾을 수 없습니다")

    base = _to_out(session)
    return SessionDetailOut(
        **base.model_dump(),
        turns=sorted(session.turns, key=lambda t: t.seq),
        findings=sorted(session.findings, key=lambda f: f.id),
        findings_enabled=findings_on(),
        # 2026-09-14: 종합 평가 상세 페이지가 이 필드를 쓰는데 옛 응답에는 빠져 있었다
        # — 스키마에는 있고 DB 에는 값이 있는데 응답에서 누락돼 "장점·우려 없음" 으로만 뜸.
        ai_score=session.ai_score,
        ai_score_detail=session.ai_score_detail,
        scored_at=session.scored_at,
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
    application = PgApplicationRepository(db).get(session.application_id)
    posting = PgHiringRepository(db).get_posting(application.job_posting_id) if application else None

    current = None
    if session.status == "in_progress":
        # **아직 답 안 한 가장 앞 질문**이 현재 질문이다.
        # 마지막 질문을 보면 안 된다 — 3개 중 1번만 답했을 때 2번이 아니라
        # 3번을 내주게 된다. 답변 저장(submit_answer)도 같은 규칙을 쓴다.
        #
        # **"답 안 한" 은 `answered_at` 도 전사도 없는 칸이다** (0018, 2026-09-11).
        # 전사만 보던 때는 전사가 몇 분씩 늦게 채워져서, 그 사이 재접속·확인 요청이
        # 지원자를 이미 답한 질문으로 되돌렸다. 전사도 같이 보는 이유는 `answered_at`
        # 을 안 찍고 전사만 넣는 경로가 있어도 그 칸을 다시 묻지 않게 하려는 것이다.
        current = db.scalar(
            select(InterviewTurn)
            .where(
                InterviewTurn.session_id == session.id,
                InterviewTurn.answered_at.is_(None),
                InterviewTurn.transcript.is_(None),
            )
            .order_by(InterviewTurn.seq)
        )

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
    # 뒤에서 폴백을 맞춤 질문으로 바꾸는 작업(`seed_questions_bg`)과 겹치지 않게
    # 같은 행을 잠그고 다시 읽는다 — 바꾸는 중이면 끝난 뒤의 질문으로 시작한다.
    db.refresh(session, with_for_update=True)

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


@router.put(
    "/interview-sessions/{session_id}/questions",
    response_model=SessionDetailOut,
)
def set_questions(
    session_id: int,
    body: QuestionsSet,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """질문 목록을 넣는다. **시작 전에만** 바꿀 수 있다.

    진행 중에 질문이 바뀌면 지원자가 본 질문과 저장된 질문이 어긋난다 —
    나중에 전사를 읽는 사람이 "이 답이 어느 질문에 대한 것인가"를 알 수 없게 된다.

    설계 §5 의 5번(요약에서 자동 생성)이 붙어도 이 경로는 남는다 — 담당자가
    고쳐 넣을 수 있어야 한다.
    """
    session = PgInterviewRepository(db).get_session(session_id)
    if session is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "면접 세션을 찾을 수 없습니다")
    if session.status != "pending":
        raise HTTPException(
            HTTPStatus.CONFLICT, "이미 시작한 면접의 질문은 바꿀 수 없습니다"
        )

    for turn in list(session.turns):
        db.delete(turn)
    db.flush()

    for i, q in enumerate(body.questions, start=1):
        db.add(InterviewTurn(session_id=session.id, seq=i, question=q))
    db.commit()
    db.refresh(session)

    return get_session(session_id, db, user)


@router.post(
    "/public/interview/{token}/audio-upload-url",
    response_model=AudioUploadResponse,
)
def presign_answer_audio(
    token: str, body: AudioUploadRequest, db: Session = Depends(get_db)
):
    """답변 음성 업로드 URL 발급 (설계 §5-4). **공개** — 면접 토큰이 곧 인증이다.

    **이력서 업로드와 경로를 나눈 이유**: `/public/files/presign-upload` 는
    토큰 없이 누구나 부를 수 있다. 거기에 음성 형식을 허용하면 아무나 우리
    버킷에 미디어를 올릴 수 있게 된다. 여기는 **진행 중인 면접**이어야 발급된다.

    **키는 서버가 만든다.** 클라이언트가 경로를 고르면 서명이 곧 임의 위치 쓰기
    권한이 된다 — 이력서 쪽(`files._build_key`)과 같은 이유다.

    면접 음성이라 `applications/…` 밑에 두지 않는다. 지원서 첨부(`files` 행)가
    아니라 면접 회차에 붙는 것이고, 보관 기간·삭제 규칙이 달라질 자리다.
    """
    session = _get_by_token(db, token)

    if session.status == "expired":
        raise HTTPException(HTTPStatus.GONE, "링크 유효 기간이 지났습니다")
    if session.status != "in_progress":
        raise HTTPException(HTTPStatus.CONFLICT, "진행 중인 면접이 아닙니다")

    ext = _extract_ext(body.filename)
    validate_audio_upload(ext, body.content_type, body.size_bytes)

    key = f"interviews/{uuid.uuid4()}/answer.{ext}"
    return AudioUploadResponse(
        upload_url=s3.presign_put(key, body.content_type, body.size_bytes),
        s3_key=key,
        expires_in=EXPIRES_IN,
    )


@router.post("/public/interview/{token}/answer", response_model=InterviewPublicOut)
def submit_answer(
    token: str,
    body: AnswerRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """현재 질문에 답한다. 공개.

    **아직 답 안 한 가장 앞 질문**에 붙인다 — 지원자가 순번을 보내지 않는다.
    보내게 하면 어긋난 번호로 남의 칸에 답이 들어갈 수 있다.

    저장이 끝나면 백그라운드로 **꼬리질문 하나**를 만들어 다음 자리에 넣는다 —
    지원자는 이 사이에 이미 미리 준비된 다음 질문을 답하고 있고, 꼬리는 그
    다음이나 그 뒤에 자연스럽게 나간다. 실패해도 흐름은 그대로.
    """
    session = _get_by_token(db, token)

    if session.status == "expired":
        raise HTTPException(HTTPStatus.GONE, "링크 유효 기간이 지났습니다")
    # **끝난 뒤에 도착한 전사도 받는다** (2026-09-11). 번호를 짚었고, 그 칸이 이미
    # 답한 칸이며, 끝난 지 LATE_ANSWER_GRACE 안이면 — 새 답을 받는 것이 아니라
    # 이미 한 답의 글이 늦게 온 것뿐이다. 칸 조건은 아래에서 본다.
    ended_at = session.ended_at
    if ended_at is not None and ended_at.tzinfo is None:
        ended_at = ended_at.replace(tzinfo=timezone.utc)
    late = (
        session.status == "done"
        and body.seq is not None
        and ended_at is not None
        and datetime.now(timezone.utc) - ended_at <= LATE_ANSWER_GRACE
    )
    if session.status != "in_progress" and not late:
        raise HTTPException(
            HTTPStatus.CONFLICT, "진행 중인 면접이 아닙니다"
        )

    where = [
        InterviewTurn.session_id == session.id,
        InterviewTurn.transcript.is_(None),
    ]
    # 번호를 보냈으면 그 칸에만 넣는다. 전사가 뒤에서 도는 동안 다음 질문이 이미
    # 나가 있을 수 있어서, "가장 앞 빈칸" 규칙이면 답이 한 칸씩 밀린다.
    #
    # 워커는 말이 끝나는 순간 `answered_at` 부터 찍고(내부 `.../answered`) 전사는
    # 나중에 번호를 붙여 여기로 보낸다 — 그래서 번호가 있으면 **답한 칸이어도**
    # 전사가 비어 있으면 채운다. 번호가 없으면(글로 답하기·예전 경로) 지금 질문에 넣는다.
    if body.seq is not None:
        where.append(InterviewTurn.seq == body.seq)
    else:
        where.append(InterviewTurn.answered_at.is_(None))

    turn = db.scalar(select(InterviewTurn).where(*where).order_by(InterviewTurn.seq))
    if turn is None:
        # 번호를 짚어 보냈는데 없다 = 이미 답이 들어갔거나 없는 번호다. 같은 답을
        # 두 번 보내도 앞의 것을 덮어쓰지 않는다.
        raise HTTPException(
            HTTPStatus.CONFLICT, "답변할 질문이 없습니다 — 면접을 종료해 주세요"
        )
    if late and turn.answered_at is None:
        # 끝난 뒤에는 새 답을 받지 않는다 — 답한 칸의 늦은 글만
        raise HTTPException(HTTPStatus.CONFLICT, "진행 중인 면접이 아닙니다")

    # 앞서 답한 것들 — 진행 보조가 "연속으로 짧은지"를 보는 데 쓴다.
    # 저장 전에 읽어야 이번 답변이 안 섞인다.
    earlier = [
        t.transcript
        for t in db.scalars(
            select(InterviewTurn)
            .where(
                InterviewTurn.session_id == session.id,
                InterviewTurn.transcript.is_not(None),
            )
            .order_by(InterviewTurn.seq)
        ).all()
    ]

    if body.audio_s3_key is not None:
        # 전사 **전에** 키를 박아 둔다 (2026-09-16). 전사가 실패하면 이 요청의
        # 변경은 전부 사라지는데, 그러면 S3 에 음성이 있어도 어느 회차의 것인지
        # 아무도 모른다 — 나중에 다시 받아쓸 수가 없다.
        _remember_audio_key(db, turn, body.audio_s3_key)
        transcript = _transcribe_answer(turn, body.audio_s3_key)
    else:
        transcript = body.transcript

    turn.transcript = transcript
    if turn.answered_at is None:
        # 워커를 거치지 않은 답(글로 답하기·녹음 업로드)은 여기서 "답했다" 가 된다
        turn.answered_at = datetime.now(timezone.utc)
    db.commit()

    if late:
        # 끝난 면접이다 — 꼬리질문은 만들지 않는다. 채점은 끝날 때 이 글 없이
        # 돌았으니 다시 매긴다(ADR-0034). 늦은 전사가 여럿이면 그만큼 다시 돈다.
        from app.interview.scoring import score_interview_bg

        background.add_task(score_interview_bg, session.id)
    else:
        # 꼬리질문 하나를 뒤에서 만든다 (2026-09-10, ADR-0034 후속).
        # 답변이 짧거나 백엔드가 안 되면 함수가 자체적으로 조용히 접는다.
        background.add_task(_generate_followup_bg, session.id, turn.id)

    # 이 답변 하나를 서류와 맞춰 본다 (2026-09-11) — 담당자 화상 방이 그 답변 밑에
    # 띄운다. 꼬리질문 뒤에 둔다: 그쪽은 지원자가 곧 받을 질문이라 먼저 나와야 한다.
    # 스위치(`AGENT_FINDINGS_BACKEND`)가 꺼져 있으면 DB 도 안 열고 끝난다.
    from app.agent.interview_findings import generate_turn_findings_bg

    background.add_task(generate_turn_findings_bg, session.id, turn.id)

    out = get_interview_public(token, db)

    # 진행 보조 (ADR-0026 결정 4). **저장하지 않는다** — 이 응답에만 실린다.
    # 점수가 아니라 다음에 할 행동 한 문장이고, 평가로 가는 길이 없다.
    hint = interview_pacing.suggest(
        transcript, earlier, audio_duration_sec=turn.audio_duration_sec
    )
    if hint is None:
        return out
    return out.model_copy(
        update={"pacing": PacingHintOut(action=hint.action, message=hint.message)}
    )


@router.post("/public/interview/{token}/finish", response_model=InterviewPublicOut)
def finish_interview(
    token: str, background: BackgroundTasks, db: Session = Depends(get_db)
):
    """면접 종료. 공개 — 지원자가 끝낸다.

    **답을 다 안 해도 끝낼 수 있다.** 중간에 그만두는 것도 지원자의 선택이고,
    막으면 창을 닫아 버려 상태가 `in_progress` 로 영영 남는다. 어디까지 답했는지는
    `turns` 에 그대로 남으므로 담당자가 보고 판단한다.

    **대조(`findings`)는 뒤에서 만든다** (설계 §5-6). 여기서 sLLM 을 기다리면
    끝내기 요청이 몇십 초 멈춘다 — 지원자는 이미 다 답했는데 화면만 붙잡힌다.
    담당자 화면은 잠시 뒤 새로고침하면 채워져 있다.
    끝나면 아르가 백그라운드로 **면접 점수**도 매긴다 (ADR-0034, app/interview/scoring.py) —
    findings 와 독립. 둘 다 실패해도 세션은 이미 done 이라 지원자는 완료 화면을 본다.
    """
    session = _get_by_token(db, token)

    if session.status == "done":
        # 두 번 눌러도 같은 결과 — 새로고침으로 500 을 만들지 않는다
        return get_interview_public(token, db)
    if session.status != "in_progress":
        raise HTTPException(HTTPStatus.CONFLICT, "진행 중인 면접이 아닙니다")

    session.status = "done"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()

    from app.agent.interview_findings import generate_findings_bg
    from app.interview.scoring import score_interview_bg

    background.add_task(generate_findings_bg, session.id)
    background.add_task(score_interview_bg, session.id)
    return get_interview_public(token, db)
