"""회사 소개 (company_profile) — 폴백·프롬프트 절·메일 치환.

`app.company` 는 아르 프롬프트·메일 변수 치환의 회사 이름 원본이다. DB 값이 있으면
그것을 쓰고, 없으면 환경변수 폴백. 이 계약이 깨지면 발송 메일이 빈 회사명이 된다.
"""
from __future__ import annotations


from app.hiring.company import get_profile, name_for, prompt_context
from app.shared.mail import build_signature, render, sender_name


def _reset_profile(db):
    """시드 마이그레이션(0014) 이 채운 값을 지워 "빈 회사" 상태로 되돌린다.

    CI 는 alembic upgrade head 를 돌린 뒤 테스트를 실행하므로 시드가 적용된
    상태로 진입한다. 폴백·부분 필드 동작을 확인하는 테스트는 이 함수로
    자기가 원하는 상태를 명시적으로 만들어 시작한다.
    """
    row = get_profile(db)
    row.name = ""
    row.tagline = None
    row.hr_email = None
    row.website = None
    row.description = None
    row.narrative = None
    db.flush()
    return row


class TestNameFor:
    def test_returns_env_fallback_when_row_empty(self, db):
        """name 이 빈 값이면 환경변수 폴백('Arda')."""
        _reset_profile(db)
        assert name_for(db) == "Arda"

    def test_returns_db_value_when_set(self, db):
        row = get_profile(db)
        row.name = "SoundNest"
        db.flush()
        assert name_for(db) == "SoundNest"

    def test_ignores_whitespace_only(self, db):
        row = get_profile(db)
        row.name = "   "
        db.flush()
        # 공백만 있는 값은 환경 폴백으로 — 관리자가 실수로 저장한 빈 문자열이
        # 메일에 "  채용팀 드림" 처럼 나가는 것을 막는다.
        assert name_for(db) == "Arda"


class TestPromptContext:
    def test_minimal_row_has_only_company_name_line(self, db):
        _reset_profile(db)
        text = prompt_context(db)
        # 항상 회사명 한 줄과 규약 한 줄은 나온다 — 그래야 아르가 "회사 정보 절 없음" 을
        # 무근거 창작으로 이해하지 않는다.
        assert "## 회사 정보" in text
        assert "- 회사명: Arda" in text
        assert "지어내지 않고" in text

    def test_includes_narrative_and_description(self, db):
        row = get_profile(db)
        row.name = "SoundNest"
        row.tagline = "팀 협업의 새 표준"
        row.website = "https://soundnest.example"
        row.hr_email = "careers@soundnest.example"
        row.description = "판교 소재 B2B SaaS 스타트업. 팀 협업 도구를 만든다."
        row.narrative = "## 문화\n- 결정은 문서로 남긴다.\n- 실패는 공개한다."
        db.flush()
        text = prompt_context(db)
        assert "SoundNest" in text
        assert "팀 협업의 새 표준" in text
        assert "https://soundnest.example" in text
        assert "careers@soundnest.example" in text
        assert "판교 소재 B2B SaaS 스타트업" in text
        assert "실패는 공개한다" in text

    def test_omits_missing_fields(self, db):
        row = _reset_profile(db)
        row.name = "Arda"
        db.flush()
        text = prompt_context(db)
        assert "한 줄 소개:" not in text
        assert "웹사이트:" not in text
        assert "채용 문의:" not in text


class TestMailUsesProfile:
    def test_render_uses_db_company_name(self, db, admin_user, application, posting):
        row = get_profile(db)
        row.name = "SoundNest"
        db.flush()
        subject, body = render(
            db,
            stage="applied",
            applicant_name=application.name,
            posting_title=posting.title,
            actor_kind="human",
            actor_name=admin_user.name,
        )
        # 시드된 기본 템플릿의 {회사명} 이 SoundNest 로 치환된다
        assert "SoundNest" in subject and "SoundNest" in body
        assert "Arda" not in subject and "Arda" not in body

    def test_render_falls_back_to_env(self, db, admin_user, application, posting):
        _reset_profile(db)
        subject, body = render(
            db, stage="applied", applicant_name=application.name,
            posting_title=posting.title, actor_kind="human", actor_name=admin_user.name,
        )
        assert "Arda" in subject or "Arda" in body

    def test_signature_uses_db_company_name(self, db):
        row = get_profile(db)
        row.name = "SoundNest"
        db.flush()
        # 회사명을 넘겨 주면 그 값을 쓴다 — mail.render 가 지금 그렇게 부른다
        sig = build_signature("applied", "human", "김철수", company_name="SoundNest")
        assert sig.startswith("SoundNest 채용 담당자 김철수")

    def test_sender_name_agent_stage(self):
        # 합격·불합격이 아닌 에이전트 발송은 "아르" 로
        name = sender_name("applied", "agent", None, company_name="SoundNest")
        assert name == "SoundNest 채용 에이전트 아르"
