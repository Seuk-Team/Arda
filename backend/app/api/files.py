"""이력서 파일 presigned URL (F1·F2).

파일 본문은 이 서버를 지나가지 않는다 — `app/s3.py` 의 설명 참고.
"""

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import assert_can_view_application, get_current_user
from app.models import File, User
from app.s3 import EXPIRES_IN, presign_get, presign_put
from app.schemas.file import (
    PresignDownloadResponse,
    PresignUploadRequest,
    PresignUploadResponse,
)

router = APIRouter(prefix="/api/v1", tags=["files"])

# 확장자로 쓸 수 있는 모양인지만 본다. 허용 목록(pdf·docx·hwp)은 F3 에서 건다.
_EXT = re.compile(r"^[a-z0-9]{1,10}$")


def _build_key(filename: str, kind: str) -> str:
    """S3 키를 **서버가** 만든다.

    클라이언트가 보낸 경로를 쓰면 `applications/<남의 uuid>/resume.pdf` 를 요청해
    남의 이력서를 덮어쓸 수 있다. presigned PUT 은 그 키에 쓸 권한을 그대로 주므로,
    키를 클라이언트가 고르는 순간 서명이 곧 임의 위치 쓰기 권한이 된다.
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    if not _EXT.fullmatch(ext):
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"파일 확장자를 알 수 없습니다: {filename}",
        )
    return f"applications/{uuid.uuid4()}/{kind}.{ext}"


@router.post(
    "/public/files/presign-upload",
    response_model=PresignUploadResponse,
)
def presign_upload(body: PresignUploadRequest):
    """업로드용 presigned URL 발급 (F1). **공개** — 지원자는 로그인하지 않는다.

    발급 시점에는 아직 지원서가 없으므로 `files` 행을 만들지 않는다
    (`files.application_id` 는 NOT NULL). 클라이언트가 받은 `s3_key` 를 들고 있다가
    지원서 제출(C2)에 함께 보내면 그때 행이 생긴다.
    """
    key = _build_key(body.filename, body.kind)
    return PresignUploadResponse(
        upload_url=presign_put(key, body.content_type),
        s3_key=key,
        expires_in=EXPIRES_IN,
    )


@router.get(
    "/files/{file_id}/presign-download",
    response_model=PresignDownloadResponse,
)
def presign_download(
    file_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """다운로드용 presigned URL 발급 (F2). 로그인 필요.

    면접관은 본인에게 배정된 지원자의 파일만 받을 수 있다 (A3). 지원서를 못 보는
    사람이 그 지원서의 이력서를 받으면 접근 제어가 우회된다.
    """
    row = db.get(File, file_id)
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다")

    assert_can_view_application(db, user, row.application_id)

    return PresignDownloadResponse(
        download_url=presign_get(row.s3_key),
        filename=row.filename,
        expires_in=EXPIRES_IN,
    )
