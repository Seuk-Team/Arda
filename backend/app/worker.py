"""메일 발송 워커 (G2·G3) — `python -m app.worker` 로 뜬다.

SQS 를 long polling 으로 읽어 `email_logs` 한 행을 SES 로 보낸다.
API 프로세스와 분리된 이유는 mail.py 머리말에 있다.

재시도와 상한: 실패하면 예외를 다시 던져 메시지를 삭제하지 않는다. 큐의
가시성 타임아웃(60초)이 지나면 SQS 가 다시 준다. 큐의 RedrivePolicy 가
maxReceiveCount=3 이므로 3번째 전달까지만 오고 그 뒤에는 DLQ(arda-mail-dlq)로
빠진다. 횟수를 세는 주체는 SQS 이고, 이 코드는 그 결과를 `retry_count` ·
`status` 에 기록해 나중에 셀 수 있게 하는 쪽만 맡는다. 조용히 버리지 않는다.

**멱등**: 같은 메시지를 두 번 받아도 이미 `sent` 면 아무것도 하지 않는다.
SQS 는 at-least-once 라 중복 전달이 정상 동작이다.
"""

import json
import logging
import os
import signal
import time
from datetime import UTC, datetime
from email.utils import formataddr
from functools import lru_cache
from zoneinfo import ZoneInfo

import boto3
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.db import SessionLocal
from app.logging_conf import setup_logging
from app.models import (
    Application,
    EmailLog,
    JobPosting,
    ScheduleProposal,
    ScheduleSlot,
    User,
)

logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_REGION", "ap-northeast-2")

# 지원자용 일정 선택 링크의 베이스 (postings.py 의 공개 지원 링크와 같은 값)
PUBLIC_APP_BASE_URL = os.getenv("PUBLIC_APP_BASE_URL", "").rstrip("/")

_WEEKDAYS_KO = "월화수목금토일"

# 큐의 RedrivePolicy.maxReceiveCount 와 같은 값으로 맞춘다. 이 횟수째 전달이
# 마지막이므로, 그때 실패하면 status 를 failed 로 남기고 메시지는 DLQ 로 보낸다.
MAX_RECEIVE = 3

# 한 번에 받아올 메시지 수. 폴링 비용을 줄이려고 묶어 받는다.
BATCH_SIZE = 10

# long polling. 20 초가 SQS 최대값이고, 빈 응답 요청 수를 가장 크게 줄인다.
WAIT_SECONDS = 20

# SES 샌드박스는 초당 1통이다. 묶어 받은 메시지를 그대로 연달아 보내면 스로틀에
# 걸려 멀쩡한 메일이 재시도를 까먹는다. 발송 간격을 여기서 벌린다.
SES_MIN_INTERVAL = 1.0

# 실제로 보내지 않고 로그로만 찍는다. AWS 없이 워커 로직을 검증할 때 쓴다.
DRY_RUN = os.getenv("MAIL_DRY_RUN", "").lower() in ("1", "true", "yes")

# 회신을 받을 팀 공용 주소 (G4 결정 7). 사람이 보낸 메일은 그 사람 주소가,
# 에이전트·시스템 발송은 이 주소가 Reply-To 로 붙는다.
#
# **이 값이 비면 지원자 회신이 증발한다.** 발신은 no-reply 이고 문구는 전부
# "이 메일에 회신해 주시기 바랍니다"라고 말한다 — Reply-To 가 없으면 그 안내가
# 거짓말이 된다. 발송을 막지는 않는다(메일이 안 나가는 것이 더 나쁘다).
MAIL_REPLY_TO = os.getenv("MAIL_REPLY_TO", "").strip()

_last_sent_at = 0.0
_running = True


@lru_cache(maxsize=1)
def _sqs():
    return boto3.client("sqs", region_name=REGION)


@lru_cache(maxsize=1)
def _ses():
    return boto3.client("ses", region_name=REGION)


def _source(from_name: str | None) -> str:
    """From 헤더. 주소는 그대로 두고 **표시 이름만** 발신자에 맞춘다.

    주소까지 담당자 개인 것으로 바꾸지 않는 이유가 둘이다: 팀원 주소가 외부
    메일(gmail) 이라 그것을 From 에 넣으면 DMARC 정렬이 깨져 스팸함으로 가고,
    회사 도메인으로 바꾸려면 받을 메일함부터 있어야 한다(계약 문제다).

    표시 이름만으로도 받은편지함에 "누가 보냈는가"가 뜬다. 회신은 Reply-To 가
    그 사람에게 보낸다 — 둘을 합치면 개인 발신 계정 없이도 연락처가 성립한다.

    한글 이름은 헤더에 그대로 못 넣는다. formataddr 가 비ASCII 이름을
    MIME 인코딩(=?utf-8?b?...?=)해 준다.
    """
    address = os.environ["SES_FROM_EMAIL"]
    return formataddr((from_name, address)) if from_name else address


def _send_via_ses(
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    from_name: str | None = None,
) -> None:
    """SES 로 한 통 보낸다. 실패하면 예외가 그대로 올라간다."""
    global _last_sent_at

    if DRY_RUN:
        logger.info(
            "[DRY_RUN] 발송 생략 from=%s to=%s reply_to=%s subject=%s\n%s",
            from_name,
            to_email,
            reply_to,
            subject,
            body,
        )
        return

    # 샌드박스 발송 속도(1통/초)를 넘지 않게 간격을 벌린다
    wait = SES_MIN_INTERVAL - (time.monotonic() - _last_sent_at)
    if wait > 0:
        time.sleep(wait)

    kwargs = {
        "Source": _source(from_name),
        "Destination": {"ToAddresses": [to_email]},
        "Message": {
            "Subject": {"Data": subject, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
        },
    }
    # 빈 값을 넘기면 SES 가 거절한다 — 없으면 아예 키를 빼는 쪽이 맞다
    if reply_to:
        kwargs["ReplyToAddresses"] = [reply_to]
    resp = _ses().send_email(**kwargs)
    _last_sent_at = time.monotonic()

    # SES 가 준 MessageId 를 남긴다. 스키마에 넣을 컬럼이 없어 로그로만 갖는다 —
    # "보냈는데 안 왔다"는 문의가 오면 이 값으로 SES 쪽을 추적한다.
    logger.info("SES 수락 message_id=%s", resp.get("MessageId"))


def _format_kst(dt: datetime) -> str:
    """확정 시각을 지원자가 읽을 한국 시간 문자열로. 예: 2026-09-07(월) 14:00"""
    local = dt.astimezone(ZoneInfo("Asia/Seoul"))
    return f"{local:%Y-%m-%d}({_WEEKDAYS_KO[local.weekday()]}) {local:%H:%M}"


def _interview_at(db: Session, application_id: int) -> str | None:
    """{면접일시} 자리에 넣을 문자열 (일정 자동화, ADR-0016).

    라이브 제안이 있으면 선택 링크를, 확정됐으면 확정 시각을 싣는다.
    둘 다 아니면 None → mail.render 가 기존 "별도 안내" 로 채운다.
    """
    proposal = db.scalar(
        select(ScheduleProposal)
        .where(ScheduleProposal.application_id == application_id)
        .where(ScheduleProposal.status.in_(("proposed", "confirmed")))
        .order_by(ScheduleProposal.created_at.desc())
        .limit(1)
    )
    if proposal is None:
        return None

    if proposal.status == "confirmed" and proposal.confirmed_slot_id is not None:
        slot = db.get(ScheduleSlot, proposal.confirmed_slot_id)
        if slot is not None:
            return _format_kst(slot.start_at)
        return None

    # proposed — 만료 전이면 선택 링크 안내
    if proposal.expires_at is not None and proposal.expires_at <= datetime.now(UTC):
        return None
    return (
        "아래 링크에서 원하시는 시간을 직접 선택해 주세요.\n"
        f"일정 선택 링크: {PUBLIC_APP_BASE_URL}/schedule/{proposal.token}"
    )

def _context(db: Session, log: EmailLog) -> tuple[str, str, str | None]:
    """문구에 채울 지원자명·공고명·면접일시를 읽는다."""
    application = db.get(Application, log.application_id)
    if application is None:
        raise LookupError(f"지원서를 찾을 수 없습니다: id={log.application_id}")

    posting = db.get(JobPosting, application.job_posting_id)

    # 면접일시는 interview 문구에만 자리가 있다 — 다른 단계는 조회를 건너뛴다
    interview_at = (
        _interview_at(db, application.id) if log.stage == "interview" else None
    )
    return application.name, posting.title if posting else "", interview_at


def _actor(db: Session, log: EmailLog) -> tuple[str | None, str | None]:
    """발송 주체의 (이름, 메일). 서명과 Reply-To 가 이 값으로 갈린다 (G4).

    주체가 지워진 계정이거나 system 이면 둘 다 None 이다 — 그때는 팀 서명·팀
    회신 주소로 내려간다.
    """
    if log.actor_id is None:
        return None, None
    actor = db.get(User, log.actor_id)
    if actor is None:
        return None, None
    return actor.name, actor.email


def _reply_to(log: EmailLog, actor_email: str | None) -> str | None:
    """회신 주소. 사람이 보낸 것이면 그 사람에게 답장이 가야 한다.

    에이전트·시스템 발송은 답장을 받을 개인이 없으므로 팀 공용 주소로 보낸다.
    """
    if log.actor_kind == "human" and actor_email:
        return actor_email
    return MAIL_REPLY_TO or None

def handle(db: Session, email_log_id: int, receive_count: int = 1) -> None:
    """메시지 한 건을 처리한다. 실패하면 예외를 다시 던진다(= 메시지를 안 지운다)."""
    log = db.get(EmailLog, email_log_id)

    if log is None:
        # 발행부의 커밋보다 메시지가 먼저 도착했을 수 있다(mail.enqueue 주석 참고).
        # 가시성 타임아웃 뒤 다시 받으면 대개 보인다. 끝내 없으면 DLQ 로 간다.
        raise LookupError(f"email_logs 행이 아직 없습니다: id={email_log_id}")

    if log.status == "sent":
        logger.info("이미 발송됨 — 건너뜀 email_log_id=%s", email_log_id)
        return  # 멱등 — 같은 메시지를 두 번 받아도 두 번 보내지 않는다

    if log.status == "failed":
        # 상한을 넘겨 이미 접은 건이다. 다시 보내지 않는다.
        logger.warning("이미 실패 처리됨 — 건너뜀 email_log_id=%s", email_log_id)
        return

    try:
        actor_name, actor_email = _actor(db, log)
        # From 표시 이름은 본문 서명과 같은 문자열을 쓴다 (mail.sender_name).
        # 받은편지함의 이름과 본문 끝의 서명이 다르면 지원자가 누구에게 연락해야
        # 하는지 헷갈린다.
        from_name = mail.sender_name(log.stage, log.actor_kind, actor_name)
        if log.body is not None:
            # 확정 본문이 있는 행(수동·에이전트 발송)은 **다시 렌더하지 않는다.**
            # 사람이 보고 승인한 그 문구가 그대로 나가야 한다 — 그 사이에 템플릿이
            # 바뀌었더라도 승인된 것과 다른 메일이 나가면 안 된다.
            subject, body = log.subject or "", log.body
        else:
            subject, body = mail.render(
                db,
                log.stage,
                *_context(db, log),
                actor_kind=log.actor_kind,
                actor_name=actor_name,
            )
        _send_via_ses(
            log.to_email, subject, body, _reply_to(log, actor_email), from_name
        )
        log.status = "sent"
        log.sent_at = datetime.now(UTC)
        logger.info("발송 완료 email_log_id=%s stage=%s", email_log_id, log.stage)
    except Exception:
        log.retry_count += 1
        # 이번이 마지막 전달이면(다음은 DLQ) 조용히 버리지 않고 failed 로 남긴다.
        if receive_count >= MAX_RECEIVE:
            log.status = "failed"
            logger.exception(
                "발송 최종 실패 — failed 로 기록 email_log_id=%s", email_log_id
            )
        else:
            logger.exception(
                "발송 실패 — 재시도 예정 email_log_id=%s (%s/%s)",
                email_log_id,
                receive_count,
                MAX_RECEIVE,
            )
        raise  # 예외를 다시 던져 SQS 가 재전달·DLQ 이동을 하게 둔다
    finally:
        db.commit()

def _process(message: dict) -> None:
    """메시지 하나를 세션 하나로 처리한다."""
    body = json.loads(message["Body"])
    email_log_id = int(body["email_log_id"])
    receive_count = int(message.get("Attributes", {}).get("ApproximateReceiveCount", 1))

    db = SessionLocal()
    try:
        handle(db, email_log_id, receive_count)
    finally:
        db.close()

def poll_once(queue_url: str) -> int:
    """한 번 폴링해 받은 만큼 처리한다. 처리에 성공한 건수를 돌려준다."""
    resp = _sqs().receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=BATCH_SIZE,
        WaitTimeSeconds=WAIT_SECONDS,
        AttributeNames=["ApproximateReceiveCount"],
    )

    done = 0
    for message in resp.get("Messages", []):
        try:
            _process(message)
        except Exception:
            # 로그는 handle 안에서 이미 남겼다. 여기서는 메시지를 지우지 않는 것이
            # 핵심이다 — 지우지 않으면 SQS 가 알아서 다시 준다.
            logger.warning("메시지 처리 실패 — 큐에 남긴다")
            continue

        _sqs().delete_message(
            QueueUrl=queue_url, ReceiptHandle=message["ReceiptHandle"]
        )
        done += 1

    return done

def _stop(signum, frame) -> None:
    global _running
    logger.info("종료 신호 수신 — 폴링을 멈춘다 (signal=%s)", signum)
    _running = False

def main() -> None:
    setup_logging()

    queue_url = os.getenv("SQS_QUEUE_URL", "")
    if not queue_url:
        raise SystemExit("SQS_QUEUE_URL 이 없습니다. backend/.env 를 확인하세요")
    if not DRY_RUN and not os.getenv("SES_FROM_EMAIL"):
        raise SystemExit("SES_FROM_EMAIL 이 없습니다. backend/.env 를 확인하세요")

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    logger.info("메일 워커 시작 queue=%s dry_run=%s", queue_url, DRY_RUN)
    while _running:
        try:
            poll_once(queue_url)
        except Exception:
            # 폴링 자체가 터지는 것은 대개 네트워크·자격증명 문제다. 죽지 말고
            # 잠깐 쉬었다 다시 시도한다.
            logger.exception("폴링 실패 — 5 초 뒤 재시도")
            time.sleep(5)

    logger.info("메일 워커 종료")


if __name__ == "__main__":
    main()