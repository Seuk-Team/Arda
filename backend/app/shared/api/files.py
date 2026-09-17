"""이력서 파일 presigned URL (F1·F2) + 온프레미스 스트리밍 다운로드.

원칙은 여전히 **"파일 본문은 서버를 지나가지 않는다"** — S3/MinIO 배포에서 브라우저가
presigned URL 로 직접 내려받는다(shared/s3.py 머리말).

**온프레미스만 예외**(2026-09-17). MinIO 가 컨테이너 안에만 있어 서명 URL 호스트가
`minio:9000` 이라 브라우저에서 이름이 안 풀린다. 이관 스크립트가 파일을 `file_blobs`
(bytea) 에 넣어 두면 `presign_download` 가 티켓 기반 API URL 을 대신 돌려주고,
`download_file` 이 티켓을 검사한 뒤 바이트를 스트리밍한다.

**티켓을 쓰는 이유**: `window.open(download_url)` 은 브라우저 새 탭이라 `Authorization`
헤더를 붙일 수 없다. 그렇다고 로그인 없이 열게 두면 file_id 를 아는 누구든 이력서를
받아 갈 수 있다(ADR-0017 위반). 그래서 로그인한 사람에게만 60초·1회용 티켓을 발급하고
그 티켓을 쿼리스트링으로 받는다 — WebRTC 시그널링의 rtc-ticket 과 같은 방식
(`interview_rtc.py` 티켓 절 참고).

`file_blobs` 가 없는 파일은 기존 S3 presign 으로 자동 폴백 — AWS 배포는 이 경로만 탄다.
"""

import io
import os
import re
import secrets
import time
import uuid
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status as http
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import File, FileBlob, User
from app.shared.s3 import EXPIRES_IN, presign_get, presign_put
from app.schemas.file import (
    PresignDownloadResponse,
    PresignUploadRequest,
    PresignUploadResponse,
)

router = APIRouter(prefix="/api/v1", tags=["files"])

# ── 다운로드 티켓 (온프레미스 스트리밍 전용) ────────────────────────
# 60초·1회용. rtc-ticket 과 같은 자료구조라 통합하고 싶지만 의미(면접방 입장 vs
# 파일 다운로드)가 달라 분리한다 — 실수로 파일 티켓이 방에 통하는 것 방지.
_FILE_TICKET_TTL_SEC = 60
_FILE_TICKETS: dict[str, tuple[int, int, float]] = {}  # ticket → (file_id, user_id, at)


def _sweep_file_tickets(now: float) -> None:
    for t in [
        t for t, (_, _, at) in _FILE_TICKETS.items() if now - at > _FILE_TICKET_TTL_SEC
    ]:
        _FILE_TICKETS.pop(t, None)


def _issue_file_ticket(file_id: int, user_id: int) -> str:
    now = time.time()
    _sweep_file_tickets(now)
    ticket = secrets.token_urlsafe(24)
    _FILE_TICKETS[ticket] = (file_id, user_id, now)
    return ticket


def _redeem_file_ticket(ticket: str, file_id: int) -> int | None:
    """쓰면 사라진다. 맞으면 user_id, 아니면 None."""
    entry = _FILE_TICKETS.pop(ticket, None)
    if entry is None:
        return None
    fid, user_id, at = entry
    if fid != file_id or time.time() - at > _FILE_TICKET_TTL_SEC:
        return None
    return user_id

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
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """다운로드용 URL 발급 (F2). 로그인한 사람이면 누구나 (ADR-0017).

    - `file_blobs` 에 본문이 있으면 API 스트리밍 URL(1회용 티켓) 을 돌려준다 — 온프레미스.
    - 없으면 기존 S3 presign — AWS 배포. 두 경로가 이 안에서만 갈리므로 프론트는 같다.

    로그인 자체는 여전히 필수다 — 이력서는 개인정보이므로 토큰 없는 요청은 401.
    """
    row = db.get(File, file_id)
    if row is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다")

    if db.get(FileBlob, file_id) is not None:
        # 온프레미스 경로. 프론트가 `window.open(download_url)` 을 하니 절대 URL 이 필요하다.
        # base 는 세 순위로 정한다: (1) `PUBLIC_API_BASE_URL` 환경변수 — 온프레미스처럼
        # 최종 스킴이 정해져 있을 때 이걸 못박아 둬야 안전하다 (2) `Cf-Visitor` — Cloudflare
        # Tunnel 이 붙이는 원래 스킴, `{"scheme":"https"}` (3) 헤더/요청 스킴. 이유:
        # cloudflared → Caddy 는 http 로 오므로 Caddy 는 `X-Forwarded-Proto: http` 를
        # 붙여 넘긴다. 그 값으로 URL 을 만들면 브라우저가 https 페이지에서 mixed-content
        # 로 막는다 (2026-09-17 실측).
        ticket = _issue_file_ticket(file_id, user.id)
        base = os.getenv("PUBLIC_API_BASE_URL", "").rstrip("/")
        if not base:
            cf_visitor = request.headers.get("cf-visitor") or ""
            scheme = (
                request.headers.get("x-forwarded-proto")
                or ("https" if '"scheme":"https"' in cf_visitor else request.url.scheme)
            )
            host = request.headers.get("host") or request.url.netloc
            base = f"{scheme}://{host}"
        url = f"{base}/api/v1/files/{file_id}/download?ticket={urllib.parse.quote(ticket)}"
        return PresignDownloadResponse(
            download_url=url,
            filename=row.filename,
            expires_in=_FILE_TICKET_TTL_SEC,
        )

    return PresignDownloadResponse(
        download_url=presign_get(row.s3_key),
        filename=row.filename,
        expires_in=EXPIRES_IN,
    )


@router.get("/files/{file_id}/download")
def download_file(
    file_id: int,
    ticket: str,
    db: Session = Depends(get_db),
):
    """티켓 검사 후 파일 바이트 스트리밍 (온프레미스 전용).

    - 로그인 헤더 대신 티켓 하나로 인증한다 — 사유는 파일 머리말.
    - 티켓이 없거나 만료/재사용이면 401. 파일 메타·본문 어느 쪽이든 없으면 404.
    - Content-Disposition 은 attachment — 브라우저가 미리보기 대신 저장 다이얼로그를 띄운다.
      파일명에 한글이 있어 RFC 5987 `filename*` 을 함께 붙인다.
    """
    if _redeem_file_ticket(ticket, file_id) is None:
        raise HTTPException(http.HTTP_401_UNAUTHORIZED, "티켓이 유효하지 않습니다")
    row = db.get(File, file_id)
    blob = db.get(FileBlob, file_id)
    if row is None or blob is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다")

    ascii_fallback = row.filename.encode("ascii", "replace").decode("ascii")
    utf8_encoded = urllib.parse.quote(row.filename, safe="")
    return StreamingResponse(
        io.BytesIO(blob.content),
        media_type=row.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_fallback}"; '
                f"filename*=UTF-8''{utf8_encoded}"
            ),
            "Content-Length": str(blob.size_bytes),
        },
    )
