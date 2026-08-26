"""단계 변경 → 메일 큐 발행 (G2).

**여기서 SES 를 호출하지 않는다.** 단계 변경 API 안에서 메일을 직접 보내면
SES 가 느릴 때 담당자 화면이 같이 멈추고, SES 가 죽으면 단계 변경까지 실패한다.
이 모듈은 `email_logs` 행을 `queued` 로 만들고 그 id 만 SQS 에 실어 보낸다.
실제 발송은 `app.worker` 가 한다.

문구는 docs/00_overview/email-templates.md (G1 산출물) 를 그대로 옮긴 것이다.
문서가 기준이고 이 파일은 사본이다 — 문구를 고칠 일이 생기면 문서를 먼저 고친다.
(런타임에 문서를 읽지 않는 이유: Dockerfile 이 `app/` 만 이미지에 넣는다.
 컨테이너 안에 docs/ 가 없다.)
"""

import json
import logging
import os
from functools import lru_cache

import boto3

from app.models import EmailLog

logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_REGION", "ap-northeast-2")

# 회사명은 스키마에 없다. 01-erd.md 에 회사 테이블이 없어 환경변수로 둔다.
COMPANY_NAME = os.getenv("COMPANY_NAME", "Arda")

# 면접 일시도 스키마에 없다 (job_postings·applications 어디에도 컬럼이 없다).
# 문구에서 그 자리는 비워 둘 수 없으므로 아래 문자열로 채우고, 컬럼이 생기면 바꾼다.
INTERVIEW_AT_UNKNOWN = "별도 안내"


@lru_cache(maxsize=1)
def _sqs():
    """클라이언트를 임포트 시점이 아니라 첫 사용 시점에 만든다.

    모듈 최상단에서 만들면 AWS 설정이 없는 환경(테스트·CI)에서 임포트만 해도 터진다.
    s3.py 와 같은 방식이다.
    """
    return boto3.client("sqs", region_name=REGION)


def warm_up() -> None:
    """boto3 클라이언트를 미리 만들어 둔다.

    클라이언트 생성이 2 초쯤 걸린다(botocore 가 서비스 모델 JSON 을 읽는다).
    지연 생성만 해 두면 **재기동 후 첫 단계 변경 요청 하나가 그 2 초를 뒤집어쓴다** —
    이 기능이 애초에 없애려던 지연이 자리만 옮겨 되살아난다. 부팅 때 미리 만든다.

    실패해도 무시한다. 어차피 첫 호출 때 다시 만들고, 여기서 죽으면 AWS 가 없는
    환경에서 앱이 아예 안 뜬다.
    """
    try:
        _sqs()
    except Exception:
        logger.warning("SQS 클라이언트 예열 실패 — 첫 호출 때 다시 만든다", exc_info=True)


def _queue_url() -> str:
    """큐 URL 을 호출 시점에 읽는다.

    모듈 상수로 굳히면 테스트에서 환경변수를 바꿔도 안 먹는다.
    """
    return os.getenv("SQS_QUEUE_URL", "")


# ── 문구 (docs/00_overview/email-templates.md 사본) ────────────────────
#
# 단계 ↔ 템플릿 대응. NOTIFY_STAGES(app/stages.py) 와 C4 의 applied 를 합친 것이다.
#   applied   → 접수 확인          (C4)
#   interview → ① 서류 합격·면접 안내
#   accepted  → ③ 최종 합격
#   rejected  → ④ 불합격
#   screening → 문구 없음. 내부 검토 단계라 지원자에게 보내지 않는다.
#
# 문서의 ② "면접 결과 합격" 은 대응하는 단계가 없다. 01-erd.md 의 단계는 5개뿐이고
# 면접 라운드가 하나라 "면접 → 다음 전형" 에 해당하는 값이 없다. 이슈로 남긴다.
_TEMPLATES: dict[str, tuple[str, str]] = {
    "interview": (
        "[{회사명}] {공고명} 서류 전형 합격 및 면접 안내",
        """{지원자명} 님, 안녕하세요.

{회사명} {공고명} 포지션에 지원해 주셔서 감사합니다.
제출해 주신 서류를 검토한 결과, 다음 전형인 면접에 참여하실 수 있게 되었음을 안내드립니다.

면접 일시: {면접일시}

면접 장소와 준비물 등 세부 안내는 별도로 다시 연락드리겠습니다.
일정 조율이 필요하신 경우 이 메일에 회신해 주시기 바랍니다.

다시 한번 서류 합격을 축하드리며, 면접에서 뵙겠습니다.

{회사명} 채용 담당자 드림""",
    ),
    "accepted": (
        "[{회사명}] {공고명} 최종 합격 안내",
        """{지원자명} 님, 안녕하세요.

{회사명} {공고명} 포지션의 모든 채용 전형을 거쳐 최종 합격하셨음을 안내드립니다.
그동안 전형에 성실히 임해 주셔서 감사드리며, 진심으로 축하드립니다.

입사 절차와 필요 서류 등 세부 안내는 별도로 다시 연락드리겠습니다.
문의 사항이 있으시면 이 메일에 회신해 주시기 바랍니다.

{회사명} 채용 담당자 드림""",
    ),
    "rejected": (
        "[{회사명}] {공고명} 채용 전형 결과 안내",
        """{지원자명} 님, 안녕하세요.

{회사명} {공고명} 포지션에 지원해 주셔서 감사합니다.
신중히 검토한 결과, 이번 채용 전형에서는 함께하지 못하게 되었음을 안내드립니다.

귀한 시간을 내어 지원해 주신 점 다시 한번 감사드리며,
다음 기회에 좋은 인연으로 다시 뵙기를 바랍니다.

{회사명} 채용 담당자 드림""",
    ),
}


class UnknownStageTemplate(LookupError):
    """단계에 대응하는 문구가 없다. 워커가 잡아 failed 로 남긴다."""


def render(stage: str, applicant_name: str, posting_title: str) -> tuple[str, str]:
    """단계에 맞는 (제목, 본문) 을 만든다. 문구를 새로 지어내지 않는다."""
    tpl = _TEMPLATES.get(stage)
    if tpl is None:
        raise UnknownStageTemplate(f"'{stage}' 단계에 해당하는 메일 문구가 없습니다")

    values = {
        "지원자명": applicant_name,
        "공고명": posting_title,
        "회사명": COMPANY_NAME,
        "면접일시": INTERVIEW_AT_UNKNOWN,
    }
    subject, body = tpl
    return subject.format(**values), body.format(**values)


def enqueue(db, application_id: int, to_email: str, stage: str) -> EmailLog:
    """`email_logs` 행을 만들고 그 id 를 큐에 싣는다.

    **커밋하지 않는다.** 단계 변경·지원서 저장과 같은 트랜잭션에 묶여야 하므로
    커밋은 호출부가 한다.

    큐 발행이 먼저이고 커밋이 나중이라, 워커가 커밋 전에 메시지를 받을 수 있다.
    그때는 워커가 행을 못 찾고 예외를 던져 가시성 타임아웃 뒤 다시 받는다
    (worker.handle 참고). 호출부가 롤백하면 그 메시지는 재전달을 다 쓰고 DLQ 로 간다.
    """
    log = EmailLog(
        application_id=application_id,
        to_email=to_email,
        stage=stage,
        status="queued",
        retry_count=0,
    )
    db.add(log)
    db.flush()  # id 가 있어야 큐에 실어 보낸다

    _sqs().send_message(
        QueueUrl=_queue_url(),
        MessageBody=json.dumps({"email_log_id": log.id}),
    )
    logger.info("메일 큐 발행 email_log_id=%s stage=%s", log.id, stage)
    return log
