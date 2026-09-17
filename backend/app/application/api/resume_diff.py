"""이력서 변동 요약 API (2026-09-17 신설).

두 시나리오에 답한다:
  A. 특정 두 지원자를 명시적으로 비교 (앵커 mismatch 조사 등).
     GET /applications/{application_id}/resume-diff?prev=<prev_application_id>
  B. 접수된 지원자의 「가장 최근 이전 지원」을 자동 찾아 비교.
     GET /applications/{application_id}/resume-diff/prior

응답 스키마: {"changed", "summary", "changes", "prev_application_id", "prev_created_at"}

담당자만 볼 수 있다. 지원자에게는 내려주지 않는다 (integrity.py 와 같은 원칙).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.resume_diff import compute_resume_diff, is_same_person, latest_prior_diff
from app.db import get_db
from app.deps import get_current_user
from app.models import Application, User
from app.adapter.outbound.pg.application_pg_repository import PgApplicationRepository

router = APIRouter(prefix="/api/v1", tags=["resume-diff"])


class ResumeChangeItem(BaseModel):
    field: str
    before: str = ""
    after: str = ""
    note: str = ""


class ResumeDiffOut(BaseModel):
    changed: bool
    summary: str
    changes: list[ResumeChangeItem] = []
    prev_application_id: int | None = None
    prev_created_at: str | None = None


def _get_or_404(db: Session, application_id: int) -> Application:
    app = PgApplicationRepository(db).get(application_id)
    if app is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "지원자를 찾을 수 없습니다")
    return app


@router.get(
    "/applications/{application_id}/resume-diff",
    response_model=ResumeDiffOut,
)
def get_resume_diff(
    application_id: int,
    prev: int = Query(..., description="비교 대상 이전 지원자의 application_id"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """두 지원자 이력서를 대조해 변동을 요약한다.

    prev 지원자와 이번 지원자가 **같은 사람** 이어야 한다 (이메일 일치 or 이름+연락처
    일치). 다른 사람이면 400. 무결성 앵커 mismatch 를 조사할 때, 재접수 케이스를
    확인할 때 쓴다.
    """
    curr_app = _get_or_404(db, application_id)
    prev_app = _get_or_404(db, prev)

    if not is_same_person(curr_app, prev_app):
        raise HTTPException(
            http.HTTP_400_BAD_REQUEST,
            "동일 인물이 아닙니다 (이메일도 이름·연락처도 일치하지 않음).",
        )

    diff = compute_resume_diff(db, curr_app, prev_app)
    diff["prev_application_id"] = prev_app.id
    diff["prev_created_at"] = (
        prev_app.created_at.isoformat() if prev_app.created_at else None
    )
    return diff


@router.get(
    "/applications/{application_id}/resume-diff/prior",
    response_model=ResumeDiffOut | dict,
)
def get_prior_resume_diff(
    application_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """이 지원자와 동일 인물의 가장 최근 이전 지원과의 이력서 변동 요약.

    이전 지원이 없으면 `{"changed": false, "summary": "이전 지원 이력 없음", "changes": []}`
    를 돌려준다 (404 로 안 감 · 프론트가 조용히 처리하기 편하게).
    """
    curr_app = _get_or_404(db, application_id)
    result = latest_prior_diff(db, curr_app)
    if result is None:
        return {
            "changed": False,
            "summary": "이전 지원 이력이 없습니다.",
            "changes": [],
            "prev_application_id": None,
            "prev_created_at": None,
        }
    return result
