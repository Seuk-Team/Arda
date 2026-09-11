"""지원 현황 조회 — 지원자용 (신-1 지원자 포털).

지원자가 이메일을 넣으면 **그 주소로 조회 링크를 보낸다.** 링크를 열면 자기
지원이 지금 어디까지 왔는지 본다. 로그인도 비밀번호도 없다.

## 왜 이메일로 링크를 보내나

접수번호 + 생년월일 같은 조합을 쓰지 않는 이유는 **경우의 수가 너무 적어서**다.
지원자 나이대가 20~35세로 좁혀지면 생년월일 6자리는 5천 가지쯤이고, 자동으로
하나씩 넣어 보면 뚫린다. 그리고 지금 우리는 **생년월일을 받지도 않는다** —
그걸 쓰려면 안 받던 개인정보를 새로 받아야 한다.

메일로 링크를 보내면 **이미 가진 정보(이메일)로 본인 확인이 끝난다.** 나머지
공개 경로(면접·일정·인적성)가 전부 같은 방식이라 지원자에게도 일관된다.

## 없는 이메일도 똑같이 답한다

`POST /lookup` 은 **찾았든 못 찾았든 같은 응답**을 준다. 다르게 답하면 그것만으로
"이 사람이 여기 지원했는가"를 확인하는 도구가 된다 — 지원 사실 자체가 알려지면
안 되는 정보다(이직 준비 중인 사람에게는 특히).
"""

from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared import mail
from app.shared.labels import STAGE_LABEL_APPLICANT_KR
from app.db import get_db
from app.models import Application
from app.schemas.portal import (
    PortalLookupRequest,
    PortalLookupResponse,
    PortalStatusOut,
)
from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["portal"])

PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "").rstrip("/")

# 링크 유효 기간. 짧게 두는 편이 안전하지만, 지원자가 메일을 며칠 뒤에 여는 일이
# 흔해서 너무 짧으면 "링크가 죽었다"는 문의만 늘어난다.
TOKEN_DAYS = 7

# 지원자에게 보이는 단계 이름 — 표기와 그 근거는 `app/shared/labels.py` 에 있다.
# 지원자 포털(이 파일)과 지원자 로그인 화면(talent/api/applicant_auth.py) 이 같은
# 문구를 써야 해서 공용으로 옮겼다. 이 별칭은 기존 호출부·테스트 호환용이다.
STAGE_LABEL = STAGE_LABEL_APPLICANT_KR


def _portal_url(token: str) -> str:
    return f"{PUBLIC_APP_BASE_URL}/status/{token}"


@router.post(
    "/public/applications/lookup",
    response_model=PortalLookupResponse,
    status_code=HTTPStatus.ACCEPTED,
)
def request_lookup(body: PortalLookupRequest, db: Session = Depends(get_db)):
    """지원 현황 조회 링크를 메일로 보낸다. **공개.**

    한 사람이 공고 여러 개에 냈으면 **지원 건마다 한 통씩** 나간다. 한 통에
    링크를 여러 줄 넣지 않는 이유는 메일이 지원 건에 매여 있기 때문이다
    (`email_logs.application_id`) — 억지로 한 건에 몰아 붙이면 나머지 지원의
    기록에는 아무것도 안 남는다.

    **응답은 언제나 같다.** 아래 202 는 "보냈다"가 아니라 "접수했다"이다.
    """
    email = body.email.strip().lower()
    rows = db.scalars(
        select(Application).where(Application.email == email)
    ).all()

    now = datetime.now(timezone.utc)
    queued_log_ids: list[int] = []
    for application in rows:
        posting = PgHiringRepository(db).get_posting(application.job_posting_id)
        # 부를 때마다 새로 발급한다 — 지난 링크는 그 자리에서 죽는다.
        application.portal_token = secrets.token_urlsafe(32)
        application.portal_token_expires_at = now + timedelta(days=TOKEN_DAYS)

        body_text = (
            f"{application.name}님, 지원해 주셔서 감사합니다.\n\n"
            f"'{posting.title if posting else ''}' 지원 현황은 아래 링크에서 보실 수 있습니다.\n\n"
            f"{_portal_url(application.portal_token)}\n\n"
            f"링크는 {TOKEN_DAYS}일 동안 유효합니다. "
            "본인이 요청하지 않았다면 이 메일은 무시하셔도 됩니다."
        )
        log = mail.create_custom_log(
            db,
            application_id=application.id,
            to_email=application.email,
            subject="지원 현황 조회 링크",
            body=body_text,
            actor_kind="system",
            actor_id=None,
        )
        queued_log_ids.append(log.id)

    db.commit()

    # 커밋 뒤 발행 — 큐가 죽어도 토큰은 이미 저장돼 있다 (일정 제안과 같은 순서).
    for log_id in queued_log_ids:
        try:
            mail.publish(log_id)
        except Exception:
            logger.exception("조회 링크 메일 큐 발행 실패 email_log_id=%s", log_id)

    logger.info("portal_lookup_requested", extra={"matched": len(queued_log_ids)})
    return PortalLookupResponse(
        message="입력하신 주소로 지원 현황 조회 링크를 보냈습니다. "
        "메일이 오지 않으면 지원 시 사용한 주소가 맞는지 확인해 주세요."
    )


@router.get(
    "/public/applications/status/{token}",
    response_model=PortalStatusOut,
)
def get_status(token: str, db: Session = Depends(get_db)):
    """링크로 보는 지원 현황. **공개 — 토큰이 곧 인증이다.**

    **담당자 이름·평가·메모·불합격 사유를 내려주지 않는다.** 지원자에게 필요한
    것은 "내 지원이 지금 어디까지 왔는가" 하나다.
    """
    application = db.scalar(
        select(Application).where(Application.portal_token == token)
    )
    if application is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "유효하지 않은 링크입니다")

    expires = application.portal_token_expires_at
    if expires is not None and expires <= datetime.now(timezone.utc):
        # 만료를 410 으로 준다 — 404 면 "그런 지원이 없다"로 읽혀서 지원자가
        # 자기가 낸 적 없다고 오해한다. 일정·면접 공개 경로와 같은 판단이다.
        raise HTTPException(HTTPStatus.GONE, "링크 유효 기간이 지났습니다")

    posting = PgHiringRepository(db).get_posting(application.job_posting_id)
    return PortalStatusOut(
        applicant_name=application.name,
        posting_title=posting.title if posting else "",
        stage_label=STAGE_LABEL.get(application.current_stage, "확인 중"),
        submitted_at=application.created_at,
    )
