"""이력서·자기소개서 파일 텍스트 추출 — 요약(summarizer)의 입력을 채운다.

전부 로컬 처리라 LLM 비용이 들지 않는다 (ADR-0011 비용 가드와 무관).
**어떤 실패도 요약을 막지 않는다**: S3 를 못 읽든 파일이 깨졌든 None 을
돌려주고, 요약은 기존처럼 폼 필드만으로 돈다. 여기서 예외를 올리면
"파일 하나 때문에 요약 전체가 안 나오는" 상황이 된다.

지원 형식은 files.py ALLOWED_EXT 와 같은 목록에서 텍스트를 꺼낼 수 있는 것:
- pdf  — pypdf
- docx — zip 안의 word/document.xml (표준 라이브러리로 충분하다)
- hwpx — zip 안의 Contents/section*.xml (같은 방식)
- hwp  — 구형 바이너리 포맷이라 파서 없이는 못 읽는다. 건너뛴다.
"""

import io
import logging
import re
import zipfile
from html import unescape

from app import s3
from app.models import File

logger = logging.getLogger(__name__)

# 프롬프트에 넣을 최대 길이. 한국어는 대략 글자당 1토큰꼴이라, 8천 자면
# 요약 체인(3회 호출)을 다 돌아도 Haiku 기준 수 센트 안이다.
MAX_CHARS = 8000

_TAG = re.compile(r"<[^>]+>")


def _pdf(body: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _xml_zip(body: bytes, name_ok) -> str:
    """zip 컨테이너(docx·hwpx) 공통 — 문단 경계를 살리고 태그를 벗긴다."""
    parts: list[str] = []
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        for name in sorted(z.namelist()):
            if not name_ok(name):
                continue
            xml = z.read(name).decode("utf-8", errors="ignore")
            xml = re.sub(r"</w:p>|</hp:p>", "\n", xml)
            parts.append(unescape(_TAG.sub("", xml)))
    return "\n".join(parts)


def _docx(body: bytes) -> str:
    return _xml_zip(body, lambda n: n == "word/document.xml")


def _hwpx(body: bytes) -> str:
    return _xml_zip(
        body, lambda n: n.startswith("Contents/section") and n.endswith(".xml")
    )


def _clean(text: str) -> str:
    """빈 줄 뭉치·줄 끝 공백 정리. 추출 텍스트는 공백이 많아 토큰만 축낸다."""
    lines = [ln.strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln:
            out.append(ln)
        elif out and out[-1]:
            out.append("")  # 빈 줄은 한 줄만 남긴다
    return "\n".join(out).strip()


def extract_text(file: File) -> str | None:
    """파일 하나의 본문 텍스트. 실패·미지원이면 None (요약은 폼 필드로 돈다)."""
    ext = file.s3_key.rsplit(".", 1)[-1].lower()

    try:
        body = s3._client().get_object(Bucket=s3.BUCKET, Key=file.s3_key)["Body"].read()
    except Exception:
        logger.warning(
            "파일 내려받기 실패 — 요약은 폼 필드로만 (file_id=%s, kind=%s)",
            file.id,
            file.kind,
        )
        return None

    try:
        if ext == "pdf":
            text = _pdf(body)
        elif ext == "docx":
            text = _docx(body)
        elif ext == "hwpx":
            text = _hwpx(body)
        else:
            logger.info("추출 미지원 형식 .%s — 건너뜀 (file_id=%s)", ext, file.id)
            return None
    except Exception:
        logger.warning("텍스트 추출 실패 (.%s, file_id=%s)", ext, file.id)
        return None

    text = _clean(text)
    if not text:
        return None
    if len(text) > MAX_CHARS:
        logger.info(
            "추출 텍스트 %d자 → %d자로 자름 (file_id=%s)", len(text), MAX_CHARS, file.id
        )
        text = text[:MAX_CHARS]
    return text
