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
        assert "chain_summarize" in result
        assert "agent" in result

    def test_versions_sorted_ascending(self):
        for versions in available().values():
            assert versions == sorted(versions)


class TestResolve:
    def test_latest_version(self):
        path, version = resolve("chain_summarize")
        assert path.exists()
        assert version >= 1

    def test_explicit_version(self):
        path, version = resolve("chain_summarize", 1)
        assert version == 1
        assert "v1" in path.name

    def test_unknown_prompt_raises(self):
        with pytest.raises(PromptNotFound):
            resolve("nonexistent_prompt_xyz")

    def test_unknown_version_raises(self):
        with pytest.raises(PromptNotFound):
            resolve("chain_summarize", 9999)


class TestLoad:
    def test_returns_text_and_tag(self):
        text, tag = load("chain_summarize")
        assert len(text) > 0
        assert tag.startswith("chain_summarize.v")

    def test_tag_format(self):
        _, tag = load("chain_summarize", 1)
        assert tag == "chain_summarize.v1"


class TestVariables:
    def test_chain_summarize_has_expected_vars(self):
        # ADR-0022 체이닝으로 갈라진 뒤, 1단계는 제출물만 본다.
        # 공고 정보는 2단계(chain_evaluate)로 넘어갔다.
        assert variables("chain_summarize") == {"resume_text", "cover_letter_text"}

    def test_chain_evaluate_takes_posting_and_summary(self):
        assert variables("chain_evaluate") == {
            "posting_title",
            "posting_requirements",
            "profile_summary",
        }

    def test_chain_recommend_takes_evaluation(self):
        assert variables("chain_recommend") == {"posting_title", "evaluation_result"}


class TestRender:
    def test_fills_placeholders(self):
        text, tag = render(
            "chain_summarize",
            resume_text="경력 5년",
            cover_letter_text="지원합니다",
        )
        assert "경력 5년" in text
        assert "지원합니다" in text
        assert "{{" not in text
        assert tag == "chain_summarize.v1"

    def test_missing_variable_raises(self):
        with pytest.raises(MissingVariable):
            render("chain_summarize", resume_text="이력서만")

    def test_extra_variables_ignored(self):
        text, _ = render(
            "chain_summarize",
            resume_text="이력",
            cover_letter_text="자소서",
            extra_unused="무시됨",
        )
        assert "이력" in text
