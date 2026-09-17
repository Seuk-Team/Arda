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
    # 2026-09-17: career_years_source 이어받기 규칙이 이전 detail 을 읽어 판정한다.
    doc_score: int | None = None
    doc_score_detail: dict | None = None
    # 이력서 파일 텍스트 추출(extractor.py) 이후 _build_prompt_vars 가 읽는다
    files: list = field(default_factory=list)

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
    # 실제 응답에 있는 필드. 잘림(max_tokens)을 파싱 실패와 구분하려고 읽는다 —
    # 더블에 없으면 AttributeError 가 Step 실패로 삼켜져 원인이 안 보인다.
    stop_reason: str | None = "end_turn"

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
    def test_step1_파싱_실패는_저장하지_않는다(self, mock_cls, fake_db):
        """**우리가 못 읽은 것과 지원자 서류가 부족한 것은 다르다** (2026-09-01 변경).

        전에는 파싱 실패도 `insufficient: true` 로 저장했다. 그러면 화면에
        "제출물이 부족하다"는 거짓 진술이 남고, 값이 채워졌으니 재생성 대상에서도
        빠진다 — 실제로 운영 15건이 그 상태로 저장됐다. 실패는 미생성(NULL)으로 둔다.
        """
        mock_cls.return_value.messages.create.return_value = FakeResponse(
            content=[FakeContent(text="이건 JSON이 아닙니다")],
        )

        db, app = fake_db
        result = generate_summary(db, app.id)

        assert result is None
        assert app.ai_summary is None
        db.commit.assert_not_called()

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_한도에서_잘려도_거짓_요약을_남기지_않는다(self, mock_cls, fake_db):
        """운영에서 실제로 난 일 — 응답이 max_tokens 에서 잘려 JSON 이 깨졌다."""
        mock_cls.return_value.messages.create.return_value = FakeResponse(
            content=[FakeContent(text='{"insufficient": false, "gist": "여기서 잘림')],
            stop_reason="max_tokens",
        )

        db, app = fake_db
        assert generate_summary(db, app.id) is None
        assert app.ai_summary is None

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

    # v2 신설: 이력서에서 뽑은 career_years 로 폼 값이 빈 자리를 채운다.
    # 프론트가 career_years null 을 "신입" 이라 표시하는데(stage.ts) 이력서에는
    # 경력이 있는 지원자들 (프로덕션 15명 발견 · 2026-09-17) 을 잡기 위한 것이다.
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_career_years_filled_when_form_empty(self, mock_cls, fake_db):
        step1_with_years = json.dumps({
            "insufficient": False,
            "gist": "요약",
            "key_skills": ["Python"],
            "key_experiences": ["3년 백엔드"],
            "career_years": 5,
        }, ensure_ascii=False)
        mock_cls.return_value.messages.create.side_effect = [
            FakeResponse(content=[FakeContent(text=step1_with_years)]),
            FakeResponse(content=[FakeContent(text=STEP2_JSON)]),
            FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
        ]

        db, app = fake_db
        app.career_years = None    # 폼 빈 자리
        generate_summary(db, app.id)

        assert app.career_years == 5
        # 우정 리뷰 #294 제안: AI 로 채운 것을 doc_score_detail 에 표식으로 남긴다.
        assert app.doc_score_detail.get("career_years_source") == "ai"

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_career_years_form_wins_over_ai(self, mock_cls, fake_db):
        # 폼에 지원자가 명시적으로 입력한 값은 AI 가 덮어쓰지 않는다.
        step1_with_years = json.dumps({
            "insufficient": False,
            "gist": "요약",
            "key_skills": ["Python"],
            "key_experiences": ["7년 백엔드"],
            "career_years": 7,
        }, ensure_ascii=False)
        mock_cls.return_value.messages.create.side_effect = [
            FakeResponse(content=[FakeContent(text=step1_with_years)]),
            FakeResponse(content=[FakeContent(text=STEP2_JSON)]),
            FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
        ]

        db, app = fake_db
        app.career_years = 3       # 지원자가 폼에 3 입력
        generate_summary(db, app.id)

        assert app.career_years == 3   # AI 의 7 로 덮이지 않는다
        # 폼 값 그대로면 AI 출처 표식이 없어 "신고값" 이 기본 가정.
        assert "career_years_source" not in app.doc_score_detail

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_career_years_ai_null_leaves_form_alone(self, mock_cls, fake_db):
        # AI 가 null 을 내면 (근무 기간 표시 없음) 폼 값도 건드리지 않는다.
        step1_ai_null = json.dumps({
            "insufficient": False,
            "gist": "요약",
            "key_skills": ["Python"],
            "key_experiences": ["프로젝트 경험"],
            "career_years": None,
        }, ensure_ascii=False)
        mock_cls.return_value.messages.create.side_effect = [
            FakeResponse(content=[FakeContent(text=step1_ai_null)]),
            FakeResponse(content=[FakeContent(text=STEP2_JSON)]),
            FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
        ]

        db, app = fake_db
        app.career_years = None
        generate_summary(db, app.id)

        assert app.career_years is None   # null 그대로

    # 2026-09-17 우정 PR #294 재확인 지적: 두 번째 재생성에서 source="ai" 가 사라지지 않는지.
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_career_years_source_persists_across_regen(self, mock_cls, fake_db):
        step1_with_years = json.dumps({
            "insufficient": False,
            "gist": "요약",
            "key_skills": ["Python"],
            "key_experiences": ["6년 백엔드"],
            "career_years": 6,
        }, ensure_ascii=False)
        # 첫 재생성용 3턴 + 두 번째 재생성용 3턴
        mock_cls.return_value.messages.create.side_effect = [
            FakeResponse(content=[FakeContent(text=step1_with_years)]),
            FakeResponse(content=[FakeContent(text=STEP2_JSON)]),
            FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
            FakeResponse(content=[FakeContent(text=step1_with_years)]),
            FakeResponse(content=[FakeContent(text=STEP2_JSON)]),
            FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
        ]

        db, app = fake_db
        app.career_years = None    # 첫 재생성 전엔 폼 빈 상태

        # 1차 재생성 → source="ai" 저장
        generate_summary(db, app.id)
        assert app.career_years == 6
        assert app.doc_score_detail.get("career_years_source") == "ai"

        # 2차 재생성 → career_years 이미 채워짐 · prev_source == "ai" 이어받아 유지되어야 함
        generate_summary(db, app.id)
        assert app.career_years == 6
        assert app.doc_score_detail.get("career_years_source") == "ai"   # 사라지지 않음

    # AI 가 재평가로 다른 연수를 낼 경우 source="ai" 케이스만 갱신 (폼 신고값은 유지).
    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch("anthropic.Anthropic")
    def test_career_years_updates_when_ai_reevaluates(self, mock_cls, fake_db):
        step1_first  = json.dumps({"insufficient": False, "gist": "g", "key_skills": ["p"],
                                    "key_experiences": ["e"], "career_years": 4}, ensure_ascii=False)
        step1_second = json.dumps({"insufficient": False, "gist": "g", "key_skills": ["p"],
                                    "key_experiences": ["e"], "career_years": 8}, ensure_ascii=False)
        mock_cls.return_value.messages.create.side_effect = [
            FakeResponse(content=[FakeContent(text=step1_first)]),
            FakeResponse(content=[FakeContent(text=STEP2_JSON)]),
            FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
            FakeResponse(content=[FakeContent(text=step1_second)]),
            FakeResponse(content=[FakeContent(text=STEP2_JSON)]),
            FakeResponse(content=[FakeContent(text=STEP3_JSON)]),
        ]

        db, app = fake_db
        app.career_years = None
        generate_summary(db, app.id)
        assert app.career_years == 4

        # 이력서가 갱신돼 AI 가 8년으로 재평가 → source="ai" 케이스라 갱신됨
        generate_summary(db, app.id)
        assert app.career_years == 8
        assert app.doc_score_detail.get("career_years_source") == "ai"

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
