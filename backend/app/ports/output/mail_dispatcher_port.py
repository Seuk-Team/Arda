"""메일 발송 큐 Port (ADR-0035 Phase 3f).

`email_logs` 행이 생긴 뒤 그 id 를 발송 경로에 실어 보내는 계약. 실제 구현은:

- `SqsMailDispatcher` (기본) : SQS 에 실어 워커가 SES 로 보낸다 (기존 흐름)
- `N8nMailDispatcher`        : n8n 워크플로 웹훅에 POST (ADR-0030)

`app.shared.mail.publish()` 가 환경변수 `MAIL_DISPATCH` 로 어느 어댑터를 쓸지
정한다. LLM Port 와 같은 패턴.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class MailDispatcher(ABC):
    """이미 커밋된 `email_logs` 행을 발송 큐에 넘긴다."""

    @abstractmethod
    def publish(self, email_log_id: int) -> None:
        """행 id 하나를 발송 파이프라인에 실어 보낸다.

        구현별 오류 정책:
        - 성공 시 조용히 반환
        - 네트워크 실패 등은 예외를 던진다 — 호출부 (stage_service.publish_all) 가
          로그로 삼킨다 (단계 변경 자체는 이미 성공이므로).
        """
        ...
