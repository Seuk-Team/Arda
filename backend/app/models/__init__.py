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

# ApplicationEmbedding 은 pgvector 확장이 있을 때만 정의된다 (application.py 안의
# `if Vector is not None:` 블록). 확장이 없는 환경에선 이 이름을 노출하지 않는다 —
# `embedder._embedding_table()` 이 `from app.models import ApplicationEmbedding` 을
# try/except 로 감싸 그때 `EmbeddingUnavailable` 로 변환한다. 여기서 None 으로
# 채워 두면 그 감지가 뚫려 downstream 에서 이상한 에러가 뜬다.
# EMBEDDING_DIM 은 항상 안전하게 노출 (application.py 안에서 모듈 상수).
from app.models.application import EMBEDDING_DIM
try:
    from app.models.application import ApplicationEmbedding  # type: ignore[attr-defined]
except ImportError:
    pass

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
    # 조건부 (pgvector 확장 있을 때만)
    "ApplicationEmbedding",
    "EMBEDDING_DIM",
]
