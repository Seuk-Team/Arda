"""메일 발송 어댑터 (ADR-0035 Phase 3f).

SQS 워커 경로와 n8n 웹훅 경로 두 어댑터를 제공.
"""

from app.adapter.outbound.mail.n8n_dispatcher import N8nMailDispatcher
from app.adapter.outbound.mail.sqs_dispatcher import SqsMailDispatcher

__all__ = ["N8nMailDispatcher", "SqsMailDispatcher"]
