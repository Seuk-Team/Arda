"""단계 변경 → 메일 큐 발행 (G2).

**여기서 SES 를 호출하지 않는다.** 단계 변경 API 안에서 메일을 직접 보내면
SES 가 느릴 때 담당자 화면이 같이 멈추고, SES 가 죽으면 단계 변경까지 실패한다.
이 모듈은 `email_logs` 행을 `queued` 로 만들고 그 id 만 SQS 에 실어 보낸다.
실제 발송은 `app.worker` 가 한다.

문구는 docs/00_overview/email-templates.md (G1 산출물) 를 그대로 옮긴 것이다.
**문서와 이 파일의 `_TEMPLATES` 는 이제 "기본값"이다** (G4). 운영 문구는 설정
화면에서 편집하고, 저장된 오버라이드(`email_templates` 테이블)가 우선한다 —
`get_template` 참고. 기본 문구를 고칠 일이 생기면 여전히 문서를 먼저 고친다.
(런타임에 문서를 읽지 않는 이유: Dockerfile 이 `app/` 만 이미지에 넣는다.
 컨테이너 안에 docs/ 가 없다.)
"""

import json
import logging
import os
import re
from functools import lru_cache

import boto3

from app.models import EmailLog, EmailTemplate

logger = logging.getLogger(__name__)

REGION = os.getenv("AWS_REGION", "ap-northeast-2")

# 회사명은 스키마에 없다. 01-erd.md 에 회사 테이블이 없어 환경변수로 둔다.
COMPANY_NAME = os.getenv("COMPANY_NAME", "Arda")

# 에이전트 이름. 프롬프트(agent/prompts/agent.v1.md)의 "이름: 아르" 와 같아야 한다.
AGENT_NAME = "아르"

# 문구에 쓸 수 있는 변수. 담당자가 편집한 본문은 이 목록으로 검증한다 —
# 오타 하나가 지원자에게 그대로 나가는 것을 저장 시점에 막는다.
TEMPLATE_VARS = ("{지원자명}", "{공고명}", "{회사명}", "{면접일시}", "{서명}")

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
    "applied": (
        "[{회사명}] {공고명} 지원서가 접수되었습니다",
        """{지원자명} 님, 안녕하세요.

{회사명} {공고명} 포지션에 지원해 주셔서 감사합니다.
제출해 주신 지원서가 정상적으로 접수되었음을 알려드립니다.

서류 검토 결과는 전형 일정에 따라 순차적으로 안내드릴 예정입니다.
접수 내용에 수정이 필요하시거나 문의 사항이 있으시면 이 메일에 회신해 주시기 바랍니다.

{서명}""",
    ),
    "interview": (
        "[{회사명}] {공고명} 서류 전형 합격 및 면접 안내",
        """{지원자명} 님, 안녕하세요.

{회사명} {공고명} 포지션에 지원해 주셔서 감사합니다.
제출해 주신 서류를 검토한 결과, 다음 전형인 면접에 참여하실 수 있게 되었음을 안내드립니다.

면접 일시: {면접일시}

면접 장소와 준비물 등 세부 안내는 별도로 다시 연락드리겠습니다.
일정 조율이 필요하신 경우 이 메일에 회신해 주시기 바랍니다.

다시 한번 서류 합격을 축하드리며, 면접에서 뵙겠습니다.

{서명}""",
    ),
    "accepted": (
        "[{회사명}] {공고명} 최종 합격 안내",
        """{지원자명} 님, 안녕하세요.

{회사명} {공고명} 포지션의 모든 채용 전형을 거쳐 최종 합격하셨음을 안내드립니다.
그동안 전형에 성실히 임해 주셔서 감사드리며, 진심으로 축하드립니다.

입사 절차와 필요 서류 등 세부 안내는 별도로 다시 연락드리겠습니다.
문의 사항이 있으시면 이 메일에 회신해 주시기 바랍니다.

{서명}""",
    ),
    "rejected": (
        "[{회사명}] {공고명} 채용 전형 결과 안내",
        """{지원자명} 님, 안녕하세요.

{회사명} {공고명} 포지션에 지원해 주셔서 감사합니다.
신중히 검토한 결과, 이번 채용 전형에서는 함께하지 못하게 되었음을 안내드립니다.

귀한 시간을 내어 지원해 주신 점 다시 한번 감사드리며,
다음 기회에 좋은 인연으로 다시 뵙기를 바랍니다.

{서명}""",
    ),
}


class UnknownStageTemplate(LookupError):
    """단계에 대응하는 문구가 없다. 워커가 잡아 failed 로 남긴다."""


def get_template(db, stage: str) -> tuple[str, str, str]:
    """(제목, 본문, 출처). 담당자가 저장한 오버라이드가 있으면 그것이 우선한다.

    출처는 `"custom"`(DB 오버라이드) 또는 `"default"`(아래 _TEMPLATES) 다.
    화면이 "지금 나가는 문구가 기본값인가 수정본인가"를 표시하는 데 쓴다 —
    저장소가 둘이라 그 구분이 보이지 않으면 담당자가 헷갈린다.

    **DB 조회가 실패해도 기본값으로 발송한다.** 문구 편집 기능 하나가 죽었다고
    메일 전체가 멈추면 안 된다.
    """
    tpl = _TEMPLATES.get(stage)
    if tpl is None:
        raise UnknownStageTemplate(f"'{stage}' 단계에 해당하는 메일 문구가 없습니다")

    if db is not None:
        try:
            row = db.query(EmailTemplate).filter(EmailTemplate.stage == stage).first()
            if row is not None:
                return row.subject, row.body, "custom"
        except Exception:
            logger.warning("문구 오버라이드 조회 실패 — 기본값으로 간다", exc_info=True)

    return tpl[0], tpl[1], "default"


def sender_name(
    stage: str, actor_kind: str = "system", actor_name: str | None = None
) -> str:
    """발신자를 사람 말로 쓴 이름. 서명과 From 표시 이름이 **같은 문자열**을 쓴다.

    둘을 따로 만들면 받은편지함에는 A 가 보낸 것으로 뜨는데 본문 끝은 B 로 끝나는
    메일이 생긴다 — 지원자가 누구에게 연락해야 할지 헷갈린다.

    **합격·불합격은 주체와 무관하게 사람 이름이다** (G4 결정 6). 에이전트 발송도
    확인 게이트가 있어 최종 승인은 언제나 사람인데, 이름만 보면 AI 가 결정한
    것처럼 읽힌다. 채용에서 "심사도 AI 가 했나"라는 오해는 비싸다.

    사람 이름을 모르면(`actor_name` 없음) 팀 이름으로 내려간다 — 이름 자리를
    비워 두거나 지어내지 않는다.
    """
    if actor_kind == "agent" and stage not in ("accepted", "rejected"):
        return f"{COMPANY_NAME} 채용 에이전트 {AGENT_NAME}"
    if actor_name:
        return f"{COMPANY_NAME} 채용 담당자 {actor_name}"
    return f"{COMPANY_NAME} 채용팀"


def build_signature(
    stage: str, actor_kind: str = "system", actor_name: str | None = None
) -> str:
    """{서명} 자리에 들어갈 한 줄 (G4 결정 6)."""
    return sender_name(stage, actor_kind, actor_name) + " 드림"


def fill(source: str, values: dict[str, str]) -> str:
    """변수를 순차 치환한다. **`str.format` 을 쓰지 않는다.**

    담당자가 편집한 본문에 `{` 가 하나라도 섞이면 format 은 KeyError 를 던지고,
    그러면 워커가 죽어 재시도 끝에 DLQ 까지 간다 — 문구 오타가 발송 장애가 된다.
    replace 는 모르는 토큰을 그대로 두므로 최악이라도 "변수가 안 치환된 메일"이다.
    """
    for key, value in values.items():
        source = source.replace("{" + key + "}", value)
    return source


def fill_body(source: str, values: dict[str, str]) -> str:
    """본문 치환 — `{서명}` 이 없으면 끝에 붙인 뒤 채운다.

    수동·에이전트 발송의 본문은 사람이 그때그때 쓴다. 아르에게는 "서명을 쓰지
    말라"고 시켜 두었고(프롬프트), 담당자도 대개 안 쓴다. 그대로 두면 **서명 없는
    메일**이 나간다 — 받는 쪽에서는 누가 보냈는지 알 수 없다.
    """
    if "{서명}" not in source:
        source = source.rstrip() + "\n\n{서명}"
    return fill(source, values)


def render(
    db,
    stage: str,
    applicant_name: str,
    posting_title: str,
    interview_at: str | None = None,
    actor_kind: str = "system",
    actor_name: str | None = None,
) -> tuple[str, str]:
    """단계에 맞는 (제목, 본문) 을 만든다. 문구를 새로 지어내지 않는다.

    interview_at 은 {면접일시} 자리에 들어갈 문자열이다 — 일정 자동화(ADR-0016)가
    확정 시각이나 선택 링크 안내를 넣는다. 없으면 기존처럼 "별도 안내".
    """
    subject, body, _ = get_template(db, stage)

    values = {
        "지원자명": applicant_name,
        "공고명": posting_title,
        "회사명": COMPANY_NAME,
        "면접일시": interview_at or INTERVIEW_AT_UNKNOWN,
        "서명": build_signature(stage, actor_kind, actor_name),
    }
    return fill(subject, values), fill(body, values)


def unknown_vars(source: str) -> list[str]:
    """본문에서 허용 목록에 없는 `{...}` 토큰을 찾는다. API 가 422 판정에 쓴다.

    빈 리스트면 통과. 오타(`{지원자 명}`)나 없는 변수(`{면접장소}`)를 저장 시점에
    잡는다 — 통과시키면 지원자에게 중괄호가 그대로 나간다.
    """
    found = re.findall(r"\{[^{}]*\}", source)
    return sorted({t for t in found if t not in TEMPLATE_VARS})


def create_log(
    db,
    application_id: int,
    to_email: str,
    stage: str,
    actor_kind: str = "system",
    actor_id: int | None = None,
) -> EmailLog:
    """`email_logs` 행만 만든다. SQS 는 건드리지 않는다.

    **커밋하지 않는다** — 단계 변경·지원서 저장과 같은 트랜잭션에 묶여야 하므로
    커밋은 호출부가 한다. `flush` 만 해서 id 를 얻는다.

    발행(`publish`)과 나눠 둔 이유는 **커밋한 뒤에 발행하기 위해서다.** 먼저 발행하고
    나중에 커밋하면, 호출부가 롤백했을 때 이미 나간 메시지가 존재하지 않는 행을
    가리킨다. 일괄 변경(D9)은 한 건만 실패해도 전부 롤백하므로 그 상황이 예외가
    아니라 정상 경로에 있다.
    """
    log = EmailLog(
        application_id=application_id,
        to_email=to_email,
        stage=stage,
        status="queued",
        retry_count=0,
        actor_kind=actor_kind,
        actor_id=actor_id,
    )
    db.add(log)
    db.flush()  # id 가 있어야 큐에 실어 보낸다
    return log


def create_custom_log(
    db,
    application_id: int,
    to_email: str,
    subject: str,
    body: str,
    actor_kind: str,
    actor_id: int | None,
) -> EmailLog:
    """수동·에이전트 발송용 행. **본문을 행에 실어 둔다.**

    자동 발송과 갈리는 지점이 여기 하나다: 단계 메일은 발송 시점에 렌더하지만
    (면접 안내는 그때가 돼야 라이브 일정 링크를 안다), 사람이 쓴 본문은 이미
    확정돼 있으므로 저장한다. 그래서 **보낸 그대로가 DB 에 남는다** — 지금까지
    없던 감사 기록이다. 워커는 body 가 있으면 렌더를 건너뛴다.

    수신 주소를 인자로 받지만 호출부는 언제나 `application.email` 을 넘긴다.
    임의 주소로 보내는 경로는 API·도구 어느 쪽에도 만들지 않았다 (G4 결정 2).

    커밋은 호출부가 한다 — `create_log` 와 같은 이유다.
    """
    log = EmailLog(
        application_id=application_id,
        to_email=to_email,
        stage="custom",
        status="queued",
        retry_count=0,
        subject=subject,
        body=body,
        actor_kind=actor_kind,
        actor_id=actor_id,
    )
    db.add(log)
    db.flush()
    return log


def publish(email_log_id: int) -> None:
    """이미 커밋된 `email_logs` 행의 id 를 큐에 싣는다."""
    _sqs().send_message(
        QueueUrl=_queue_url(),
        MessageBody=json.dumps({"email_log_id": email_log_id}),
    )
    logger.info("메일 큐 발행 email_log_id=%s", email_log_id)


def enqueue(db, application_id: int, to_email: str, stage: str) -> EmailLog:
    """행 생성 + 큐 발행을 한 번에. 커밋은 호출부가 한다.

    커밋 전에 발행하므로 워커가 행보다 메시지를 먼저 볼 수 있다. 그때 워커는
    예외를 던져 가시성 타임아웃 뒤 다시 받는다(worker.handle 참고).
    **롤백할 수 있는 흐름에서는 이 함수 대신 `create_log` + 커밋 + `publish` 를 쓴다.**
    """
    log = create_log(db, application_id, to_email, stage)
    publish(log.id)
    return log
