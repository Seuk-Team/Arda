"""SQS 로 메일 큐 발행 (ADR-0035 Phase 3f · 기존 mail.py 로직 이관).

워커(app.shared.worker) 가 이 큐를 소비해 SES 로 보낸다. 기존 흐름 그대로.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache

import boto3

from app.ports.output.mail_dispatcher_port import MailDispatcher

logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_REGION", "ap-northeast-2")


@lru_cache(maxsize=1)
def _sqs_client():
    """지연 생성 · 첫 사용 시. 임포트 시점에 만들면 AWS 없는 환경에서 터진다."""
    return boto3.client("sqs", region_name=REGION)


class SqsMailDispatcher(MailDispatcher):
    def publish(self, email_log_id: int) -> None:
        queue_url = os.getenv("SQS_QUEUE_URL", "")
        _sqs_client().send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps({"email_log_id": email_log_id}),
        )
        logger.info("메일 큐 발행 email_log_id=%s (SQS)", email_log_id)


def warm_up() -> None:
    """boto3 클라이언트를 미리 만들어 첫 요청 지연을 없앤다."""
    try:
        _sqs_client()
    except Exception:
        logger.warning("SQS 클라이언트 예열 실패", exc_info=True)
