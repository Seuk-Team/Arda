"""PoC용 합성 샘플 생성 — 실제 지원자 파일을 저장소에 넣지 않기 위함.

    uv run python -m app.agent.extract.make_samples

pdf 10 · docx 5 · hwp 5를 만든다.
pdf 중 2건은 '스캔본 흉내'(텍스트 없음)로 만들어 실패 케이스를 재현한다.
개인정보 없음 — 전부 합성 문자열.

PDF는 fpdf2와 한글 TTF가 있으면 **한글 본문**으로 만든다. 실제 이력서가 한글이라
영문 샘플만으로는 추출을 검증했다고 할 수 없다. 둘 중 하나라도 없으면 폰트를
심지 않는 최소 PDF(영문)로 물러난다 — 그때는 한글 검증이 안 된 것으로 읽어야 한다.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

# 한글 TTF 후보. 없으면 영문 폴백.
KOREAN_FONTS = (
    "/mnt/c/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/malgun.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
)

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2]
# 샘플 바이너리는 커밋하지 않는다 (backend/app/agent/.gitignore).
# 실제 지원자 파일은 어떤 경우에도 저장소에 넣지 않는다.
OUT = HERE / "samples"

NAMES = ["김도현", "이서연", "박준호", "최민지", "정우성"]
# PDF 샘플은 Helvetica(latin-1) 한 벌만 쓰는 최소 PDF라 한글을 넣을 수 없다.
# 한글 PDF 추출 검증은 pypdf + 실제 파일로 W3에서 한다.
LATIN_NAMES = ["Kim Dohyun", "Lee Seoyeon", "Park Junho", "Choi Minji", "Jung Woosung"]
SKILLS = ["Python FastAPI PostgreSQL", "React TypeScript Vite", "AWS Docker CI/CD"]


def _find_korean_font() -> str | None:
    for p in KOREAN_FONTS:
        if Path(p).exists():
            return p
    return None


def _pdf_korean_bytes(body: str, font: str, with_text: bool = True) -> bytes:
    """fpdf2로 한글 TTF를 심은 PDF. with_text=False면 빈 페이지(스캔본 흉내)."""
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    if with_text:
        pdf.add_font("ko", "", font)
        pdf.set_font("ko", size=12)
        pdf.multi_cell(0, 8, body)
    return bytes(pdf.output())


def _pdf_bytes(text: str, with_text: bool = True) -> bytes:
    content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET" if with_text else "BT ET"
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    buf = "%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(buf))
        buf += f"{i} 0 obj\n{body}\nendobj\n"
    xref = len(buf)
    buf += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        buf += f"{off:010d} 00000 n \n"
    buf += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    )
    return buf.encode("latin-1", errors="ignore")


def _docx_bytes(text: str) -> bytes:
    import io

    ct = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
    )
    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", ct)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", doc)
    return bio.getvalue()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    made = 0

    font = _find_korean_font()
    try:
        import fpdf  # noqa: F401

        korean_pdf = font is not None
    except ImportError:
        korean_pdf = False

    for i in range(10):
        sk = SKILLS[i % len(SKILLS)]
        years = 2 + i % 5
        scanned = i >= 8  # 마지막 2건은 스캔본 흉내
        path = OUT / f"resume_{i + 1:02d}{'_scan' if scanned else ''}.pdf"

        if korean_pdf:
            name = NAMES[i % len(NAMES)]
            body = (
                f"이력서 — {name}\n"
                f"지원 직무: 백엔드 개발자\n"
                f"경력: {years}년\n"
                f"기술: {sk}\n\n"
                f"자기소개서\n"
                f"대규모 트래픽을 다루는 서비스에서 API 성능을 개선했습니다."
            )
            path.write_bytes(_pdf_korean_bytes(body, font, with_text=not scanned))
        else:
            name = LATIN_NAMES[i % len(LATIN_NAMES)]
            body = f"Resume {name} / exp {years} years / {sk}"
            path.write_bytes(_pdf_bytes(body, with_text=not scanned))
        made += 1

    for i in range(5):
        name = NAMES[i % len(NAMES)]
        text = (
            f"자기소개서 - {name}. 백엔드 개발을 지원합니다. "
            f"주요 기술: {SKILLS[i % len(SKILLS)]}. 경력 {2 + i}년."
        )
        (OUT / f"cover_{i + 1:02d}.docx").write_bytes(_docx_bytes(text))
        made += 1

    for i in range(5):
        # 실제 HWP 바이너리가 아니다 — 폴백 경로 검증용 더미
        (OUT / f"resume_{i + 1:02d}.hwp").write_bytes(b"HWP Document File\x00" + bytes(64))
        made += 1

    mode = f"한글 PDF (font: {font})" if korean_pdf else "영문 PDF (fpdf2/한글폰트 없음)"
    print(f"샘플 {made}건 생성 → {OUT}\nPDF 모드: {mode}")


if __name__ == "__main__":
    main()
