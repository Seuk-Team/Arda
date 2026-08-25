from typing import Literal

from pydantic import BaseModel, Field

from app.models import FILE_KINDS

FileKind = Literal[FILE_KINDS]  # ("resume", "cover_letter")


class PresignUploadRequest(BaseModel):
    # filename 은 확장자를 뽑는 데만 쓴다. 경로로는 절대 쓰지 않는다 — 아래 s3_key 참고
    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)
    kind: FileKind


class PresignUploadResponse(BaseModel):
    upload_url: str
    # 클라이언트는 이 값을 그대로 들고 있다가 지원서 제출 때 함께 보낸다
    s3_key: str
    expires_in: int


class PresignDownloadResponse(BaseModel):
    download_url: str
    filename: str
    expires_in: int
