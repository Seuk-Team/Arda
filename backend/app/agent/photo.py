"""이력서에서 지원자 사진을 꺼낸다 — 대리응시 확인용 (회의 2026-09-09).

**저장하지 않는다.** 꺼내서 그 자리에서 비교하고 버린다. 얼굴 지문은 민감정보이고,
남겨 두면 지켜야 할 것이 하나 더 생긴다. 비교는 면접 워커가 하고 여기서는 사진만 준다.

**판정이 아니다.** 대리응시를 막으려는 것이지 지원자를 평가하려는 것이 아니다.
"다른 사람이다" 라고 단정하지 않고 "얼굴이 많이 다릅니다" 까지만 말한다
(ADR-0029 가 영상을 저장하지 않는 것과 같은 자리).
"""

from __future__ import annotations

import io
import logging
import zipfile

logger = logging.getLogger(__name__)

# 이보다 작은 그림은 사진이 아니라 아이콘·구분선이다. 증명사진은 보통 한 변이 수백 px.
MIN_SIDE = 80
# 너무 큰 그림은 배경이나 스캔한 페이지 전체다 — 얼굴만 있는 증명사진이 아니다.
MAX_PIXELS = 4000 * 4000


def _images_from_pdf(body: bytes) -> list[bytes]:
    from pypdf import PdfReader

    out: list[bytes] = []
    for page in PdfReader(io.BytesIO(body)).pages:
        for image in page.images:
            out.append(image.data)
    return out


def _images_from_zip(body: bytes, prefix: str) -> list[bytes]:
    """docx·hwpx 는 zip 이고 그림이 폴더 하나에 모여 있다."""
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        return [
            z.read(n)
            for n in z.namelist()
            if n.startswith(prefix) and n.rsplit(".", 1)[-1].lower() in ("jpg", "jpeg", "png")
        ]


def images_of(file) -> list[bytes]:
    """이력서 파일에 든 그림들. 못 읽으면 빈 목록.

    **어떤 실패도 면접을 막지 않는다.** 사진을 못 꺼내면 확인을 건너뛸 뿐이다 —
    서류에 사진이 없다고 지원자가 불리해지면 안 된다.
    """
    from app.shared import s3

    ext = file.s3_key.rsplit(".", 1)[-1].lower()
    try:
        body = s3._client().get_object(Bucket=s3.BUCKET, Key=file.s3_key)["Body"].read()
    except Exception:
        logger.warning("이력서 내려받기 실패 (file_id=%s)", file.id)
        return []

    try:
        if ext == "pdf":
            return _images_from_pdf(body)
        if ext == "docx":
            return _images_from_zip(body, "word/media/")
        if ext == "hwpx":
            return _images_from_zip(body, "BinData/")
    except Exception:
        logger.warning("이력서에서 그림을 꺼내지 못했다 (file_id=%s, ext=%s)", file.id, ext)
    return []


def portrait_of(app) -> bytes | None:
    """지원자 증명사진. 없으면 None.

    이력서 서식이 사진 한 장을 담는 것을 전제로 한다. 그래도 여러 장이 나오면
    **가장 큰 것**을 고른다 — 로고·도장보다 증명사진이 크다. 크기로 거르는 것은
    얼굴 검출보다 훨씬 싸고, 진짜 얼굴인지는 받는 쪽(워커)이 어차피 다시 본다.
    """
    resume = next((f for f in app.files if f.kind == "resume"), None)
    if resume is None:
        return None

    best: tuple[int, bytes] | None = None
    for raw in images_of(resume):
        size = _pixels(raw)
        if size is None or size < MIN_SIDE * MIN_SIDE or size > MAX_PIXELS:
            continue
        if best is None or size > best[0]:
            best = (size, raw)
    return best[1] if best else None


def _pixels(raw: bytes) -> int | None:
    """가로×세로. 못 읽으면 None — 그림이 아니거나 깨진 것이다."""
    from PIL import Image

    try:
        with Image.open(io.BytesIO(raw)) as im:
            w, h = im.size
    except Exception:
        return None
    return w * h if min(w, h) >= MIN_SIDE else None
