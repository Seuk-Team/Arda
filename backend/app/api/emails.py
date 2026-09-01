"""메일 문구·수동 발송 API (G4).

두 가지를 담는다.

1. **문구 오버라이드** (`/email-templates`) — 설정 화면 "메일 템플릿" 탭.
   행이 없으면 코드 기본값(`mail._TEMPLATES`)이 나간다. 저장은 admin 전용
   (ADR-0017 의 admin 전용 넷 중 하나).
2. **수동 발송** (`/applications/{id}/emails`) — 지원자 상세 패널.
   로그인한 사람이면 누구나. member 의 단계 변경이 이미 메일을 발송하므로
   수동 발송만 admin 으로 좁힐 논리가 없다.

**발송은 여기서 하지 않는다.** `email_logs` 행을 만들고 커밋한 뒤 SQS 에 id 만
싣는다 — G2 와 같은 순서다. 커밋 전에 발행하면 롤백된 행을 워커가 집는다.
"""

import logging
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import mail
from app.db import get_db
from app.deps import get_current_user, require_roles
from app.models import (
    TEMPLATE_STAGES,
    Application,
    EmailLog,
    EmailTemplate,
    JobPosting,
    User,
)
from app.schemas.email import (
    EmailLogListOut,
    EmailLogOut,
    MailPreviewOut,
    ManualEmailCreate,
    TemplateListOut,
    TemplateOut,
    TemplateSave,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["emails"])


def _assert_known_stage(stage: str) -> None:
    if stage not in TEMPLATE_STAGES:
        raise HTTPException(
            HTTPStatus.NOT_FOUND,
            f"'{stage}' 단계에는 편집할 문구가 없습니다",
        )


def _template_out(db: Session, stage: str) -> TemplateOut:
    subject, body, source = mail.get_template(db, stage)
    row = (
        db.scalar(select(EmailTemplate).where(EmailTemplate.stage == stage))
        if source == "custom"
        else None
    )
    editor = db.get(User, row.updated_by) if row is not None else None
    return TemplateOut(
        stage=stage,
        subject=subject,
        body=body,
        source=source,
        updated_at=row.updated_at if row else None,
        updated_by_name=editor.name if editor else None,
    )


@router.get("/email-templates", response_model=TemplateListOut)
def list_templates(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """문구 4종. 조회는 로그인 전원 — 수동 발송 프리필도 이것을 쓴다."""
    return TemplateListOut(
        items=[_template_out(db, stage) for stage in TEMPLATE_STAGES]
    )


@router.put("/email-templates/{stage}", response_model=TemplateOut)
def save_template(
    stage: str,
    body: TemplateSave,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
):
    """문구 오버라이드 저장. admin 전용.

    허용 목록에 없는 `{...}` 토큰은 422 다. 통과시키면 중괄호가 그대로 지원자에게
    나간다 — 발송은 되돌릴 수 없으므로 저장 시점에 잡는 것이 유일한 기회다.

    `{서명}` 이 없으면 본문 끝에 붙인다. 편집하다 서명 줄을 지우는 일이 흔한데,
    서명 없는 메일이 나가게 두느니 자동으로 채운다.
    """
    _assert_known_stage(stage)

    bad = mail.unknown_vars(body.subject) + mail.unknown_vars(body.body)
    if bad:
        raise HTTPException(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "쓸 수 없는 변수입니다: "
            + ", ".join(sorted(set(bad)))
            + " (가능: "
            + ", ".join(mail.TEMPLATE_VARS)
            + ")",
        )

    text = body.body if "{서명}" in body.body else body.body.rstrip() + "\n\n{서명}"

    row = db.scalar(select(EmailTemplate).where(EmailTemplate.stage == stage))
    if row is None:
        row = EmailTemplate(stage=stage, subject=body.subject, body=text, updated_by=actor.id)
        db.add(row)
    else:
        row.subject = body.subject
        row.body = text
        row.updated_by = actor.id
    db.commit()
    return _template_out(db, stage)


@router.delete("/email-templates/{stage}", response_model=TemplateOut)
def reset_template(
    stage: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_roles("admin")),
):
    """오버라이드 삭제 = 기본 문구로 복귀. admin 전용.

    204 가 아니라 복귀한 기본 문구를 돌려준다 — 화면이 곧바로 그것을 그린다.
    """
    _assert_known_stage(stage)
    row = db.scalar(select(EmailTemplate).where(EmailTemplate.stage == stage))
    if row is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "수정된 문구가 없습니다")
    db.delete(row)
    db.commit()
    return _template_out(db, stage)


# ── 수동 발송 ─────────────────────────────────────────────────────────


def _application(db: Session, application_id: int) -> Application:
    row = db.get(Application, application_id)
    if row is None:
        raise HTTPException(HTTPStatus.NOT_FOUND, "지원자를 찾을 수 없습니다")
    return row


def _values(db: Session, application: Application, actor: User, stage: str) -> dict:
    posting = db.get(JobPosting, application.job_posting_id)
    return {
        "지원자명": application.name,
        "공고명": posting.title if posting else "",
        "회사명": mail.COMPANY_NAME,
        "면접일시": mail.INTERVIEW_AT_UNKNOWN,
        "서명": mail.build_signature(stage, "human", actor.name),
    }


@router.get(
    "/applications/{application_id}/emails/preview", response_model=MailPreviewOut
)
def preview_email(
    application_id: int,
    stage: str = Query("interview", description="프리필에 쓸 문구 단계"),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """수동 발송 프리필 — 템플릿에 이 지원자 값을 채워 돌려준다.

    치환을 화면이 하게 두지 않는다. 서명 규칙(G4 결정 6)이 프론트에 복제되는
    순간 "미리보기와 실제 발송이 다르다"가 생긴다.
    """
    _assert_known_stage(stage)
    application = _application(db, application_id)
    subject, body, _ = mail.get_template(db, stage)
    values = _values(db, application, actor, stage)
    return MailPreviewOut(
        subject=mail.fill(subject, values), body=mail.fill(body, values)
    )


@router.post(
    "/applications/{application_id}/emails",
    response_model=EmailLogOut,
    status_code=HTTPStatus.CREATED,
)
def send_manual_email(
    application_id: int,
    body: ManualEmailCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """수동 발송. 수신자는 **서버가 지원자 주소로 고정한다** (본문에도 없다).

    남은 변수(`{서명}` 등)는 여기서 채운다 — 담당자가 프리필을 지우고 다시
    썼더라도 서명이 빠지지 않게 한다.
    """
    application = _application(db, application_id)
    values = _values(db, application, actor, "custom")

    log = mail.create_custom_log(
        db,
        application_id=application.id,
        to_email=application.email,
        subject=mail.fill(body.subject, values),
        body=mail.fill_body(body.body, values),
        actor_kind="human",
        actor_id=actor.id,
    )
    db.commit()

    # 커밋 뒤 발행 — 큐가 죽어도 행은 queued 로 남아 나중에 셀 수 있다
    try:
        mail.publish(log.id)
    except Exception:
        logger.exception("수동 발송 큐 발행 실패 email_log_id=%s", log.id)

    return EmailLogOut.model_validate(log).model_copy(
        update={"actor_name": actor.name}
    )


@router.get("/applications/{application_id}/emails", response_model=EmailLogListOut)
def list_emails(
    application_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """이 지원자에게 나간 메일 이력. 자동·수동을 한 목록에서 본다.

    "보냈는데 안 왔다"는 문의가 오면 여기부터 본다 — 지금까지는 DB 를 직접
    들여다보는 것 말고 방법이 없었다.
    """
    _application(db, application_id)
    rows = db.scalars(
        select(EmailLog)
        .where(EmailLog.application_id == application_id)
        .order_by(EmailLog.id.desc())
    ).all()

    names = dict(
        db.execute(
            select(User.id, User.name).where(
                User.id.in_([r.actor_id for r in rows if r.actor_id])
            )
        ).all()
    )
    items = [
        EmailLogOut.model_validate(r).model_copy(
            update={"actor_name": names.get(r.actor_id)}
        )
        for r in rows
    ]
    return EmailLogListOut(items=items, count=len(items))
