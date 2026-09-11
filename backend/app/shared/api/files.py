"""이력서 파일 presigned URL (F1·F2).

파일 본문은 이 서버를 지나가지 않는다 — `app/shared/s3.py` 의 설명 참고.
"""

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import File, User
from app.shared.s3 import EXPIRES_IN, presign_get, presign_put
from app.schemas.file import (
    PresignDownloadResponse,
    PresignUploadRequest,
    PresignUploadResponse,
)

router = APIRouter(prefix="/api/v1", tags=["files"])

# 확장자로 쓸 수 있는 모양인지 먼저 본다 (경로 주입·빈 확장자 차단).
_EXT = re.compile(r"^[a-z0-9]{1,10}$")

# ── 업로드 규격 (F3) ─────────────────────────────────────────────────
# 허용 목록으로 막는다. 금지 목록은 빠지는 게 생긴다.
# 형식은 01-erd.md files 표 비고에서 확정된 것이고, 임의로 늘리지 않는다.
ALLOWED_EXT = ("pdf", "docx", "hwp", "hwpx")

# 확장자마다 받아들일 content_type. 확장자와 타입이 어긋나면 담당자가 열 수 없는 파일이
# 이력서 자리에 박힌다. hwp 계열은 브라우저·OS 마다 타입을 다르게 붙여서 octet-stream 까지 받는다.
ALLOWED_TYPE = {
    "pdf": {"application/pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    },
    "hwp": {"application/x-hwp", "application/haansofthwp", "application/octet-stream"},
    "hwpx": {"application/hwp+zip", "application/octet-stream"},
}

MAX_BYTES = 10 * 1024 * 1024  # 10MB

# ── 면접 답변 음성 (설계 §5-4) ────────────────────────────────
#
# **이력서 허용 목록과 섞지 않는다.** 위 `ALLOWED_EXT` 에 음성 확장자를 얹으면
# 이력서 자리에 `.webm` 을 올릴 수 있게 된다 — 담당자가 열 수 없는 파일이
# 이력서로 박힌다. 쓰이는 곳이 다르면 목록도 따로 둔다.
# 영상도 받는다 — 면접 답변을 카메라로 찍으면 **음성이 같은 파일에 들어간다**
# (ADR-0029 진위 분석의 입력이기도 하다). 전사는 그 파일에서 음성만 뽑는다.
AUDIO_EXT = ("webm", "m4a", "mp3", "wav", "mp4")

# 브라우저 MediaRecorder 는 코덱을 붙여 보낸다(`audio/webm;codecs=opus`).
# 세미콜론 뒤는 떼고 본다 — 브라우저마다 붙는 값이 달라 전부 적을 수 없다.
AUDIO_TYPE = {
    "webm": {"audio/webm", "video/webm"},  # 크롬이 video/webm 으로 붙일 때가 있다
    "m4a": {"audio/mp4", "audio/x-m4a", "audio/m4a"},
    "mp3": {"audio/mpeg", "audio/mp3"},
    "wav": {"audio/wav", "audio/x-wav", "audio/wave"},
    # 사파리가 영상을 mp4 로 낸다. webm 은 위에서 video/webm 을 이미 받는다.
    "mp4": {"video/mp4"},
}


MEDIA_MAX_BYTES = 50 * 1024 * 1024  # 면접 녹화 전용 상한


def validate_audio_upload(ext: str, content_type: str, size_bytes: int) -> None:
    """면접 답변 음성용. 이력서와 같은 이유로 **발급 시점에** 막는다.

    **상한이 이력서와 다르다.** 음성만이면 10MB 로 넉넉하지만 카메라를 켜면
    같은 길이가 훨씬 커진다(640x480 vp8 로 1분에 대략 5~10MB). 이력서 상한을
    올리면 그쪽 방어가 같이 느슨해지므로 여기만 따로 둔다.
    """
    if ext not in AUDIO_EXT:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"허용되지 않는 음성 형식입니다. 가능: {', '.join(AUDIO_EXT)}",
        )
    if size_bytes <= 0:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY, "파일 크기가 올바르지 않습니다"
        )
    if size_bytes > MEDIA_MAX_BYTES:
        raise HTTPException(
            http.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"녹화는 {MEDIA_MAX_BYTES // 1024 // 1024}MB 이하만 올릴 수 있습니다",
        )
    base_type = content_type.split(";")[0].strip().lower()
    if base_type not in AUDIO_TYPE[ext]:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"확장자(.{ext})와 파일 형식({content_type})이 맞지 않습니다",
        )


def _validate_upload(ext: str, content_type: str, size_bytes: int) -> None:
    """발급 전에 막는다.

    presigned URL 은 한 번 내주면 그 URL 로 무엇이든 올라간다. 올라온 뒤에 지우면
    S3 요금과 전송량은 이미 나간 뒤다. 막을 지점은 발급 시점이다.
    """
    if ext not in ALLOWED_EXT:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"허용되지 않는 형식입니다. 가능: {', '.join(ALLOWED_EXT)}",
        )
    if size_bytes <= 0:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY, "파일 크기가 올바르지 않습니다"
        )
    if size_bytes > MAX_BYTES:
        raise HTTPException(
            http.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"파일은 {MAX_BYTES // 1024 // 1024}MB 이하만 올릴 수 있습니다",
        )
    if content_type not in ALLOWED_TYPE[ext]:
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"확장자(.{ext})와 파일 형식({content_type})이 맞지 않습니다",
        )


def _extract_ext(filename: str) -> str:
    """확장자만 뽑는다. 경로로 쓸 수 있는 모양이 아니면 거절한다."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if not _EXT.fullmatch(ext):
        raise HTTPException(
            http.HTTP_422_UNPROCESSABLE_ENTITY,
            f"파일 확장자를 알 수 없습니다: {filename}",
        )
    return ext


def _build_key(ext: str, kind: str) -> str:
    """S3 키를 **서버가** 만든다.

    클라이언트가 보낸 경로를 쓰면 `applications/<남의 uuid>/resume.pdf` 를 요청해
    남의 이력서를 덮어쓸 수 있다. presigned PUT 은 그 키에 쓸 권한을 그대로 주므로,
    키를 클라이언트가 고르는 순간 서명이 곧 임의 위치 쓰기 권한이 된다.
    """
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
    ext = _extract_ext(body.filename)
    _validate_upload(ext, body.content_type, body.size_bytes)

    key = _build_key(ext, body.kind)
    return PresignUploadResponse(
        upload_url=presign_put(key, body.content_type, body.size_bytes),
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
    """다운로드용 presigned URL 발급 (F2). 로그인한 사람이면 누구나 (ADR-0017).

    로그인 자체는 여전히 필수다 — 이력서는 개인정보이므로 토큰 없는 요청은 401.
    """
    row = db.get(File, file_id)
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다")

    return PresignDownloadResponse(
        download_url=presign_get(row.s3_key),
        filename=row.filename,
        expires_in=EXPIRES_IN,
    )
