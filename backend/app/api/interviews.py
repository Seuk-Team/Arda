"""AI 면접 API — 세션 생성과 지원자 공개 접근 (ADR-0026).

설계는 docs/02_tasks/AI면접-설계.md §5 의 2·3번.

지원자는 로그인이 없으므로 일정 제안(ADR-0016)과 **같은 토큰 공개 접근 패턴**을 쓴다.
만료도 같은 방식이다 — 스케줄러 없이 조회 시점에 판정한다(B4 마감과 동일).

**질문은 아직 자동 생성하지 않는다.** 설계 §5 의 5번에서 붙인다. 그때까지는
담당자가 넣은 질문 목록으로 돈다 — 그래야 뼈대가 먼저 관통된다.
"""

import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import interview_pacing, lie_analysis, s3
from app.agent import stt
from app.api.files import _extract_ext, validate_audio_upload
from app.s3 import EXPIRES_IN
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
    ActiveSessionOut,
    AnswerRequest,
    AudioUploadRequest,
    AudioUploadResponse,
    ConsentRequest,
    InterviewPublicOut,
    PacingHintOut,
    QuestionsSet,
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
    if session.status == "in_progress":
        # **아직 답 안 한 가장 앞 질문**이 현재 질문이다.
        # 마지막 질문을 보면 안 된다 — 3개 중 1번만 답했을 때 2번이 아니라
        # 3번을 내주게 된다. 답변 저장(submit_answer)도 같은 규칙을 쓴다.
        current = db.scalar(
            select(InterviewTurn)
            .where(
                InterviewTurn.session_id == session.id,
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
    session = db.get(InterviewSession, session_id)
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


# 위 발급 경로가 만든 모양만 받는다. 클라이언트가 준 키를 그냥 믿으면
# `applications/<남의 uuid>/resume.pdf` 를 답변이라고 보내 **남의 이력서를 읽어
# 전사**시킬 수 있다 — 서버가 S3 를 대신 읽어 주는 경로라 그대로 유출이 된다.
_AUDIO_KEY = re.compile(
    r"^interviews/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"answer\.([a-z0-9]{1,10})$"
)


def _transcribe_answer(turn: InterviewTurn, key: str) -> str:
    """음성을 읽어 전사하고, 회차에 길이·비용까지 적는다 (설계 §5-4).

    **`raw` 를 저장한다 — `resolved` 가 아니다.** 전사에는 엔티티 해석("파이썬
    이년" → "Python 2년")이 같이 나오는데, 면접 답변은 나중에 이력서 주장과
    맞춰 **원문으로 인용**되는 자리다(ADR-0026 결정 3). 다듬은 문장을 인용하면
    지원자가 "그렇게 말한 적 없다"고 할 때 우리가 틀린다.

    실패하면 **아무것도 저장하지 않고 502** 다. 음성은 S3 에 남아 있지만 회차는
    비어 있으므로 지원자에게는 같은 질문이 그대로 보이고 다시 답할 수 있다.
    반쯤 저장해 두면 답을 못 한 채로 다음 질문으로 넘어간다.
    """
    matched = _AUDIO_KEY.match(key)
    if matched is None:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY, "잘못된 음성 파일 키입니다"
        )

    try:
        audio = s3.read_object(key)
    except Exception as exc:
        raise HTTPException(
            HTTPStatus.BAD_GATEWAY, f"음성을 읽지 못했습니다 ({type(exc).__name__})"
        )

    try:
        result = stt.transcribe(audio, filename=f"answer.{matched.group(1)}")
    except Exception as exc:
        raise HTTPException(
            HTTPStatus.BAD_GATEWAY, f"음성을 전사하지 못했습니다 ({type(exc).__name__})"
        )

    text = (result.get("raw") or "").strip()
    if not text:
        # 빈 문자열을 넣으면 "답한 질문"이 되어 다음 질문으로 넘어간다.
        # 말이 안 담긴 녹음은 답변이 아니라 다시 하면 되는 일이다.
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "음성에서 말을 찾지 못했습니다. 다시 답변해 주세요",
        )

    turn.audio_s3_key = key
    turn.audio_duration_sec = result.get("audio_duration_sec")
    turn.stt_cost_usd = result.get("cost_usd")
    return text


@router.post("/public/interview/{token}/answer", response_model=InterviewPublicOut)
def submit_answer(token: str, body: AnswerRequest, db: Session = Depends(get_db)):
    """현재 질문에 답한다. 공개.

    **아직 답 안 한 가장 앞 질문**에 붙인다 — 지원자가 순번을 보내지 않는다.
    보내게 하면 어긋난 번호로 남의 칸에 답이 들어갈 수 있다.

    지금은 텍스트만 받는다. 음성 업로드 → STT 는 설계 §5 의 4번이다.
    """
    session = _get_by_token(db, token)

    if session.status == "expired":
        raise HTTPException(HTTPStatus.GONE, "링크 유효 기간이 지났습니다")
    if session.status != "in_progress":
        raise HTTPException(
            HTTPStatus.CONFLICT, "진행 중인 면접이 아닙니다"
        )

    where = [
        InterviewTurn.session_id == session.id,
        InterviewTurn.transcript.is_(None),
    ]
    # 번호를 보냈으면 그 칸에만 넣는다. 전사가 뒤에서 도는 동안 다음 질문이 이미
    # 나가 있을 수 있어서, "가장 앞 빈칸" 규칙이면 답이 한 칸씩 밀린다.
    if body.seq is not None:
        where.append(InterviewTurn.seq == body.seq)

    turn = db.scalar(select(InterviewTurn).where(*where).order_by(InterviewTurn.seq))
    if turn is None:
        # 번호를 짚어 보냈는데 없다 = 이미 답이 들어갔거나 없는 번호다. 같은 답을
        # 두 번 보내도 앞의 것을 덮어쓰지 않는다.
        raise HTTPException(
            HTTPStatus.CONFLICT, "답변할 질문이 없습니다 — 면접을 종료해 주세요"
        )

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
        transcript = _transcribe_answer(turn, body.audio_s3_key)
    else:
        transcript = body.transcript

    turn.transcript = transcript
    db.commit()

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
    끝나면 아르가 백그라운드로 **면접 점수**도 매긴다 (ADR-0034, app/interview_scoring.py) —
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
    from app.interview_scoring import score_interview_bg

    background.add_task(generate_findings_bg, session.id)
    background.add_task(score_interview_bg, session.id)
    return get_interview_public(token, db)
