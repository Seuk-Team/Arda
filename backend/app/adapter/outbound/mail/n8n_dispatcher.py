"""n8n 웹훅으로 메일 발행 (ADR-0030 · ADR-0035 Phase 3f).

n8n 워크플로가 웹훅을 받고 우리 내부 API `/internal/email-logs/{id}/render` 를
불러 본문·수신자를 가져간 뒤 SMTP 로 발송, 그 결과를 `/result` 로 되돌린다.
"""

from __future__ import annotations

import logging
import os

from app.ports.output.mail_dispatcher_port import MailDispatcher

logger = logging.getLogger(__name__)

# compose 안 통신이라 http · 인증 없음. Basic Auth 는 편집 화면 접근용.
_N8N_WEBHOOK_URL_DEFAULT = "http://n8n:5678/webhook/stage-changed"


class N8nMailDispatcher(MailDispatcher):
    def publish(self, email_log_id: int) -> None:
        # 지연 import — worker 흐름이면 httpx 자체를 안 탄다
        import httpx

        url = (
            os.getenv("N8N_WEBHOOK_URL", _N8N_WEBHOOK_URL_DEFAULT).strip()
            or _N8N_WEBHOOK_URL_DEFAULT
        )
        resp = httpx.post(
            url,
            json={"email_log_id": email_log_id},
            timeout=5.0,
        )
        resp.raise_for_status()
        logger.info("메일 큐 발행 email_log_id=%s (n8n webhook)", email_log_id)
