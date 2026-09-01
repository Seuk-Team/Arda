"""파일 텍스트 추출 검증 — S3 는 전부 가짜다 (실호출 없음).

핵심 계약: **어떤 실패도 None 으로 끝난다** — 예외가 밖으로 나가면
요약 전체가 죽는다 (extractor.py 첫 문단).
"""

import io
import zipfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agent import extractor
from app.agent.summarizer import _build_prompt_vars


def _file(s3_key: str, kind: str = "resume"):
    return SimpleNamespace(id=1, s3_key=s3_key, kind=kind)


def _fake_s3(body: bytes):
    """get_object 가 body 를 돌려주는 가짜 클라이언트."""
    client = MagicMock()
    client.get_object.return_value = {"Body": io.BytesIO(body)}
    return client


def _docx_bytes(*paragraphs: str) -> bytes:
    xml = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f"<w:document><w:body>{xml}</w:body></w:document>")
    return buf.getvalue()


def _hwpx_bytes(*paragraphs: str) -> bytes:
    xml = "".join(f"<hp:p><hp:t>{p}</hp:t></hp:p>" for p in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Contents/section0.xml", f"<hs:sec>{xml}</hs:sec>")
    return buf.getvalue()


class TestExtractText:
    def test_docx(self):
        body = _docx_bytes("백엔드 3년 경력", "FastAPI &amp; PostgreSQL")
        with patch.object(extractor.s3, "_client", return_value=_fake_s3(body)):
            text = extractor.extract_text(_file("applications/x/resume.docx"))
        assert text == "백엔드 3년 경력\nFastAPI & PostgreSQL"

    def test_hwpx(self):
        body = _hwpx_bytes("자기소개", "성실합니다")
        with patch.object(extractor.s3, "_client", return_value=_fake_s3(body)):
            text = extractor.extract_text(_file("applications/x/cover_letter.hwpx"))
        assert text == "자기소개\n성실합니다"

    def test_긴_텍스트는_MAX_CHARS_로_잘린다(self):
        body = _docx_bytes("가" * (extractor.MAX_CHARS + 500))
        with patch.object(extractor.s3, "_client", return_value=_fake_s3(body)):
            text = extractor.extract_text(_file("applications/x/resume.docx"))
        assert text is not None
        assert len(text) == extractor.MAX_CHARS

    def test_hwp_는_미지원이라_None(self):
        with patch.object(extractor.s3, "_client", return_value=_fake_s3(b"x")):
            assert extractor.extract_text(_file("applications/x/resume.hwp")) is None

    def test_s3_실패는_None(self):
        client = MagicMock()
        client.get_object.side_effect = RuntimeError("연결 실패")
        with patch.object(extractor.s3, "_client", return_value=client):
            assert extractor.extract_text(_file("applications/x/resume.pdf")) is None

    def test_깨진_파일은_None(self):
        with patch.object(extractor.s3, "_client", return_value=_fake_s3(b"not-a-zip")):
            assert extractor.extract_text(_file("applications/x/resume.docx")) is None

    def test_빈_문서는_None(self):
        body = _docx_bytes()
        with patch.object(extractor.s3, "_client", return_value=_fake_s3(body)):
            assert extractor.extract_text(_file("applications/x/resume.docx")) is None


class TestBuildPromptVars:
    """파일 텍스트가 요약 입력에 합쳐지는지 — 추출기는 가짜다."""

    def _app(self, files=()):
        return SimpleNamespace(
            job_posting_id=1, name="김테스트", education="한별대", career_years=3,
            skills=["Python"], self_intro="자기소개 본문", files=list(files),
        )

    def _db(self):
        db = MagicMock()
        db.get.return_value = SimpleNamespace(title="백엔드", description="요건")
        return db

    def test_이력서_파일_텍스트가_resume_text_에_들어간다(self):
        app = self._app([_file("a/resume.pdf", "resume")])
        with patch("app.agent.extractor.extract_text", return_value="이력서 알맹이"):
            vars = _build_prompt_vars(self._db(), app)
        assert "[이력서 파일 내용]" in vars["resume_text"]
        assert "이력서 알맹이" in vars["resume_text"]
        assert "이름: 김테스트" in vars["resume_text"]

    def test_자기소개서_파일은_cover_letter_text_에_붙는다(self):
        app = self._app([_file("a/cover_letter.docx", "cover_letter")])
        with patch("app.agent.extractor.extract_text", return_value="파일 자소서"):
            vars = _build_prompt_vars(self._db(), app)
        assert vars["cover_letter_text"] == "자기소개 본문\n\n파일 자소서"

    def test_추출_실패해도_폼_필드로_돈다(self):
        app = self._app([_file("a/resume.pdf", "resume")])
        with patch("app.agent.extractor.extract_text", return_value=None):
            vars = _build_prompt_vars(self._db(), app)
        assert "[이력서 파일 내용]" not in vars["resume_text"]
        assert "이름: 김테스트" in vars["resume_text"]
        assert vars["cover_letter_text"] == "자기소개 본문"

    def test_파일이_없으면_기존과_동일(self):
        vars = _build_prompt_vars(self._db(), self._app())
        assert "이름: 김테스트" in vars["resume_text"]
        assert vars["cover_letter_text"] == "자기소개 본문"
