"""자동 심사 (ADR-0034, 지시서 N1) — 점수 합산 규칙과 "아르가 단계를 옮기는" 자리.

팀장 결정(2026-09-10): 서류·면접은 아르가 점수를 매기고 단계를 옮긴다. 최종 합격·
불합격만 사람이 한다. 수동 변경은 언제나 가능하고, 사람이 한 번 옮긴 지원자는
(`decision_source='human'`) 이후 자동 판정이 건드리지 않는다.

이 모듈이 맡는 것
- 가중치 읽기(`company_profile.scoring_weights`)와 세 가지 합산: 서류·면접·최종.
- 서류 판정 `decide_document`: 요약이 끝난 뒤 백그라운드에서 한 번 불린다.
  임계 이상 → applied→screening→interview(두 칸을 한 번에 건너뛸 수 없어 두 번 옮긴다),
  미만 → rejected. 이력에는 changed_by=NULL(시스템) + 점수 사유.
- 서류 합격 뒤 자동으로 붙는 것: 인적성 세션+메일, 면접관 1명 자동 배정, 일정 제안.
- 불합격 메일 일괄 발송 `send_pending_rejections`: 마감 뒤 담당자가 한 번 누른다.

규칙(전이)은 `app/application/stages.py`, 부수효과(이력·메일)는 `app/application/stage_service.py` 가 그대로
맡는다 — 여기서는 그 둘을 **순서대로 부를 뿐** 새 규칙을 만들지 않는다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.shared import mail
from app.hiring.company import get_profile
from app.models import (
    Application,
    InterviewerAssignment,
    InterviewerAvailability,
    JobPosting,
    PostingInterviewer,
    User,
)
from app.ports.output.application_repository import ApplicationRepository
from app.application.stage_service import apply_stage_change, publish_all
from app.application.stages import StageTransitionError
from app.adapter.outbound.pg.hiring_pg_repository import PgHiringRepository

logger = logging.getLogger(__name__)

# 가중치 기본값. company_profile.scoring_weights 가 이 키를 덮어쓴다.
# doc_* 세 개 = 서류 100점의 구성, itv_* 두 개 = 면접 100점의 구성,
# doc·interview = 최종 합계의 구성. 각 묶음의 합이 100이 아니어도 된다 — 합으로 나눈다.
#
# 2026-09-11 개정: 필수 요건 강조 (50→60), 우대 축소 (20→10). fit-check 24명 실측 분석:
#   요건 우수 지원자가 우대 부족만으로 탈락하는 케이스(임재원 등)가 있어
#   우대 가중치를 낮추고 요건 비중을 올렸다. 문화(30)는 그대로 두되 문화 하한 규칙을
#   `doc_score_from` 에 추가 — 요건 70 이상이면 문화 점수가 50 미만으로 내려가지 않는다.
DEFAULT_WEIGHTS: dict[str, int] = {
    "doc": 50,
    "interview": 50,
    "doc_requirements": 60,
    "doc_preferred": 10,
    "doc_culture": 30,
    "itv_answers": 70,
    "itv_truth": 30,
}

# 요건 우수(≥70) 지원자를 문화 감점 하나로 떨어뜨리지 않기 위한 하한.
# 남기훈(요건 75, 문화 35) 같은 케이스에서 회의 기반 의사결정 언급 하나로
# 문화 35 가 총점을 결정한다 — 요건이 확실하면 그 하나로 판정을 흔들지 않게 한다.
CULTURE_FLOOR_WHEN_REQUIREMENTS_HIGH = 50
REQUIREMENTS_HIGH_THRESHOLD = 70

# 등급 경계 (final_score 기준). 아래 것부터 맞는 첫 등급.
GRADE_BOUNDS: tuple[tuple[int, str], ...] = ((85, "S"), (70, "A"), (55, "B"))


# ── 합산 규칙 ─────────────────────────────────────────────────────


def weights(db: Session | None) -> dict[str, int]:
    """회사 가중치. 없거나 깨져 있으면 기본값. 키가 일부만 있어도 나머지는 기본값."""
    merged = dict(DEFAULT_WEIGHTS)
    if db is None:
        return merged
    try:
        raw = get_profile(db).scoring_weights or {}
    except Exception:  # 프로파일 표가 아직 없는 테스트 DB 등
        raw = {}
    for key, value in raw.items():
        if key in merged and isinstance(value, (int, float)) and value >= 0:
            merged[key] = int(value)
    return merged


def _weighted(parts: dict[str, int | float | None], keys: tuple[tuple[str, str], ...], w: dict) -> int | None:
    """(부분 점수, 가중치 키) 묶음의 가중 평균. **없는 부분은 빼고 나머지로 다시 나눈다.**

    진위 표본이 없는 면접은 답변 점수만으로 100 환산되는 식이다. 전부 없으면 None.
    """
    total = 0.0
    weight_sum = 0
    for part_key, weight_key in keys:
        value = parts.get(part_key)
        weight = w.get(weight_key, 0)
        if value is None or weight <= 0:
            continue
        total += float(value) * weight
        weight_sum += weight
    if weight_sum == 0:
        return None
    return int(round(total / weight_sum))


def doc_score_from(detail: dict, w: dict) -> int | None:
    """서류 100점 = 요건·우대·인재상 세 갈래의 가중 평균.

    2026-09-11: 요건 하한 규칙 — requirements ≥ 70 이면 culture 를 50 아래로 안 본다.
    요건을 확실히 갖춘 지원자를 문화 하나(예: "회의 기반 의사결정" 문구) 로 떨어뜨리지
    않기 위해서다. 문화의 상한은 손대지 않으므로 좋은 문화는 그대로 반영된다.
    """
    requirements = detail.get("requirements")
    preferred = detail.get("preferred")
    culture = detail.get("culture")

    if (
        isinstance(requirements, (int, float))
        and requirements >= REQUIREMENTS_HIGH_THRESHOLD
        and isinstance(culture, (int, float))
    ):
        culture = max(culture, CULTURE_FLOOR_WHEN_REQUIREMENTS_HIGH)

    return _weighted(
        {"requirements": requirements, "preferred": preferred, "culture": culture},
        (("requirements", "doc_requirements"), ("preferred", "doc_preferred"), ("culture", "doc_culture")),
        w,
    )


def interview_score_from(answers: int | None, truth: int | None, w: dict) -> int | None:
    """면접 100점 = 답변 대조 + 진위 일관성. 진위 표본이 없으면 답변만."""
    return _weighted(
        {"answers": answers, "truth": truth},
        (("answers", "itv_answers"), ("truth", "itv_truth")),
        w,
    )


def final_score(doc: int | None, interview: int | None, w: dict) -> float | None:
    """최종 = 서류 × w_doc + 면접 × w_interview. **둘 다 있어야** 낸다 — 면접 전에
    최종 점수가 보이면 사람이 그것을 최종으로 읽는다."""
    if doc is None or interview is None:
        return None
    weight_sum = w.get("doc", 0) + w.get("interview", 0)
    if weight_sum <= 0:
        return None
    return round((doc * w.get("doc", 0) + interview * w.get("interview", 0)) / weight_sum, 1)


def grade(score: float | None) -> str | None:
    if score is None:
        return None
    for bound, letter in GRADE_BOUNDS:
        if score >= bound:
            return letter
    return "C"


def truth_consistency(samples: dict | None) -> int | None:
    """실시간 판정 집계({"n", "truth_sum"}) → 0~100. 표본이 없으면 None."""
    if not samples:
        return None
    n = samples.get("n") or 0
    if n <= 0:
        return None
    return int(round(float(samples.get("truth_sum") or 0.0) / n))


# ── 서류 판정 ─────────────────────────────────────────────────────


def _system_user_id(db: Session, posting: JobPosting) -> int | None:
    """NOT NULL 인 created_by/assigned_by 자리에 넣을 사람. 공고를 만든 담당자가
    가장 자연스럽고, 없으면 관리자 아무나. 아무도 없으면 None(그 부수효과는 건너뛴다)."""
    if posting.created_by is not None:
        return posting.created_by
    return db.scalar(
        select(User.id).where(User.role == "admin").order_by(User.id).limit(1)
    )


def pick_interviewer(db: Session, posting: JobPosting, now: datetime) -> int | None:
    """공고 풀에서 **앞으로의 가용 시간이 있고 배정 건수가 가장 적은** 면접관 1명.

    풀이 비었거나 아무도 가용 시간이 없으면 None — 그때는 사람이 배정한다.
    같은 건수면 id 가 작은 사람(등록이 빠른 사람). 운으로 뽑지 않아 재현 가능하다.
    """
    pool = list(
        db.scalars(
            select(PostingInterviewer.user_id)
            .where(PostingInterviewer.job_posting_id == posting.id)
            .order_by(PostingInterviewer.user_id)
        )
    )
    if not pool:
        return None

    available = set(
        db.scalars(
            select(InterviewerAvailability.interviewer_id)
            .where(InterviewerAvailability.interviewer_id.in_(pool))
            .where(InterviewerAvailability.end_at > now)
            .distinct()
        )
    )
    candidates = [uid for uid in pool if uid in available]
    if not candidates:
        return None

    counts = dict(
        db.execute(
            select(InterviewerAssignment.interviewer_id, func.count())
            .where(InterviewerAssignment.interviewer_id.in_(candidates))
            .group_by(InterviewerAssignment.interviewer_id)
        ).all()
    )
    return min(candidates, key=lambda uid: (counts.get(uid, 0), uid))


def _after_pass(
    db: Session, application: Application, posting: JobPosting, now: datetime, detail: dict
) -> list[int]:
    """서류 합격 뒤 자동으로 붙는 것들. 메일 행 id 목록을 돌려준다(커밋 뒤 발행).

    각각 실패해도 단계 이동은 이미 됐다 — 한 부수효과가 다른 것을 막지 않게 따로 감싼다.
    """
    log_ids: list[int] = []
    actor_id = _system_user_id(db, posting)

    # ① 인적성 설문 — 점수에는 안 들어간다(ADR-0027). 최종 판단 전 참고.
    try:
        from app.application.api.aptitude import new_session, queue_aptitude_mail

        if actor_id is not None:
            session = new_session(db, application.id, actor_id)
            log_ids.append(
                queue_aptitude_mail(
                    db, application, posting, session,
                    actor_kind="agent", actor_name=None, actor_id=None,
                )
            )
            detail["aptitude_sent"] = True
    except Exception:
        logger.exception("자동 인적성 발송 실패: application_id=%s", application.id)
        detail["aptitude_sent"] = False

    # ② 면접관 자동 배정 → ③ 일정 제안(제안 메일이 면접 안내를 겸한다)
    interviewer_id = pick_interviewer(db, posting, now)
    detail["needs_manual_assignment"] = interviewer_id is None
    if interviewer_id is not None and actor_id is not None:
        detail["auto_interviewer_id"] = interviewer_id
        db.add(
            InterviewerAssignment(
                application_id=application.id,
                interviewer_id=interviewer_id,
                assigned_by=actor_id,
            )
        )
        db.flush()
        try:
            from app.interview.api.schedules import NoCandidateSlots, build_proposal

            _, _, log = build_proposal(
                db, application, [interviewer_id],
                slot_minutes=60, max_slots=5, expires_at=None,
                created_by=actor_id, actor_kind="agent", actor_id=None, now=now,
            )
            log_ids.append(log.id)
            return log_ids
        except NoCandidateSlots:
            detail["needs_manual_assignment"] = True
            logger.info("자동 배정했으나 후보 슬롯 없음: application_id=%s", application.id)
        except Exception:
            detail["needs_manual_assignment"] = True
            logger.exception("자동 일정 제안 실패: application_id=%s", application.id)

    # 배정·제안이 안 되면 면접 단계 안내 메일이라도 나간다 — 지원자는 기다리는 이유를 알아야 한다.
    log_ids.append(
        mail.create_log(
            db, application_id=application.id, to_email=application.email,
            stage="interview", actor_kind="agent", actor_id=None,
        ).id
    )
    return log_ids


def decide_document(db: Session, application: Application, now: datetime | None = None) -> str:
    """서류 자동 판정. `doc_score` 가 이미 저장된 뒤에 부른다. 커밋한다.

    돌려주는 값: pass · reject · hold. hold 는 "이번엔 안 옮겼다" — 점수 없음, 수동 모드,
    사람이 이미 옮김, applied 가 아님.
    """
    now = now or datetime.now(timezone.utc)
    posting = PgHiringRepository(db).get_posting(application.job_posting_id)
    score = application.doc_score

    if (
        posting is None
        or score is None
        or application.decision_source == "human"
        or application.current_stage != "applied"
    ):
        application.doc_decision = "hold"
        db.commit()
        return "hold"

    if posting.screening_mode != "auto":
        application.doc_decision = "hold"
        application.doc_decided_at = now
        db.commit()
        return "hold"

    threshold = int(posting.pass_threshold)
    detail = dict(application.doc_score_detail or {})
    detail["threshold"] = threshold
    log_ids: list[int] = []

    try:
        if score >= threshold:
            reason = f"아르 서류 심사 통과 — {score}점 (기준 {threshold}점)"
            # 전진은 한 칸씩만(stages.py). 심사 중(screening)을 거쳐 면접으로.
            apply_stage_change(db, application, "screening", None, reason, now, notify=False, actor_kind="agent")
            apply_stage_change(db, application, "interview", None, reason, now, notify=False, actor_kind="agent")
            application.doc_decision = "pass"
            log_ids = _after_pass(db, application, posting, now, detail)
        else:
            reason = f"아르 서류 심사 불합격 — {score}점 (기준 {threshold}점). 안내 메일은 마감 뒤 일괄 발송"
            apply_stage_change(db, application, "rejected", None, reason, now, notify=False, actor_kind="agent")
            application.doc_decision = "reject"
    except StageTransitionError:
        logger.exception("자동 판정 전이 실패: application_id=%s", application.id)
        db.rollback()
        application.doc_decision = "hold"
        db.commit()
        return "hold"

    application.doc_score_detail = detail
    application.doc_decided_at = now
    db.commit()
    publish_all(log_ids)
    logger.info(
        "screening_decided",
        extra={"application_id": application.id, "score": score, "threshold": threshold,
               "decision": application.doc_decision},
    )
    return application.doc_decision


def send_pending_rejections(
    db: Session,
    posting_id: int,
    *,
    application_repo: "ApplicationRepository | None" = None,
) -> int:
    """아르가 불합격으로 옮겼지만 아직 메일이 안 나간 지원자에게 불합격 메일을 만든다.

    사람이 직접 불합격시킨 건은 그때 메일이 이미 갔으므로 대상이 아니다. 이미 rejected
    메일 행이 있는 사람은 건너뛴다 — 두 번 눌러도 두 번 안 간다.

    조회는 `ApplicationRepository` 로 위임한다 (ADR-0035 Phase 1). `application_repo`
    를 넣으면 그것을 쓰고, 없으면 Postgres 구현으로 기본값. 이 인자는 **유닛 테스트가
    DB 없이 이 경로를 격리 검증**하기 위한 자리다 — 프로덕션 호출자는 넣지 않는다.
    """
    if application_repo is None:
        from app.adapter.outbound.pg.application_pg_repository import (
            PgApplicationRepository,
        )

        application_repo = PgApplicationRepository(db)

    rows = application_repo.find_agent_rejected_pending_mail(posting_id)
    log_ids = [
        mail.create_log(
            db, application_id=a.id, to_email=a.email, stage="rejected",
            actor_kind="agent", actor_id=None,
        ).id
        for a in rows
    ]
    db.commit()
    # 발행 실패는 행이 queued 로 남아 나중에 셀 수 있다(publish_all 주석). 돌려주는 값은
    # "이번에 만든 메일 수" — 발행 성공 수로 돌려주면 큐가 잠깐 죽었을 때 0 이 되어
    # 담당자가 아무도 안 걸렸다고 오해한다.
    if log_ids:
        publish_all(log_ids)
    return len(log_ids)
