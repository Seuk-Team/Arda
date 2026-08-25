"""이력서·자소서 텍스트 추출 (PoC).

지원: pdf(텍스트 PDF) · docx · hwp는 실패 시 수동 폴백 경로만 명시.
스캔본 PDF·암호 PDF는 이 PoC에서 성공 대상이 아니다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractResult:
    path: str
    fmt: str
    ok: bool
    chars: int
    preview: str
    error: str | None = None
    # 어느 경로로 뽑았는지. 결과표에 남겨야 "무엇으로 검증했나"에 답할 수 있다.
    engine: str = "-"


def pypdf_available() -> bool:
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return False
    return True


def _preview(text: str, n: int = 120) -> str:
    one = " ".join(text.split())
    return one if len(one) <= n else one[: n - 1] + "…"


def extract_pdf(path: Path) -> ExtractResult:
    raw = path.read_bytes()
    # 최소 의존: 샘플 PDF는 비압축 Latin-1 텍스트 스트림으로 생성한다.
    # 실서비스에서는 pypdf 등으로 교체한다 (uv sync --extra agent).
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(path.open("rb"))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
        if not text:
            return ExtractResult(
                str(path),
                "pdf",
                False,
                0,
                "",
                "텍스트 없음(스캔본·빈 페이지 가능)",
                engine="pypdf",
            )
        return ExtractResult(
            str(path), "pdf", True, len(text), _preview(text), engine="pypdf"
        )
    except ImportError:
        pass

    # stdlib 폴백: BT/ET 사이 Tj 문자열만 긁기 (PoC 샘플용)
    try:
        s = raw.decode("latin-1", errors="ignore")
    except Exception as e:  # noqa: BLE001
        return ExtractResult(str(path), "pdf", False, 0, "", f"decode: {e}")

    chunks: list[str] = []
    i = 0
    while True:
        a = s.find("(", i)
        if a < 0:
            break
        b = s.find(") Tj", a)
        if b < 0:
            break
        chunks.append(s[a + 1 : b])
        i = b + 4
    text = " ".join(chunks).strip()
    if not text:
        return ExtractResult(
            str(path),
            "pdf",
            False,
            0,
            "",
            "stdlib 폴백으로 텍스트를 못 얻음 — pypdf 설치 권장",
            engine="stdlib",
        )
    return ExtractResult(
        str(path), "pdf", True, len(text), _preview(text), engine="stdlib"
    )


def extract_docx(path: Path) -> ExtractResult:
    import zipfile
    import xml.etree.ElementTree as ET

    try:
        with zipfile.ZipFile(path) as zf:
            xml = zf.read("word/document.xml")
        root = ET.fromstring(xml)
        texts = [
            (node.text or "")
            for node in root.iter(
                "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
            )
        ]
        text = "".join(texts).strip()
        if not text:
            return ExtractResult(
                str(path), "docx", False, 0, "", "본문 텍스트 없음", engine="stdlib-zip"
            )
        return ExtractResult(
            str(path), "docx", True, len(text), _preview(text), engine="stdlib-zip"
        )
    except KeyError:
        return ExtractResult(str(path), "docx", False, 0, "", "word/document.xml 없음")
    except zipfile.BadZipFile:
        return ExtractResult(str(path), "docx", False, 0, "", "docx(zip) 손상")
    except Exception as e:  # noqa: BLE001
        return ExtractResult(str(path), "docx", False, 0, "", str(e))


def extract_hwp(path: Path) -> ExtractResult:
    """HWP는 PoC에서 성공 대상이 아니다 — 수동 폴백 경로를 명시한다."""
    _ = path.read_bytes()[:8]  # 존재·가독만 확인
    return ExtractResult(
        str(path),
        "hwp",
        False,
        0,
        "",
        "HWP 자동 추출 미지원 → 담당자가 상세 폼에 수동 입력(폴백)",
    )


def extract_file(path: Path) -> ExtractResult:
    suf = path.suffix.lower().lstrip(".")
    if suf == "pdf":
        return extract_pdf(path)
    if suf == "docx":
        return extract_docx(path)
    if suf in {"hwp", "hwpx"}:
        return extract_hwp(path)
    return ExtractResult(str(path), suf or "?", False, 0, "", f"미지원 확장자: {suf}")
