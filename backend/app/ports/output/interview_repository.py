"""Interview (면접) Repository Port (ADR-0035 Phase 3a).

Interview 컨텍스트의 스타 (InterviewSession) 를 감싸는 저장소 계약.

Application Repository 와 같은 패턴이다 — SQLAlchemy 세션·쿼리 조립이 도메인 로직
(screening.latest_interview_score · interview_scoring.score_interview 등) 에서 빠지면
mock 저장소로 격리 검증이 가능해진다.

새 쿼리가 필요할 때마다 여기 메서드를 추가해 나간다. 현재는 최소 두 개만 열어 둔다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import InterviewSession


class InterviewRepository(ABC):
    """Interview 도메인의 저장소 인터페이스."""

    @abstractmethod
    def get_session(self, session_id: int) -> InterviewSession | None:
        """id 로 조회. 없으면 None."""
        ...

    @abstractmethod
    def latest_ai_score_for_application(self, application_id: int) -> int | None:
        """지원자의 가장 최근 끝난 면접의 AI 점수. 없으면 None.

        여러 면접이 있을 수 있고 — 재면접·다른 공고 — 의미가 있는 것은 **가장 최근
        끝난 것 하나**다. `ended_at` 이 NULL 인 경우가 끼면 id 역순으로 갈라진다.
        """
        ...
