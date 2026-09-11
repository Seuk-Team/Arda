"""면접 일정 제안 도메인 서비스 (ADR-0035 Phase 4 · UseCase 분리).

`interview/api/schedules.py` 라우터가 HTTP 파싱·응답만 맡고 제안 생성·후보 계산의
비즈니스 로직은 여기로. 자동 심사 경로 (`app.application.screening`) 도 같은 함수를
쓴다 — 담당자 REST 와 아르(자동 심사)가 같은 규칙을 공유한다.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    Application,
    EmailLog,
    InterviewerAvailability,
    ScheduleProposal,
    ScheduleSlot,
)
from app.shared import mail


class NoCandidateSlots(ValueError):
    """가용 시간이 없어 후보 슬롯을 하나도 못 만들었다. 호출부가 422 또는 폴백으로."""


def build_candidates(
    windows: list[InterviewerAvailability],
    confirmed: dict[int, list[tuple[datetime, datetime]]],
    slot_minutes: int,
    max_slots: int,
    now: datetime,
) -> list[tuple[int, datetime, datetime]]:
    """가용 시간 창을 슬롯 길이로 잘라 후보를 만든다.

    - 과거분·이미 확정된 면접과 겹치는 슬롯은 제외한다 (확정 시점에 한 번 더
      검증하지만, 어차피 안 될 선택지를 지원자에게 보여주는 것부터가 잘못이다).
    - 창 하나가 아무리 길어도 max_slots 개까지만 자른다 — 몇 달짜리 창을
      통째로 조각내는 낭비를 막는 상한이다. 전체는 마지막에 다시 자른다.
    """
    step = timedelta(minutes=slot_minutes)
    seen: set[tuple[int, datetime]] = set()
    candidates: list[tuple[int, datetime, datetime]] = []

    for w in sorted(windows, key=lambda w: w.start_at):
        made = 0
        start = w.start_at
        while start + step <= w.end_at and made < max_slots:
            end = start + step
            key = (w.interviewer_id, start)
            overlap = any(
                start < c_end and end > c_start
                for c_start, c_end in confirmed.get(w.interviewer_id, ())
            )
            if start > now and key not in seen and not overlap:
                seen.add(key)
                candidates.append((w.interviewer_id, start, end))
                made += 1
            start = end

    candidates.sort(key=lambda c: (c[1], c[0]))
    return candidates[:max_slots]


def build_proposal(
    db: Session,
    application: Application,
    interviewer_ids: list[int],
    *,
    slot_minutes: int,
    max_slots: int,
    expires_at: datetime | None,
    created_by: int,
    actor_kind: str,
    actor_id: int | None,
    now: datetime,
) -> tuple[ScheduleProposal, list[ScheduleSlot], EmailLog]:
    """제안 한 건을 만든다 — 후보 슬롯·제안 행·제안 메일 행까지. **커밋·발행은 호출부가.**

    담당자 REST(`schedules.create_proposal`)와 자동 심사(ADR-0034, `application/screening.py`)가
    같이 쓴다. 흐름: 면접관 가용 시간 → 후보 슬롯 → 기존 proposed 취소 → 제안 저장 → 메일 행.
    후보가 없으면 NoCandidateSlots — 자동 경로는 그때 사람에게 넘긴다.
    """
    windows = list(
        db.scalars(
            select(InterviewerAvailability)
            .where(InterviewerAvailability.interviewer_id.in_(interviewer_ids))
            .where(InterviewerAvailability.end_at > now)
        )
    )

    # 이미 확정된 면접(같은 면접관의 다른 지원자 포함)과 겹치면 후보에서 뺀다
    confirmed: dict[int, list[tuple[datetime, datetime]]] = {}
    rows = db.execute(
        select(ScheduleSlot.interviewer_id, ScheduleSlot.start_at, ScheduleSlot.end_at)
        .join(ScheduleProposal, ScheduleProposal.confirmed_slot_id == ScheduleSlot.id)
        .where(ScheduleProposal.status == "confirmed")
        .where(ScheduleSlot.interviewer_id.in_(interviewer_ids))
        .where(ScheduleSlot.end_at > now)
    ).all()
    for iid, s, e in rows:
        confirmed.setdefault(iid, []).append((s, e))

    candidates = build_candidates(windows, confirmed, slot_minutes, max_slots, now)
    if not candidates:
        raise NoCandidateSlots("생성 가능한 후보 슬롯이 없습니다 — 면접관 가용 시간을 확인하세요")

    # 재제안: 라이브 제안은 항상 최대 1건. 이전 것은 canceled 로 이력만 남긴다
    db.execute(
        update(ScheduleProposal)
        .where(ScheduleProposal.application_id == application.id)
        .where(ScheduleProposal.status == "proposed")
        .values(status="canceled", updated_at=now)
    )

    proposal = ScheduleProposal(
        application_id=application.id,
        # public_token(B6)과 같은 근거 — 128비트라 추측으로 맞힐 수 없다
        token=secrets.token_urlsafe(16),
        status="proposed",
        expires_at=expires_at,
        created_by=created_by,
    )
    db.add(proposal)
    db.flush()  # 슬롯이 proposal.id 를 참조한다

    slots = [
        ScheduleSlot(
            proposal_id=proposal.id,
            interviewer_id=interviewer_id,
            start_at=start,
            end_at=end,
        )
        for interviewer_id, start, end in candidates
    ]
    db.add_all(slots)

    # 제안 메일 — 워커가 stage=interview 렌더 때 라이브 제안을 보고 링크를 싣는다
    log = mail.create_log(
        db,
        application_id=application.id,
        to_email=application.email,
        stage="interview",
        actor_kind=actor_kind,  # 제안을 만든 담당자, 또는 자동 심사의 아르 (G4)
        actor_id=actor_id,
    )
    return proposal, slots, log
