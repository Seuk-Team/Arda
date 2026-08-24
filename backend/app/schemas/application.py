from pydantic import BaseModel, ConfigDict, field_validator


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
