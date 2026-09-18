"""지원자 앱 로그인 — 비밀번호, 아직 안 정했으면 생년월일 (ADR-0033 · 2026-09-16 개정).

지원자가 앱·웹에서 자기 지원 현황을 본다. 아이디는 **지원할 때 쓴 이메일**이다.

- **비밀번호를 정한 계정**은 비밀번호로만 들어온다. 설정 링크는 메일로 받는다
  (`applicant_password.py`). 둘 다 열어 두면 약한 쪽으로 들어오기 때문이다.
- **아직 안 정한 계정**은 예전대로 **생년월일 8자리**(`YYYYMMDD`)로 들어온다.
  기존 지원자를 그 자리에서 막지 않는다.

아래는 생년월일 방식에 대한 원래 기록이다 — **그 방식이 여전히 살아 있는 동안
유효하다.**

## 이 방식의 약점을 문서에 남긴다

생년월일은 비밀번호로 약하다. 지원자 연령대가 20~35세로 좁혀지면 경우의 수가
**만 단위**고, 자동으로 하나씩 넣으면 뚫린다. `portal.py` 가 같은 이유로 이
조합을 거부했었다 — 그 판단은 지금도 기술적으로 맞다.

그럼에도 채택한 이유와, 그래서 **무엇으로 막는지**는 [ADR-0033] 에 적었다.
여기서는 실제로 건 방어만 정리한다.

1. **시도 횟수 제한이 유일한 실질 방어다.** 해시가 아니다 — 탐색 공간이 작아서
   해시를 떠도 대조로 뚫린다. 그래서 이메일당 실패를 세고 잠근다.
2. **틀린 이메일과 틀린 생년월일을 구별해 주지 않는다.** 다르게 답하면 그것만으로
   "이 사람이 여기 지원했는가"를 확인하는 도구가 된다 — 지원 사실 자체가
   알려지면 안 되는 정보다(이직 준비 중인 사람에게는 특히).
3. **토큰이 볼 수 있는 것은 자기 지원뿐이다.** 직원 토큰과 종류를 나눠
   (`security.TYP_*`) 서로의 경로를 못 타게 했다.
4. **생년월일이 없는 지원서는 로그인이 안 된다.** 옛 지원서는 값이 비어 있고,
   그때는 막는 쪽으로 떨어진다 — 빈 값끼리 맞아떨어지는 일이 없어야 한다.

## 잠금은 이 프로세스 안에서만 유효하다

실패 횟수를 파이썬 딕셔너리에 둔다. uvicorn 워커가 2개 이상이면 프로세스마다
따로 세므로 **실질 상한이 워커 수만큼 늘어난다.** 운영은 지금 워커 1개다
(app/main.py 기동 로그에 같은 취지의 경고가 있다). 워커를 늘리려면 여기와
`interview_rtc` 를 함께 Redis 로 옮겨야 한다.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from http import HTTPStatus

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_applicant_email
from app.talent import applicant_password
from app.shared.labels import STAGE_LABEL_APPLICANT_KR as STAGE_LABEL
from app.models import (
    Application,
    AptitudeSession,
    InterviewSession,
    ScheduleProposal,
)
from app.schemas.applicant_auth import (
    ApplicantLoginRequest,
    ApplicantLoginResponse,
    ApplicantMeOut,
    MyApplicationOut,
    MyInterviewOut,
    MyTokenLinkOut,
    PasswordSetupRequest,
    PasswordTokenOut,
    SetPasswordRequest,
)
from app.security import APPLICANT_EXPIRES_MINUTES, create_applicant_token, is_demo_applicant
from app.application.demo_reset import reset_demo_applicant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["applicant-auth"])

# 잠금 정책. 만 단위 탐색 공간을 사람이 아니라 **시간**으로 막는다 —
# 5회마다 15분이면 하루에 480회고, 생년월일 만 가지를 훑는 데 20일이 넘는다.
MAX_ATTEMPTS = 5
LOCK_SECONDS = 15 * 60

# 이메일 → (실패 횟수, 마지막 실패 시각)
_FAILS: dict[str, tuple[int, float]] = {}


def _locked_for(email: str, now: float) -> int:
    """남은 잠금 시간(초). 0 이면 안 잠겼다."""
    entry = _FAILS.get(email)
    if entry is None:
        return 0
    count, last = entry
    if count < MAX_ATTEMPTS:
        return 0
    left = int(LOCK_SECONDS - (now - last))
    if left <= 0:
        _FAILS.pop(email, None)
        return 0
    return left


def _note_failure(email: str, now: float) -> None:
    count, _ = _FAILS.get(email, (0, now))
    _FAILS[email] = (count + 1, now)


def _parse_birth(raw: str) -> date | None:
    """`YYYYMMDD` 만 받는다. 구분자가 섞인 입력은 앱이 정리해 보낸다."""
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def _not_expired(model, *, finished: tuple[str, ...]):
    """기한이 지난 줄을 거르는 조건 (2026-09-16, 앱 오너 요청).

    **만료 판정은 토큰을 열 때만 돈다**(스케줄러 없음 — B4 마감과 같은 방식).
    그래서 아무도 그 링크를 안 열었으면 `status` 는 기한이 지나도 `pending` 이다.
    이 목록이 상태만 보고 걸러 왔기 때문에, 앱 홈은 「3일 남음」이라 적고 들어가면
    「기한이 지났습니다」가 뜨는 일이 났다(2026-09-15 실기기).

    **끝난 것은 기한과 무관하게 남긴다.** 면접을 마쳤거나 일정이 확정된 줄은
    지원자가 다시 볼 자리이지 놓친 것이 아니다 — 여기를 안 가르면 09-09 에
    고쳤던 "마친 면접이 화면에서 사라지는" 문제가 되돌아온다.

    이 함수는 **읽기만 한다.** 목록을 그릴 때마다 `status` 를 `expired` 로 쓰면
    지원자가 앱을 켤 때마다 GET 이 커밋을 남긴다 — 그건 토큰을 실제로 열 때 한다.
    """
    return or_(
        model.status.in_(finished),
        model.expires_at.is_(None),
        model.expires_at > datetime.now(timezone.utc),
    )


@router.post("/public/applicant/login", response_model=ApplicantLoginResponse)
def applicant_login(
    body: ApplicantLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """지원자 로그인. 공개 — 로그인 자체가 이 경로다.

    **실패 사유를 나누지 않는다.** 없는 이메일·틀린 생년월일·생년월일이 없는
    옛 지원서가 전부 같은 401 이다.
    """
    email = body.email.strip().lower()
    now = time.time()

    left = _locked_for(email, now)
    if left > 0:
        raise HTTPException(
            HTTPStatus.TOO_MANY_REQUESTS,
            f"로그인 시도가 많습니다. {left // 60 + 1}분 뒤에 다시 시도해 주세요",
        )

    # **비밀번호를 정한 계정은 생년월일로 못 들어온다** (2026-09-16, ADR-0033 개정).
    # 둘 다 열어 두면 약한 쪽으로 들어온다 — 생년월일은 SNS·이력서로 알 수 있는
    # 값이라, 비밀번호를 정해도 보안이 그대로다.
    if applicant_password.has_password(db, email):
        ok = bool(body.password) and applicant_password.verify(db, email, body.password)
    elif body.password:
        # 아직 안 정한 계정에 비밀번호로 들어오려 한 경우. **"설정 안 했다"고
        # 알려 주지 않는다** — 그 자체가 "이 사람이 여기 지원했다" 는 신호다.
        ok = False
    else:
        birth = _parse_birth(body.birth_date or "")
        rows = (
            db.scalars(select(Application).where(Application.email == email)).all()
            if birth is not None
            else []
        )
        # 같은 이메일로 여러 공고에 지원할 수 있다. 하나라도 맞으면 통과다 —
        # `birth_date` 가 없는 행은 맞을 수 없다(None == None 을 만들지 않는다).
        ok = any(r.birth_date is not None and r.birth_date == birth for r in rows)

    if not ok:
        _note_failure(email, now)
        # 남은 시도 횟수를 알려주지 않는다. 알려주면 "이 이메일은 존재한다"는
        # 신호가 된다 — 없는 이메일도 똑같이 세기 때문이다.
        logger.info("applicant_login_failed", extra={"email_domain": email.rpartition("@")[2]})
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "로그인 정보가 맞지 않습니다")

    _FAILS.pop(email, None)

    # 심사위원 공유 데모 지원자면 로그인 때마다 세 화면(인적성·면접일정·AI면접)을
    # 기준 상태로 되돌린다 — 앞 심사위원이 끝내 놨어도 다음 사람이 처음부터 본다.
    # 실 지원자는 DEMO_APPLICANT_EMAILS 에 없어 이 경로를 타지 않는다. 리셋이 실패해도
    # 로그인은 막지 않는다 (편의 기능이 인증을 가로막지 않게).
    if is_demo_applicant(email):
        try:
            reset_demo_applicant(db, email)
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("demo_applicant_reset 실패: %s", email.rpartition("@")[2])

    return ApplicantLoginResponse(
        access_token=create_applicant_token(email),
        expires_in=APPLICANT_EXPIRES_MINUTES * 60,
    )


@router.post("/public/applicant/password-setup-request", status_code=HTTPStatus.ACCEPTED)
def request_password_setup(
    body: PasswordSetupRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """비밀번호 설정 링크를 메일로 보낸다. **처음 정할 때와 잊었을 때가 같은 경로다.**

    **지원 이력이 없어도 202 다.** 있고 없고를 다르게 답하면 "이 사람이 여기
    지원했는가" 를 확인하는 도구가 된다 — 이직 준비 중인 사람에게는 지원 사실
    자체가 지켜야 할 정보다(로그인이 실패 사유를 안 나누는 것과 같은 이유).

    **링크가 새면 계정이 넘어간다.** 그래서 원본은 메일 본문에만 두고 DB 에는
    해시만 남기며, 새로 발급하면 그 이메일의 이전 링크는 그 자리에서 죽는다.
    """
    email = applicant_password.normalize(body.email)
    rows = db.scalars(
        select(Application).where(Application.email == email).limit(1)
    ).all()
    if rows:
        token = applicant_password.issue_token(db, email)
        db.commit()
        background.add_task(
            _send_password_mail, rows[0].id, email, applicant_password.setup_url(token)
        )
    return {"detail": "메일을 보냈습니다"}


@router.get(
    "/public/applicant/set-password/{token}", response_model=PasswordTokenOut
)
def check_password_token(token: str, db: Session = Depends(get_db)):
    """링크가 살아 있는지 + 어느 계정인지. 화면이 아이디를 보여 줘야 한다.

    **만료와 이미 사용됨을 구별해 주지 않는다** — 다르게 답하면 토큰 유효성을
    떠볼 수 있다. 둘 다 410 에 같은 문구다.
    """
    row = applicant_password.resolve_token(db, token)
    if row is None:
        raise HTTPException(HTTPStatus.GONE, "만료됐거나 이미 사용한 링크입니다")
    return PasswordTokenOut(email=row.email)


@router.post("/public/applicant/set-password/{token}")
def set_password(
    token: str, body: SetPasswordRequest, db: Session = Depends(get_db)
):
    """비밀번호를 정한다. **링크는 한 번만 쓴다** — 쓰고 나면 그 자리에서 죽는다.

    정하고 나면 그 계정은 **생년월일로 못 들어온다**(로그인 참고).
    """
    if applicant_password.too_long(body.password):
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "비밀번호가 너무 깁니다 (한글은 24자, 영문·숫자는 64자까지)",
        )
    row = applicant_password.resolve_token(db, token)
    if row is None:
        raise HTTPException(HTTPStatus.GONE, "만료됐거나 이미 사용한 링크입니다")

    applicant_password.set_password(db, row, body.password)
    return {"detail": "비밀번호를 정했습니다"}


def _send_password_mail(application_id: int, email: str, url: str) -> None:
    """설정 링크를 메일로 보낸다. **실패해도 요청은 이미 202 로 끝났다.**

    지원자를 기다리게 하지 않는 자리다 — 메일 경로가 죽어 있어도 "메일을 보냈다"
    라고 답하는 것은 위 경로가 존재 여부를 안 알려주는 것과 같은 선택이다.
    """
    from app.db import SessionLocal
    from app.shared import mail

    try:
        with SessionLocal() as db:
            log = mail.create_log(db, application_id, email, "password_setup")
            log.subject, log.body = mail.render_password_setup(db, url)
            db.commit()
            mail.publish(log.id)
    except Exception:
        logger.exception("비밀번호 설정 메일 발송 실패: domain=%s", email.rpartition("@")[2])


@router.get("/applicant/me", response_model=ApplicantMeOut)
def applicant_me(
    email: str = Depends(get_current_applicant_email),
    db: Session = Depends(get_db),
):
    """내 지원 현황. **토큰의 이메일로만 찾는다** — 조회 인자를 받지 않는다.

    인자로 받으면 남의 것을 넣어 보는 길이 생긴다. 볼 수 있는 것은 자기가 낸
    지원뿐이고, 담당자 이름·평가·AI 요약은 내려주지 않는다.
    """
    rows = db.scalars(
        select(Application)
        .where(Application.email == email)
        .order_by(Application.created_at.desc())
    ).all()

    titles = {}
    sessions: dict[int, list[InterviewSession]] = {}
    aptitudes: dict[int, list[AptitudeSession]] = {}
    schedules: dict[int, list[ScheduleProposal]] = {}
    if rows:
        # HiringRepository 로 위임 (ADR-0035 Phase 3b). 같은 쿼리를 여기저기서
        # 반복하지 않기 위해 저장소 한 곳으로 모은다.
        from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

        ids = {r.job_posting_id for r in rows}
        titles = {p.id: p.title for p in PgHiringRepository(db).find_postings_by_ids(ids)}
        # **끝난 것도 싣는다** (2026-09-09 개정). 09-08 까지는 `done` 을 뺐는데,
        # 그러면 면접을 마친 지원자의 화면에서 면접이 **통째로 사라진다** —
        # "완료"와 "아직 안 잡힘"이 같은 화면이 되어, 방금 30분 면접을 본 사람이
        # 자기가 낸 것이 접수됐는지 알 수 없다(앱 실측에서 나온 것이다).
        #
        # 대신 `expired` 는 여전히 뺀다. 그건 **지원자가 놓친 것**이라 화면에
        # 띄우면 할 수 있는 일이 없는 줄이 남는다.
        #
        # 상태를 같이 내리므로 **화면이 버튼을 열지 말지 스스로 가른다** —
        # 끝난 줄에는 들어가는 문을 그리지 않는다(app · web 둘 다).
        app_ids = [r.id for r in rows]
        for s in db.scalars(
            select(InterviewSession)
            .where(
                InterviewSession.application_id.in_(app_ids),
                InterviewSession.status.in_(("pending", "in_progress", "done")),
                _not_expired(InterviewSession, finished=("done",)),
            )
            .order_by(InterviewSession.id)
        ).all():
            sessions.setdefault(s.application_id, []).append(s)

        # 인적성도 같은 규칙이다 — 낸 것(`done`)은 "제출했습니다" 로 보여 주고,
        # 만료된 것만 뺀다.
        for a in db.scalars(
            select(AptitudeSession)
            .where(
                AptitudeSession.application_id.in_(app_ids),
                AptitudeSession.status.in_(("pending", "done")),
                _not_expired(AptitudeSession, finished=("done",)),
            )
            .order_by(AptitudeSession.id)
        ).all():
            aptitudes.setdefault(a.application_id, []).append(a)

        # 일정은 `confirmed` 도 싣는다 — 확정 뒤에도 **언제로 잡혔는지 다시 볼 일**이
        # 있어서다. 면접·인적성과 다른 점이라 여기 적어 둔다.
        for p in db.scalars(
            select(ScheduleProposal)
            .where(
                ScheduleProposal.application_id.in_(app_ids),
                ScheduleProposal.status.in_(("proposed", "confirmed")),
                _not_expired(ScheduleProposal, finished=("confirmed",)),
            )
            .order_by(ScheduleProposal.id)
        ).all():
            schedules.setdefault(p.application_id, []).append(p)

    return ApplicantMeOut(
        email=email,
        name=rows[0].name if rows else "",
        applications=[
            MyApplicationOut(
                id=r.id,
                posting_title=titles.get(r.job_posting_id, ""),
                # **포털과 같은 문구를 쓴다.** `rejected` 를 "불합격"으로 내리지
                # 않는 이유가 여기서도 그대로다 — 담당자가 통보하기 전에 앱이
                # 먼저 말하면, 사람이 전할 말을 화면이 앞지른다.
                stage_label=STAGE_LABEL.get(r.current_stage, "확인 중"),
                applied_at=r.created_at,
                interviews=[
                    MyInterviewOut(
                        token=s.token, status=s.status, expires_at=s.expires_at
                    )
                    for s in sessions.get(r.id, [])
                ],
                aptitudes=[
                    MyTokenLinkOut(
                        token=a.token, status=a.status, expires_at=a.expires_at
                    )
                    for a in aptitudes.get(r.id, [])
                ],
                schedules=[
                    MyTokenLinkOut(
                        token=p.token, status=p.status, expires_at=p.expires_at
                    )
                    for p in schedules.get(r.id, [])
                ],
            )
            for r in rows
        ],
    )
