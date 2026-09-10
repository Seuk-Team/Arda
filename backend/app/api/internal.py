"""내부 API — n8n 워크플로 전용 (ADR-0030·ADR-0031).

n8n 이 실제 사람이 아니라 자동화 도구다 — 그래서 JWT 사용자 인증 대신 서비스 토큰
하나로 보호한다. 이 토큰은 서버 `.env` 의 `ARDA_SERVICE_TOKEN` 에만 있고, 저장소에는
값이 없다(이름만 `.env.example` 에).

두 경로:

- `GET  /internal/email-logs/{id}/render`  → n8n 이 보낼 완성된 제목·본문·수신자.
  기존 워커의 렌더 로직과 같은 것을 그대로 부른다 — 두 경로가 다른 문구를 만들면
  담당자가 두 경로를 오갈 때마다 지원자한테 나가는 메일이 바뀐다.
- `POST /internal/email-logs/{id}/result` → 발송 결과(sent + provider_message_id
  또는 failed + error) 를 행에 남긴다. n8n 이 재시도 3회 후 결과를 이 API 로만
  적으므로, **멱등이다** — 이미 sent 인 행에 sent 를 다시 써도 no-op.

MAIL_DISPATCH=worker 인 동안엔 이 경로가 안 불린다 — 그때는 워커가 자기가 렌더하고
자기가 결과를 행에 쓴다. 이 라우터는 오직 n8n 경로용.

관련: [docs/03_decision/0030-n8n-알림-자동화-분리.md] · [ADR-0031] · infra/n8n/stage-changed.json.
"""

import logging
import os
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.db import get_db
from app.models import Application, EmailLog, InterviewTurn
from app.worker import _actor, _context, _reply_to

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/internal", tags=["internal"])


def _require_service_token(
    x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
) -> None:
    """서비스 토큰 검증. 서버 `.env` 의 `ARDA_SERVICE_TOKEN` 과 비교한다.

    빈 값·환경변수 미설정은 전부 401. 이 경로가 실수로 열리지 않도록 기본은
    "닫힘" 이다 — 토큰 없이 배포하면 워크플로가 401 로 실패해 눈에 띈다.
    """
    expected = os.getenv("ARDA_SERVICE_TOKEN", "").strip()
    if not expected:
        # 운영 서버에서 이 상태면 n8n 워크플로 전부 실패한다 — 로그로 남긴다
        logger.error("ARDA_SERVICE_TOKEN 미설정 — /internal/* 는 전부 401")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="service token not configured",
        )
    if not x_service_token or x_service_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid service token",
        )


class RenderOut(BaseModel):
    """n8n 워크플로의 렌더링 조회 → SMTP 발송 노드가 읽는 형태."""

    to: str
    subject: str
    body_text: str
    body_html: str | None = None  # 지금은 안 쓰지만 자리는 열어 둠 (07-deploy 참조)
    from_email: str
    reply_to: str | None = None


class ResultIn(BaseModel):
    """n8n 워크플로의 결과 기록 노드가 보내는 것."""

    status: Literal["sent", "failed"]
    provider_message_id: str | None = None
    error: str | None = None


@router.get(
    "/email-logs/{log_id}/render",
    response_model=RenderOut,
    dependencies=[Depends(_require_service_token)],
)
def render_email_log(log_id: int, db: Session = Depends(get_db)) -> RenderOut:
    """n8n 에게 "이 로그 행에 대응하는 완성된 제목·본문·수신자" 를 준다.

    로직은 워커의 handle() 과 같은 원리: `log.body` 가 있으면 그대로 (수동·에이전트가
    이미 승인한 문구), 없으면 템플릿 렌더.

    n8n 이 부르는 순간에 값이 결정되므로 — 담당자가 그 사이에 템플릿을 바꾸면 다음
    발송부터 반영된다. 워커 동작과 같다.
    """
    log = db.get(EmailLog, log_id)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"email_log not found: id={log_id}",
        )

    # 이미 sent 인 행은 다시 렌더할 이유가 없고, n8n 이 실수로 다시 보내면 지원자에게
    # 같은 메일이 두 번 간다. 워커의 멱등 규칙과 같은 방향.
    if log.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"already sent: id={log_id}",
        )

    actor_name, actor_email = _actor(db, log)
    from_name = mail.sender_name(log.stage, log.actor_kind, actor_name)
    if log.body is not None:
        # 확정 본문이 있는 행(수동·에이전트 발송)은 다시 렌더하지 않는다 — 워커와 같은 규칙.
        subject, body = log.subject or "", log.body
    else:
        subject, body = mail.render(
            db,
            log.stage,
            *_context(db, log),
            actor_kind=log.actor_kind,
            actor_name=actor_name,
        )

    # From 은 표시 이름 없이 주소만 넘긴다 — n8n SMTP 노드가 알아서 표시 이름을 붙일
    # 여지가 있지만 지금은 단순히 주소 하나. 원하면 formataddr 처럼 "이름 <주소>" 로
    # 바꿔도 되는데, 워커 흐름과 동일하게 두려면 별도 필드가 나아 보인다 — 추후 조정.
    from_email = os.getenv("SES_FROM_EMAIL", "").strip() or "noreply@localhost"

    return RenderOut(
        to=log.to_email,
        subject=subject,
        body_text=body,
        body_html=None,
        from_email=from_email,
        reply_to=_reply_to(log, actor_email),
    )


@router.post(
    "/email-logs/{log_id}/result",
    dependencies=[Depends(_require_service_token)],
    status_code=status.HTTP_204_NO_CONTENT,
)
def record_email_log_result(
    log_id: int,
    body: ResultIn,
    db: Session = Depends(get_db),
) -> None:
    """n8n 워크플로가 발송 결과(성공·실패)를 이 행에 남긴다.

    **멱등**: 이미 sent 인 행은 손대지 않는다 — 재시도로 두 번 성공이 와도 안전.
    n8n 은 재시도 3회 후에도 실패면 failed 로 온다.
    """
    log = db.get(EmailLog, log_id)
    if log is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"email_log not found: id={log_id}",
        )

    if log.status == "sent" and body.status == "sent":
        logger.info(
            "결과 기록 중복 sent — no-op email_log_id=%s message_id=%s",
            log_id,
            body.provider_message_id,
        )
        return

    if body.status == "sent":
        from datetime import UTC, datetime

        log.status = "sent"
        log.sent_at = datetime.now(UTC)
        log.provider_message_id = body.provider_message_id
        logger.info(
            "결과 기록 sent email_log_id=%s message_id=%s",
            log_id,
            body.provider_message_id,
        )
    else:  # failed
        log.status = "failed"
        log.retry_count = (log.retry_count or 0) + 1
        logger.warning(
            "결과 기록 failed email_log_id=%s error=%s",
            log_id,
            (body.error or "unknown")[:200],
        )

    db.commit()


# ── 실시간 판정 (ADR-0029) ──────────────────────────────────────────────
#
# 거짓말 탐지 워커가 면접 중에 낸 판정을 **담당자 화면으로 흘려보낸다.**
#
# **왜 워커가 직접 보내는가.** 처음에는 판정이 지원자 폰을 거쳐 담당자에게 갔다.
# 화면에 안 그려도 **개발자 도구를 열면 보인다** — ADR-0029 의 "지원자에게 판정을
# 보여 주지 않는다"가 거기서 깨진다. 지원자 기기를 아예 안 지나가게 바꾼다
# (2026-09-08, cloverky 지적).
#
# **저장하지 않는다.** 흐르는 값이고, 남기기로 한 것은 면접이 끝난 뒤의 결과다
# (ADR-0029 결정 2). 여기서 쌓기 시작하면 "언제 잰 값인가"가 흐려진다.
#
# 받는 사람이 없으면 **그냥 버린다** — 담당자가 아직 화면을 안 열었을 뿐이고,
# 그것 때문에 면접이 멈추면 안 된다.


class VerdictIn(BaseModel):
    """워커가 보내는 판정 하나. **모양을 좁게 잡지 않는다** — 모델이 내는 값이
    늘어도 백엔드를 고치지 않게 그대로 흘려보낸다."""

    model_config = ConfigDict(extra="allow")

    truth_pct: float | None = None
    lie_pct: float | None = None
    window_sec: float | None = None


@router.post(
    "/interview/{token}/verdict",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_service_token)],
)
async def push_verdict(token: str, body: VerdictIn, db: Session = Depends(get_db)):
    """면접 한 건의 실시간 판정을 담당자에게 민다.

    **토큰으로 방을 찾는다** — 시그널링과 같은 방이라 담당자가 이미 앉아 있다.
    받는 사람이 없으면 204 로 조용히 끝난다(워커가 재시도하지 않게).

    ADR-0034: 판정 개별 값은 여전히 저장하지 않지만, 면접 점수의 "진위 일관성" 재료로
    세션에 **집계값**(표본 수·truth_pct 합)만 더한다. 이 부분이 실패해도 담당자
    화면으로 미는 것은 이미 끝났으므로 로그만 남긴다.
    """
    from app.api.interview_rtc import push_to_recruiter

    await push_to_recruiter(token, {"type": "verdict", **body.model_dump()})

    if body.truth_pct is not None:
        try:
            from app.interview_scoring import record_truth_sample
            from app.models import InterviewSession

            session = db.scalar(select(InterviewSession).where(InterviewSession.token == token))
            if session is not None and session.status == "in_progress":
                record_truth_sample(db, session, float(body.truth_pct))
        except Exception:
            logger.exception("진위 표본 집계 실패: token=%s", token[:8])


class QuestionOut(BaseModel):
    seq: int
    question: str


@router.get(
    "/interview/{token}/questions",
    response_model=list[QuestionOut],
    dependencies=[Depends(_require_service_token)],
)
def get_questions(token: str, db: Session = Depends(get_db)):
    """면접 질문 전체. 워커가 시작할 때 한 번 받는다.

    **왜 필요한가**: 지원자용 조회는 "지금 질문" 하나만 준다. 그래서 워커가 다음
    질문을 알려면 답변을 저장해야 했고, 답변을 저장하려면 전사가 끝나야 했다 —
    지원자가 전사를 기다린 이유가 이 사슬이다.

    질문 목록을 미리 쥐면 **말이 끝나자마자 다음 질문을 보낼 수 있다.** 전사는
    뒤에서 돌다가 끝나면 `seq` 를 붙여 저장한다.

    **담당자가 넣은 질문이라 지원자 정보가 아니다** — 그래도 서비스 토큰 뒤에 둔다.
    """
    session = _find_session_or_404(db, token)
    turns = db.scalars(
        select(InterviewTurn)
        .where(InterviewTurn.session_id == session.id)
        .order_by(InterviewTurn.seq)
    ).all()
    return [QuestionOut(seq=t.seq, question=t.question) for t in turns]


# --- 이력서 사진: 워커가 대리응시를 확인할 때 쓴다 (회의 2026-09-09 3번) ---
#
# **저장하지 않는다.** 워커가 면접 시작 때 한 번 받아서 얼굴을 대조하고 버린다.
# 얼굴 지문을 DB 에 쌓으면 지켜야 할 민감정보가 하나 더 늘고, 대리응시 확인에는
# 그때그때 비교로 충분하다 — InterviewSession 이 영상을 저장하지 않는 것과 같은 이유.
#
# 사진이 없으면 404 다. 워커는 그때 **확인을 건너뛴다** — 서식에 사진이 빠졌다고
# 지원자가 면접을 못 보면 안 된다.


@router.get(
    "/interview/{token}/portrait",
    dependencies=[Depends(_require_service_token)],
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def get_portrait(token: str, db: Session = Depends(get_db)):
    """면접 지원자의 이력서 증명사진 원본 바이트."""
    from app.agent.photo import portrait_of

    session = _find_session_or_404(db, token)
    app_row = db.get(Application, session.application_id)
    photo = portrait_of(app_row) if app_row else None
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="사진 없음")

    # 이력서에 든 그림은 대개 JPEG 이지만 PNG 도 있다. 받는 쪽이 바이트를 보고
    # 여는 만큼 정확한 서브타입까지 맞추지는 않는다.
    return Response(content=photo, media_type="image/jpeg")


class IdentityIn(BaseModel):
    """워커가 보내는 동일인 확인 결과. 면접 한 건에 **한 번만** 온다."""

    # same | different | unclear — 워커의 face_match.verdict() 와 같은 말
    match: Literal["same", "different", "unclear"]
    score: float


@router.post(
    "/interview/{token}/identity",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_service_token)],
)
async def push_identity(token: str, body: IdentityIn):
    """이력서 사진 대조 결과를 담당자에게 민다.

    **판정(`verdict`)과 다른 통로로 보낸다.** 참·거짓 판정은 매초 흐르는 값이고
    이건 신원 확인이라 성격이 다르다 — 섞어 보내면 화면에서 "거짓말 지표"처럼
    읽히고, 그건 이 값이 하려는 말이 아니다.
    """
    from app.api.interview_rtc import push_to_recruiter

    await push_to_recruiter(token, {"type": "identity", **body.model_dump()})


def _find_session_or_404(db: Session, token: str):
    """토큰으로 면접 세션을 찾는다. 없으면 404 — 워커용 경로 셋이 같이 쓴다."""
    from app.api.interview_rtc import _find_session

    session = _find_session(db, token)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="세션 없음")
    return session
