"""app.models · 도메인 엔티티 패키지 (ADR-0035 Phase 2).

**옛 코드는 그대로**: `from app.models import User, JobPosting, Application, ...` 계속 동작.
새 코드는 컨텍스트 파일에서 직접 import 할 수 있다:
    from app.models.application import Application, EmailLog
    from app.models.hiring import JobPosting

Bounded Context 배치는 ADR-0035 §3 참조.
"""

from __future__ import annotations

# 상수 (컨텍스트 전역)
from app.models.constants import (
    APPLICATION_SOURCES,
    DECISION_SOURCES,
    DOC_DECISIONS,
    DOC_TYPES,
    EMAIL_ACTOR_KINDS,
    EMAIL_LOG_STAGES,
    EMAIL_STATUSES,
    FILE_KINDS,
    POSTING_STATUSES,
    PROPOSAL_STATUSES,
    PUBLICATION_STATUSES,
    ROLES,
    SCREENING_MODES,
    STAGES,
    TEMPLATE_STAGES,
    _in,
)

# 컨텍스트별 엔티티 — SQLAlchemy Base 가 configure 되기 전에 모두 import 되도록
# 여기서 한꺼번에 끌어들인다.
from app.models.talent import User
from app.models.hiring import JobPosting, PostingInterviewer, CompanyProfile, EmailTemplate
from app.models.application import Application, StageHistory, Evaluation, ApplicationNote, File, EmailLog, AptitudeSession, AptitudeAnswer
from app.models.interview import InterviewerAssignment, InterviewerAvailability, ScheduleProposal, ScheduleSlot, InterviewSession, InterviewTurn, InterviewFinding
from app.models.shared import AgentTrace, DocumentAnchor, ChainPublication

__all__ = [
    # 상수
    "APPLICATION_SOURCES",
    "DECISION_SOURCES",
    "DOC_DECISIONS",
    "DOC_TYPES",
    "EMAIL_ACTOR_KINDS",
    "EMAIL_LOG_STAGES",
    "EMAIL_STATUSES",
    "FILE_KINDS",
    "POSTING_STATUSES",
    "PROPOSAL_STATUSES",
    "PUBLICATION_STATUSES",
    "ROLES",
    "SCREENING_MODES",
    "STAGES",
    "TEMPLATE_STAGES",
    "_in",
    # 엔티티 (컨텍스트 순)
    "User",
    "JobPosting",
    "PostingInterviewer",
    "CompanyProfile",
    "EmailTemplate",
    "Application",
    "StageHistory",
    "Evaluation",
    "ApplicationNote",
    "File",
    "EmailLog",
    "AptitudeSession",
    "AptitudeAnswer",
    "InterviewerAssignment",
    "InterviewerAvailability",
    "ScheduleProposal",
    "ScheduleSlot",
    "InterviewSession",
    "InterviewTurn",
    "InterviewFinding",
    "AgentTrace",
    "DocumentAnchor",
    "ChainPublication",
]
