"""단계 전환의 **부수효과**를 한 곳에 모은다 — 이력(D5) · 불합격 사유(D8) · 메일 큐(G1).

전환 **규칙** 은 `app/stages.py` 다. 이 파일은 "규칙을 통과한 전환이 실제로 무엇을
남기는가"를 맡는다. 둘을 나눈 이유는 규칙은 DB 를 몰라도 되고, 부수효과는 DB 순서가
전부이기 때문이다.

**왜 모듈로 뺐나 (#148)**: REST(`api/applications.py`)와 에이전트 도구
(`agent/tools/write.py`)가 각자 이 순서를 따로 구현하고 있었고, 실제로 갈렸다 —
에이전트 쪽은 `email_logs` 행만 만들고 SQS 로 발행하지 않아 **메일이 영영 나가지
않는데 응답은 성공**이었다. 불합격 사유도 에이전트 경로에서는 남지 않았다.
규칙은 공유하면서 부수효과만 따로 쓰면 이런 식으로 조용히 갈린다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from http import HTTPStatus

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import mail
from app.models import Application, StageHistory
from app.stages import NOTIFY_STAGES, REJECTED, validate_transition

logger = logging.getLogger(__name__)


def require_reason(to_stage: str, reason: str | None) -> None:
    """불합격은 이유를 남긴다 (D8).

    나중에 "이 사람 왜 불합격이었죠?"에 답할 수 있어야 한다. 다른 단계는 사유가
    없어도 다음 단계 이름이 곧 설명이지만, 불합격은 그렇지 않다.
    """
    if to_stage == REJECTED and not (reason and reason.strip()):
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY, "불합격은 사유를 입력해야 합니다"
        )


def apply_stage_change(
    db: Session,
    application: Application,
    to_stage: str,
    changed_by: int,
    reason: str | None,
    now: datetime,
) -> int | None:
    """단계 하나를 바꾸고 이력·메일 행을 남긴다. **커밋하지 않는다.**

    단건 변경(D3)·일괄 변경(D9)·에이전트 도구가 전부 이 함수를 쓴다 — 규칙이
    여러 곳에 있으면 반드시 어긋난다. 규칙 자체는 `app/stages.py` 에만 있다.

    SQS 발행은 하지 않고 `email_logs.id` 만 돌려준다. 호출부가 **커밋한 뒤에**
    `publish_all` 로 발행해야 롤백된 건의 메시지가 큐에 남지 않는다.
    메일이 필요 없는 단계면 None.
    """
    from_stage = application.current_stage
    validate_transition(from_stage, to_stage)  # 어긋나면 StageTransitionError

    application.current_stage = to_stage
    application.updated_at = now

    db.add(
        StageHistory(
            application_id=application.id,
            from_stage=from_stage,
            to_stage=to_stage,
            changed_by=changed_by,
            reason=reason,  # D8 — 불합격 사유. 다른 단계에서는 대개 None
            created_at=now,
        )
    )

    if to_stage not in NOTIFY_STAGES:
        return None

    # 메일은 여기서 보내지 않는다 — 큐에 올리기만 하고 워커가 발송한다 (G2·G3).
    # 발송이 이 요청 안에서 일어나면 SES 가 느릴 때 단계 변경까지 같이 느려지고,
    # 발송 실패가 단계 변경을 롤백시킨다.
    return mail.create_log(
        db,
        application_id=application.id,
        to_email=application.email,
        stage=to_stage,
    ).id


def publish_all(email_log_ids: list[int]) -> int:
    """커밋이 끝난 뒤 큐에 싣는다. 발행한 건수를 돌려준다.

    큐가 죽어도 단계 변경은 이미 성공이다 — 담당자가 카드를 못 옮기는 것이 메일이
    늦는 것보다 나쁘다. 행은 `queued` 로 남으니 나중에 셀 수 있다.
    """
    published = 0
    for log_id in email_log_ids:
        try:
            mail.publish(log_id)
            published += 1
        except Exception:
            logger.exception("메일 큐 발행 실패 email_log_id=%s", log_id)
    return published
