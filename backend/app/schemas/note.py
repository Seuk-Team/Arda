from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _not_blank(v: str) -> str:
    # 공백만 있는 메모가 목록을 채우면 아무도 안 읽게 된다
    if not v.strip():
        raise ValueError("내용을 입력하세요")
    return v.strip()


class NoteCreate(BaseModel):
    body: str = Field(min_length=1)

    _strip = field_validator("body")(_not_blank)


class NoteUpdate(BaseModel):
    body: str = Field(min_length=1)
    # 클라이언트가 읽어 간 시점의 값. 지금 DB 값과 다르면 그 사이 누가 고친 것이다
    # (ADR-0005). 이것 없이 저장하면 남의 수정을 모르고 덮어쓴다.
    updated_at: datetime

    _strip = field_validator("body")(_not_blank)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    application_id: int
    author_id: int
    author_name: str  # 목록에서 누가 썼는지 바로 보이게 (02-api.md)
    body: str
    created_at: datetime
    updated_at: datetime
