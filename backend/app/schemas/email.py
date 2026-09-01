"""메일 문구·발송 (G4) 요청·응답 형태."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TemplateOut(BaseModel):
    """문구 한 벌. `source` 가 "지금 나가는 것이 기본값인가 수정본인가"를 알려준다.

    저장소가 둘(코드 기본값 + DB 오버라이드)이라 이 구분이 화면에 안 보이면
    담당자가 자기가 고친 것이 반영됐는지 알 수 없다.
    """

    stage: str
    subject: str
    body: str
    source: str  # "default" | "custom"
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class TemplateListOut(BaseModel):
    items: list[TemplateOut]


class TemplateSave(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)


class ManualEmailCreate(BaseModel):
    """수동 발송 (G4). **수신자를 받지 않는다.**

    서버가 `application.email` 로만 보낸다 — 임의 주소로 나가는 경로를 만들지
    않는 것이 오발송 반경을 줄이는 가장 확실한 방법이다.
    """

    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)


class EmailLogOut(BaseModel):
    """발송 이력 한 줄. 자동·수동을 한 목록에서 본다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    to_email: str
    stage: str
    status: str
    actor_kind: str
    actor_name: str | None = None  # 라우터가 채운다
    subject: str | None = None
    body: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class EmailLogListOut(BaseModel):
    items: list[EmailLogOut]
    count: int


class MailPreviewOut(BaseModel):
    """수동 발송 프리필 — 템플릿에 이 지원자 값을 채워 본 결과.

    화면이 직접 치환하지 않게 한다. 서명 규칙(G4 결정 6)이 프론트에 복제되면
    "미리보기와 실제 발송이 다르다"가 곧 생긴다.
    """

    subject: str
    body: str
