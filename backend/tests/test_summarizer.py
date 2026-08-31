"""요약 생성 테스트 — Claude API mock 기반 (ADR-0018 3단계 체이닝)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from app.agent.summarizer import _build_prompt_vars, generate_summary


# ── fixtures ──


@dataclass
class FakePosting:
    title: str = "백엔드 개발자"
    description: str = "Python 3년 이상"


@dataclass
class FakeApp:
    id: int = 1
    job_posting_id: int = 10
    name: str = "김도현"
    education: str = "서울대 컴공"
    career_years: int = 5
    skills: list[str] | None = None
    self_intro: str = "열심히 하겠습니다"
    ai_summary: str | None = None
    ai_summary_at: object = None
    ai_summary_model: str | None = None

    def __post_init__(self):
        if self.skills is None:
            self.skills = ["Python", "FastAPI"]


@pytest.fixture()
def fake_db():
    db = MagicMock()
    posting = FakePosting()
    app = FakeApp()
    db.get = lambda model, id_: (
        app if model.__name__ == "Application" else posting
    )
    return db, app


# ── _build_prompt_vars ──


class TestBuildPromptVars:
    def test_full_data(self, fake_db):
        db, app = fake_db
        result = _build_prompt_vars(db, app)
        assert result["posting_title"] == "백엔드 개발자"
        assert result["posting_requirements"] == "Python 3년 이상"
        assert "김도현" in result["resume_text"]
        assert "Python" in result["resume_text"]
        assert result["cover_letter_text"] == "열심히 하겠습니다"

    def test_missing_name(self, fake_db):
        db, app = fake_db
        app.name = None
        result = _build_prompt_vars(db, app)
        assert "이름" not in result["resume_text"]

    def test_missing_all_profile(self, fake_db):
        db, app = fake_db
        app.name = None
        app.education = None
        app.career_years = None
        app.skills = None
        result = _build_prompt_vars(db, app)
        assert result["resume_text"] == "제출된 내용 없음"

    def test_missing_self_intro(self, fake_db):
        db, app = fake_db
        app.self_intro = None
        result = _build_prompt_vars(db, app)
        assert result["cover_letter_text"] == "제출된 내용 없음"

    def test_missing_posting(self):
        db = MagicMock()
        app = FakeApp()
        db.get = lambda model, id_: (
            app if model.__name__ == "Application" else None
        )
        result = _build_prompt_vars(db, app)
        assert result["posting_title"] == "공고 정보 없음"
        assert result["posting_requirements"] == "요건 정보 없음"


# ── generate_summary (3단계 체이닝) ──


@dataclass
class FakeUsage:
    input_tokens: int = 200
    output_tokens: int = 100


@dataclass
class FakeContent:
    text: str = '{"gist":"요약","fit":"적합","concerns":"없음"}'
    type: str = "text"


@dataclass
class FakeResponse:
    content: list = None
    usage: FakeUsage = None

    def __post_init__(self):
        if self.content is None:
            self.content = [FakeContent()]
        if self.usage is None:
            self.usage = FakeUsage()


STEP1_JSON = json.dumps({
    "insufficient": False,
    "gist": "Python 백엔드 개발 경험이 풍부한 지원자다.",
    "key_skills": ["Python", "FastAPI"],
    "key_experiences": ["3년간 백엔드 개발"],
}, ensure_ascii=False)

STEP2_JSON = json.dumps({
    "fit_score": 4,
    "fit": ["Python 3년 요건 충족"],
    "concerns": ["AWS 경험 미확인"],
}, ensure_ascii=False)

STEP3_JSON = json.dumps({
    "action": "면접 권유",
    "reasons": ["기술 요건 충족도 높음"],
    "check_points": ["AWS 운영 경험 구체적으로 확인"],
}, ensure_ascii=False)


def _make_chain_responses():
    """3단계 응답 목록을 만든다."""
    return [
        FakeResponse(content=[FakeContent(text=STEP1_JSON)]),
        FakeResponse(content=[FakeContent(text=STEP2_JSON)]),
        FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
    ]


class TestGenerateSummary:
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_success(self, mock_cls, fake_db):
        mock_cls.return_value.messages.create.side_effect = _make_chain_responses()

        db, app = fake_db
        result = generate_summary(db, app.id)

        assert result is not None
        parsed = json.loads(result)
        assert parsed["gist"] == "Python 백엔드 개발 경험이 풍부한 지원자다."
        assert parsed["fit_score"] == 4
        assert parsed["recommendation"]["action"] == "면접 권유"
        assert app.ai_summary == result
        assert app.ai_summary_model is not None
        db.commit.assert_called_once()

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_step1_insufficient_skips_rest(self, mock_cls, fake_db):
        insufficient = json.dumps({
            "insufficient": True, "gist": "", "key_skills": [], "key_experiences": [],
        })
        mock_cls.return_value.messages.create.return_value = FakeResponse(
            content=[FakeContent(text=insufficient)],
        )

        db, app = fake_db
        result = generate_summary(db, app.id)

        parsed = json.loads(result)
        assert parsed["insufficient"] is True
        assert mock_cls.return_value.messages.create.call_count == 1

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_step1_invalid_json_returns_insufficient(self, mock_cls, fake_db):
        mock_cls.return_value.messages.create.return_value = FakeResponse(
            content=[FakeContent(text="이건 JSON이 아닙니다")],
        )

        db, app = fake_db
        result = generate_summary(db, app.id)

        parsed = json.loads(result)
        assert parsed["insufficient"] is True

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_step2_invalid_json_continues(self, mock_cls, fake_db):
        responses = [
            FakeResponse(content=[FakeContent(text=STEP1_JSON)]),
            FakeResponse(content=[FakeContent(text="평가 실패")]),
            FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
        ]
        mock_cls.return_value.messages.create.side_effect = responses

        db, app = fake_db
        result = generate_summary(db, app.id)

        parsed = json.loads(result)
        assert parsed["gist"] != ""
        assert parsed["fit_score"] is None
        assert parsed["fit"] == []

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_cost_logged_with_chain_tags(self, mock_cls, fake_db):
        mock_cls.return_value.messages.create.side_effect = _make_chain_responses()

        db, app = fake_db
        generate_summary(db, app.id)

        assert "chain_summarize.v" in app.ai_summary_model
        assert "chain_evaluate.v" in app.ai_summary_model
        assert "chain_recommend.v" in app.ai_summary_model

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_three_api_calls(self, mock_cls, fake_db):
        mock_cls.return_value.messages.create.side_effect = _make_chain_responses()

        db, app = fake_db
        generate_summary(db, app.id)

        assert mock_cls.return_value.messages.create.call_count == 3

    def test_missing_application(self):
        db = MagicMock()
        db.get.return_value = None
        result = generate_summary(db, 999)
        assert result is None

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_api_key(self, fake_db):
        db, app = fake_db
        import os
        old = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result = generate_summary(db, app.id)
            assert result is None
        finally:
            if old:
                os.environ["ANTHROPIC_API_KEY"] = old
