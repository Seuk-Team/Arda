"""메일 SMTP 폴백 — n8n 이 멈춰도 통보가 나간다 (2026-09-16).

[ADR-0031](../../../docs/03_decision/0031-aws-최소화.md) 이 "워커는 SMTP 20줄로
비상 폴백만" 이라고 적었고, [ADR-0036](../../../docs/03_decision/0036-SQS-워커-폐기.md)
이 SQS 워커 컨테이너를 내리면서 그 후속을 남겼다. 이 파일이 그 후속이다.

## 왜 필요한가

지금 발송은 **API → n8n → SMTP 한 경로뿐**이다. n8n 이 멈추면 합격·불합격 통보가
통째로 멎는데, 그 사실이 드러나는 것은 지원자가 "연락이 없다" 고 말할 때다.

## 두 가지를 한다

1. **즉시 폴백** — `mail.publish` 가 n8n 에 못 실으면 여기서 바로 SMTP 로 보낸다.
2. **밀린 것 쓸어 담기** (`flush_pending`) — n8n 이 웹훅은 받고(200) 그 뒤에 죽으면
   행은 `queued` 로 남는다. 그건 발행 시점에 못 잡으므로 나중에 훑어서 보낸다.
   **API 프로세스가 몇 분마다 스스로 돈다** (2026-09-17, `start_flush_loop`) — 전에는
   사람이 명령을 쳐야 했고, 그래서 사람이 모르는 동안은 아무도 안 보냈다.

## 보내는 규칙은 워커와 같다

렌더·From 표시 이름·회신 주소를 `worker` 의 함수로 그대로 쓴다. **확정 본문이 있는
행은 다시 렌더하지 않는다** — 사람이 보고 승인한 문구가 그대로 나가야 한다.
"""

from __future__ import annotations

import logging
import os
import smtplib
import threading
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EmailLog

logger = logging.getLogger(__name__)

# n8n 이 쓰는 것과 같은 계정이다(지메일 앱 비밀번호 — ADR-0031). 값이 없으면
# 폴백이 꺼진 것으로 본다 — **조용히 다른 데로 보내지 않는다.**
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "1").strip() not in {"0", "false", "False"}

# 밀린 것으로 보는 시간. n8n 이 정상일 때 몇 초면 끝나므로 10분이면 충분히 늦다.
PENDING_AFTER_MIN = int(os.getenv("MAIL_PENDING_AFTER_MIN", "10"))

# 한 번에 쓸어 담을 상한. 장애가 길었으면 여러 번 돌린다 — 한 번에 수백 통을
# 밀어 넣으면 지메일이 계정을 잠근다.
FLUSH_LIMIT = int(os.getenv("MAIL_FLUSH_LIMIT", "50"))

# 쓸어 담기를 스스로 도는 간격(분). 0 이면 끈다 — 그때는 예전처럼 손으로 돌린다.
FLUSH_INTERVAL_MIN = float(os.getenv("MAIL_FLUSH_INTERVAL_MIN", "5"))

# 쓸어 담기가 같은 행을 몇 번까지 다시 보내 보나. 넘으면 `failed` 로 접는다 —
# 주소가 틀렸거나 계정이 잠긴 행을 5분마다 영원히 두드리지 않게. 접힌 행은
# n8n 이 접은 것과 같이 **사람이 보고 판단한다.**
FLUSH_MAX_RETRY = int(os.getenv("MAIL_FLUSH_MAX_RETRY", "3"))


def available() -> bool:
    """폴백을 쓸 수 있는가. **설정이 없으면 없는 대로 둔다.**"""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASSWORD)


def _from_email() -> str:
    return os.getenv("SES_FROM_EMAIL", "").strip() or SMTP_USER


def send_message(
    to_email: str,
    subject: str,
    body: str,
    *,
    reply_to: str | None = None,
    from_name: str | None = None,
) -> None:
    """SMTP 로 한 통 보낸다. 실패하면 예외를 올린다 — 삼키지 않는다."""
    if not available():
        raise RuntimeError("SMTP 설정이 없습니다 (SMTP_HOST·SMTP_USER·SMTP_PASSWORD)")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, _from_email())) if from_name else _from_email()
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
        if SMTP_STARTTLS:
            smtp.starttls()
        smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)


def send_log(db: Session, log: EmailLog) -> bool:
    """이 행을 SMTP 로 보내고 결과를 기록한다. 보냈으면 True.

    **이미 보낸 행은 건드리지 않는다** — 폴백이 두 번째 사본을 보내면 지원자는
    같은 통보를 두 번 받는다. 그건 안 보내는 것만큼이나 나쁘다.
    """
    from app.shared import mail
    from app.hiring.company import name_for
    from app.shared.worker import _actor, _context, _reply_to

    if log.status == "sent":
        return False

    actor_name, actor_email = _actor(db, log)
    if log.body is not None:
        subject, body = log.subject or "", log.body
    else:
        subject, body = mail.render(
            db,
            log.stage,
            *_context(db, log),
            actor_kind=log.actor_kind,
            actor_name=actor_name,
        )

    try:
        send_message(
            log.to_email,
            subject,
            body,
            reply_to=_reply_to(log, actor_email),
            from_name=mail.sender_name(
                log.stage, log.actor_kind, actor_name, company_name=name_for(db)
            ),
        )
    except Exception:
        log.retry_count += 1
        logger.exception("SMTP 폴백 발송 실패 email_log_id=%s", log.id)
        db.commit()
        return False

    log.status = "sent"
    log.sent_at = datetime.now(UTC)
    # **`provider_message_id` 를 비워 둔다.** 이 칸이 비어 있으면서 `sent` 인 행이
    # "폴백으로 나갔다" 는 표시가 된다 — 나중에 n8n 로그와 대조할 때 갈린다.
    logger.warning("SMTP 폴백으로 발송함 email_log_id=%s stage=%s", log.id, log.stage)
    db.commit()
    return True


def send_log_id(email_log_id: int) -> bool:
    """세션을 직접 열어 한 건 보낸다 — `publish` 폴백이 쓰는 입구."""
    from app.db import SessionLocal

    with SessionLocal() as db:
        log = db.get(EmailLog, email_log_id)
        if log is None:
            logger.warning("SMTP 폴백: 행이 없습니다 email_log_id=%s", email_log_id)
            return False
        return send_log(db, log)


def flush_pending(db: Session, *, after_min: int | None = None, limit: int | None = None) -> dict:
    """오래 `queued` 로 남은 행들을 SMTP 로 보낸다.

    n8n 이 웹훅은 받고(200) 그 뒤에 죽으면 행이 `queued` 로 남는다 — 발행 시점에는
    성공으로 보여 폴백이 안 걸린다. 그래서 나중에 훑는 경로가 따로 필요하다.

    **`failed` 는 건드리지 않는다.** 상한을 넘겨 이미 접은 건이고, 되살리려면
    사람이 보고 판단해야 한다. n8n 이 `failed` 를 알려 온 것도 같다 — n8n 과 이
    폴백은 **같은 SMTP 계정**이라 다시 보내도 대개 같은 이유로 실패하고, n8n 쪽이
    실제로는 보낸 뒤 시간초과로 실패를 적었으면 지원자가 두 통을 받는다.

    **한 행씩 잠그고 보낸다**(`FOR UPDATE SKIP LOCKED`). `send_log` 가 행마다 커밋해
    잠금이 풀리므로, 한꺼번에 잠그면 두 번째 행부터 다른 프로세스와 겹칠 수 있다.
    프로세스가 둘이 되거나 손으로 돌린 명령과 자동 반복이 겹쳐도 같은 행을 두 번
    보내지 않는다.

    `FLUSH_MAX_RETRY` 번 보내도 안 나간 행은 `failed` 로 접는다.
    """
    after = after_min if after_min is not None else PENDING_AFTER_MIN
    cap = limit if limit is not None else FLUSH_LIMIT
    cutoff = datetime.now(UTC) - timedelta(minutes=after)

    tried: list[int] = []
    sent = 0
    given_up = 0
    while len(tried) < cap:
        query = (
            select(EmailLog)
            .where(
                EmailLog.status == "queued",
                EmailLog.created_at < cutoff,
                EmailLog.retry_count < FLUSH_MAX_RETRY,
            )
            .order_by(EmailLog.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if tried:
            # 이번 회차에 실패한 행은 queued 로 남는다 — 같은 회차에 다시 집지 않는다
            query = query.where(EmailLog.id.not_in(tried))
        log = db.scalar(query)
        if log is None:
            break
        tried.append(log.id)
        if send_log(db, log):
            sent += 1
        elif log.status == "queued" and log.retry_count >= FLUSH_MAX_RETRY:
            log.status = "failed"
            db.commit()
            given_up += 1
            logger.error(
                "SMTP 폴백 %s번 실패 — failed 로 접는다 email_log_id=%s (사람이 확인할 것)",
                FLUSH_MAX_RETRY, log.id,
            )
        else:
            db.commit()  # 잠금을 푼다

    if tried:
        logger.warning(
            "밀린 메일 %s건 중 %s건을 SMTP 폴백으로 보냈다 (%s분 이상 대기 · 접음 %s)",
            len(tried), sent, after, given_up,
        )
    return {"found": len(tried), "sent": sent, "given_up": given_up}


def start_flush_loop() -> threading.Event | None:
    """쓸어 담기를 `FLUSH_INTERVAL_MIN` 분마다 도는 스레드를 띄운다 (2026-09-17, 수택님 B1).

    API 기동 때 한 번 부른다. SMTP 설정이 없거나 간격이 0 이면 띄우지 않고 None.
    돌려준 Event 를 set 하면 멈춘다. 한 회차가 실패해도 다음 회차는 돈다.
    """
    if not available() or FLUSH_INTERVAL_MIN <= 0:
        logger.info(
            "밀린 메일 자동 쓸어 담기 꺼짐 (SMTP 설정 %s · 간격 %s분)",
            "있음" if available() else "없음", FLUSH_INTERVAL_MIN,
        )
        return None

    from app.db import SessionLocal

    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(FLUSH_INTERVAL_MIN * 60):
            try:
                with SessionLocal() as db:
                    flush_pending(db)
            except Exception:
                logger.exception("밀린 메일 자동 쓸어 담기 실패 — 다음 회차에 다시 한다")

    threading.Thread(target=loop, name="mail-flush", daemon=True).start()
    logger.info(
        "밀린 메일 자동 쓸어 담기 켜짐 — %s분마다 · %s분 넘게 queued 인 행",
        FLUSH_INTERVAL_MIN, PENDING_AFTER_MIN,
    )
    return stop


def main() -> None:  # pragma: no cover - 운영 진입점
    """`python -m app.shared.mail_smtp` — 밀린 메일을 쓸어 담는다.

    API 가 스스로 돌기 때문에(`start_flush_loop`) 평소에는 칠 일이 없다. n8n 장애를
    확인한 뒤 기다리지 않고 바로 보내고 싶을 때 손으로 한 번 돌린다.
    """
    import logging as _logging

    from app.db import SessionLocal

    _logging.basicConfig(level=_logging.INFO)
    if not available():
        logger.error("SMTP 설정이 없어 아무것도 하지 않는다")
        return
    with SessionLocal() as db:
        result = flush_pending(db)
    logger.info("밀린 메일 처리: %s", result)


if __name__ == "__main__":  # pragma: no cover
    main()
