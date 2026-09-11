"""Hiring (채용) Repository Port (ADR-0035 Phase 3b).

Hiring 컨텍스트의 스타 (JobPosting) 를 감싸는 저장소 계약.

지금은 id 조회·id 목록 조회 두 개만. `db.get(JobPosting, id)` 가 코드베이스에서
가장 많이 반복되는 쿼리 패턴 (약 15개 지점) 이라 여기부터 흡수한다.

새 메서드는 필요할 때 추가한다 — 지금은 최소를 만들고, 실제 호출자 리팩터는 각
도메인 오너가 점진적으로.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.models import JobPosting


class HiringRepository(ABC):
    """Hiring 도메인의 저장소 인터페이스."""

    @abstractmethod
    def get_posting(self, posting_id: int) -> JobPosting | None:
        """id 로 공고 조회. 없으면 None."""
        ...

    @abstractmethod
    def find_postings_by_ids(self, ids: Iterable[int]) -> list[JobPosting]:
        """여러 id 를 한꺼번에 조회. 순서는 보장하지 않는다.

        지원자 포털에서 여러 지원의 공고 제목을 한 번에 붙일 때 쓴다
        (applicant_auth.py 의 지원 목록 렌더링).
        """
        ...
