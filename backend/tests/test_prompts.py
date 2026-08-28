"""프롬프트 로더 테스트 — render·resolve·available·variables 검증."""

import pytest

from app.agent.prompts import (
    MissingVariable,
    PromptNotFound,
    available,
    load,
    render,
    resolve,
    variables,
)


class TestAvailable:
    def test_returns_known_prompts(self):
        result = available()
        assert "summarize" in result
        assert "agent" in result

    def test_versions_sorted_ascending(self):
        for versions in available().values():
            assert versions == sorted(versions)


class TestResolve:
    def test_latest_version(self):
        path, version = resolve("summarize")
        assert path.exists()
        assert version >= 1

    def test_explicit_version(self):
        path, version = resolve("summarize", 1)
        assert version == 1
        assert "v1" in path.name

    def test_unknown_prompt_raises(self):
        with pytest.raises(PromptNotFound):
            resolve("nonexistent_prompt_xyz")

    def test_unknown_version_raises(self):
        with pytest.raises(PromptNotFound):
            resolve("summarize", 9999)


class TestLoad:
    def test_returns_text_and_tag(self):
        text, tag = load("summarize")
        assert len(text) > 0
        assert tag.startswith("summarize.v")

    def test_tag_format(self):
        _, tag = load("summarize", 1)
        assert tag == "summarize.v1"


class TestVariables:
    def test_summarize_has_expected_vars(self):
        result = variables("summarize")
        expected = {"posting_title", "posting_requirements", "resume_text", "cover_letter_text"}
        assert result == expected


class TestRender:
    def test_fills_placeholders(self):
        text, tag = render(
            "summarize",
            posting_title="백엔드 개발자",
            posting_requirements="Python 3년",
            resume_text="경력 5년",
            cover_letter_text="지원합니다",
        )
        assert "백엔드 개발자" in text
        assert "Python 3년" in text
        assert "{{" not in text

    def test_missing_variable_raises(self):
        with pytest.raises(MissingVariable):
            render("summarize", posting_title="제목만")

    def test_extra_variables_ignored(self):
        text, _ = render(
            "summarize",
            posting_title="제목",
            posting_requirements="요건",
            resume_text="이력",
            cover_letter_text="자소서",
            extra_unused="무시됨",
        )
        assert "제목" in text
