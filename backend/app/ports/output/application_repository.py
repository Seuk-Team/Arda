"""Application (지원) Repository Port (ADR-0035 Phase 1).

Application 컨텍스트의 스타 (지원 워크플로) 를 감싸는 저장소 계약. 지금은
`app.models.Application` 을 그대로 도메인 값으로 쓴다 (ADR-0035 §2 · Entity/ORM
분리 안 함). 나중에 순수 dataclass 로 뽑을 여지는 남기되 이번 Phase 에서는 안 한다.

**이 파일은 계약 (ABC) 만 둔다.** 구현은 `app/adapter/outbound/pg/application_pg_repository.py`.

Repository 를 두는 이유 두 가지:
1. `screening.py` · `stage_service.py` 같은 도메인 로직이 SQLAlchemy 세션·쿼리에
   직접 매달리지 않게 된다 — 유닛 테스트에서 Repository 를 mock 으로 바꾼다.
2. `app.models.Application` 이 71 파일에 흩어져 있는 결합을 서서히 이 자리로 수렴.
   지금은 첫 걸음일 뿐이라 필요한 메서드만 얹는다. 새 쿼리가 필요할 때마다 여기에
   추가해 나간다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models import Application


class ApplicationRepository(ABC):
    """Application 도메인의 저장소 인터페이스.

    호출자는 이 계약만 알면 된다 — 뒤에 Postgres 가 붙는지 mock 이 붙는지 몰라도 된다.
    """

    @abstractmethod
    def get(self, application_id: int) -> Application | None:
        """id 로 조회. 없으면 None."""
        ...

    @abstractmethod
    def find_agent_rejected_pending_mail(self, posting_id: int) -> list[Application]:
        """아르가 자동 불합격 처리했지만 아직 불합격 메일이 발송되지 않은 지원자들.

        `send_pending_rejections` (screening.py) 에서 마감 후 담당자가 한 번 눌러
        일괄 발송할 대상. 사람이 직접 불합격시킨 건 (`decision_source='human'`) 은
        그때 메일이 이미 갔으므로 여기서 제외한다.
        """
        ...
