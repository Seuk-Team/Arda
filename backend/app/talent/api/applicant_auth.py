"""지원자 앱 로그인 — 이메일 + 생년월일 8자리 (ADR-0033).

지원자가 앱에서 자기 지원 현황을 본다. 아이디는 **지원할 때 쓴 이메일**,
비밀번호는 **생년월일 8자리**(`YYYYMMDD`)다.

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
from datetime import date, datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_applicant_email
from app.api.portal import STAGE_LABEL
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
)
from app.security import APPLICANT_EXPIRES_MINUTES, create_applicant_token

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

    birth = _parse_birth(body.birth_date)
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
        raise HTTPException(HTTPStatus.UNAUTHORIZED, "이메일 또는 생년월일이 맞지 않습니다")

    _FAILS.pop(email, None)
    return ApplicantLoginResponse(
        access_token=create_applicant_token(email),
        expires_in=APPLICANT_EXPIRES_MINUTES * 60,
    )


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
