from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.file import FileKind


class SubmittedFile(BaseModel):
    """지원자가 presign(F1)으로 S3 에 올린 파일 한 건.

    `s3_key` 는 **서버가 발급한 값을 그대로 돌려받는 것**이다. 클라이언트가 지어낸
    키를 그대로 믿으면 남의 파일을 자기 지원서에 붙일 수 있으므로, 접수 시점에
    키 모양과 종류 일치를 다시 본다 (`public.py _collect_files`).
    """

    s3_key: str = Field(min_length=1, max_length=500)
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(gt=0)
    content_type: str = Field(min_length=1, max_length=100)
    kind: FileKind


class PostingPublicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None


class ApplicationCreate(BaseModel):
    name: str
    email: str
    phone: str
    education: str | None = None
    career_years: int | None = None
    skills: list[str] | None = None
    self_intro: str | None = None
    privacy_agreed: bool
    # F1 → C2 의 연결. presign 은 발급 시점에 지원서가 없어 `files` 행을 만들지
    # 못한다(application_id 가 NOT NULL). 그래서 접수 때 함께 받아 여기서 만든다.
    # 지원자가 내는 것은 이력서·자기소개서 2종뿐이다 (01-erd.md files.kind).
    files: list[SubmittedFile] = Field(default_factory=list, max_length=2)

    @field_validator("privacy_agreed")
    @classmethod
    def must_agree(cls, v: bool) -> bool:
        if not v:
            raise ValueError("privacy_agreed 는 true 여야 합니다")
        return v


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_posting_id: int
    name: str
    email: str
    current_stage: str
    source: str
