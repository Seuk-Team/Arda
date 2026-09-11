"""Talent (내부 사용자) Repository Port (ADR-0035 Phase 3c).

`db.get(User, id)` 는 코드베이스에 10+ 지점에서 반복된다. 여기서부터 흡수.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from app.models import User


class TalentRepository(ABC):
    """Talent 도메인의 저장소 인터페이스."""

    @abstractmethod
    def get_user(self, user_id: int) -> User | None:
        """id 로 조회. 없으면 None."""
        ...

    @abstractmethod
    def find_users_by_ids(self, ids: Iterable[int]) -> list[User]:
        """여러 id 를 한꺼번에. 면접관 배정·일정 관련 로직에서 자주 씀."""
        ...
