"""에이전트 응답 형식 · 지원자 조회 도메인 서비스 (ADR-0035 Phase 4).

`application/api/agent.py` 라우터에서 pure 서비스 함수들을 여기로:
- 형식 함수 (라우터 응답 · 도구 결과 렌더)
- 지원자 조회 (이름 → 후보 리스트)

`_handle_direct` · `_choices_from_tool_results` · `_stage_rule_reply` 등 상호 의존이
많은 헬퍼는 라우터에 남아 있다 — 그것들은 Pydantic 스키마와 얽혀 있어 이번 이관
범위 밖. 앞으로 필요할 때 계속 여기로 옮겨 온다.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Application
from app.shared.labels import STAGE_LABEL_KR

if TYPE_CHECKING:
    from app.application.api.agent import ChatResponse, ChoiceOut, PendingActionOut, ToolCallOut


CHOICE_LIMIT = 6


def stage_label(stage: str | None) -> str | None:
    return STAGE_LABEL_KR.get(stage or "", "") or None


def lookup_applicants_by_name(db: Session, name: str) -> list[Application]:
    """정확 일치 우선, 없으면 부분 일치. 동명이인 감지 위해 다 반환."""
    exact = db.execute(
        select(Application).where(Application.name == name).limit(5)
    ).scalars().all()
    if exact:
        return list(exact)
    partial = db.execute(
        select(Application).where(Application.name.like(f"%{name}%")).limit(5)
    ).scalars().all()
    return list(partial)


def format_reply(tool_name: str, result: dict) -> str:
    """도구 결과 → 담당자용 짧은 한국어 답변. LLM 없이 코드로 렌더.

    복잡한 요약이 필요 없는 뻔한 결과에 쓴다 — 지원자 목록·상세 등. 이메일
    본문 같은 자연어 생성은 여기 못 잡으니 라우터가 아예 안 낚아채고 LLM 로.
    """
    if tool_name == "search_applications":
        results = result.get("results") or []
        count = result.get("count", len(results))
        if count == 0:
            return "검색 결과가 없어요. 다른 조건으로 찾아볼까요?"
        header = f"지원자 {count}명이 검색됐어요."
        lines = []
        for a in results[:5]:
            name = a.get("name", "?")
            years = a.get("career_years")
            years_str = f" ({years}년)" if isinstance(years, int) else ""
            skills = a.get("skills") or []
            skills_str = ", ".join(skills[:3]) if skills else ""
            stage_kr = STAGE_LABEL_KR.get(a.get("current_stage", ""), "")
            parts = [f"- **{name}**{years_str}"]
            if stage_kr:
                parts.append(f"— {stage_kr}")
            if skills_str:
                parts.append(f"— {skills_str}")
            lines.append(" ".join(parts))
        tail = f"\n\n(총 {count}명 중 상위 5명 표시)" if count > 5 else ""
        return "\n".join([header, *lines]) + tail
    # 다른 읽기 도구 확장 대비 — 원시 JSON 잘라서 폴백
    return f"{tool_name} 결과: {json.dumps(result, ensure_ascii=False)[:200]}"
