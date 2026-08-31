"""에이전트 도구 정의 + 디스패치 (M3).

Claude tool_use 프로토콜 기준으로 JSON 정의를 내보내고,
도구 이름으로 실행 함수를 찾아 호출한다.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import User

from .read import (
    get_application,
    get_schedule_status,
    list_availability,
    list_interviews,
    list_postings,
    search_applications,
    search_users,
)
from .write import (
    WRITE_TOOL_NAMES,
    assign_interviewer,
    change_stage,
    create_schedule_proposal,
    draft_email,
)

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_applications",
        "description": (
            "지원자를 검색합니다. 이름·이메일 키워드(q), 의미 기반 검색(semantic), "
            "단계(stage), 공고 ID, 정렬(sort: created_at|score), 순서(order: asc|desc), "
            "결과 수(limit, 기본 10·최대 50)를 조합할 수 있습니다. "
            "'Python 경험자', '클라우드 인프라' 같은 역량 기반 검색은 semantic을 씁니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "이름 또는 이메일 검색어 (부분 일치)",
                },
                "semantic": {
                    "type": "string",
                    "description": "의미 기반 검색어 (스킬·경력·자기소개서 내용으로 유사도 검색)",
                },
                "stage": {
                    "oneOf": [
                        {"type": "string"},
                        {"type": "array", "items": {"type": "string"}},
                    ],
                    "description": "단계 필터: applied, screening, interview, accepted, rejected",
                },
                "posting_id": {
                    "type": "integer",
                    "description": "채용공고 ID로 필터",
                },
                "sort": {
                    "type": "string",
                    "enum": ["created_at", "score"],
                    "description": "정렬 기준 (기본: created_at)",
                },
                "order": {
                    "type": "string",
                    "enum": ["asc", "desc"],
                    "description": "정렬 방향 (기본: desc)",
                },
                "limit": {
                    "type": "integer",
                    "description": "최대 결과 수 (기본 10, 최대 50). 더 필요할 때만 올린다",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_application",
        "description": (
            "지원자 한 명의 상세 정보를 조회합니다. "
            "프로필, AI 요약, 평가, 단계 이력, 첨부파일 목록을 포함합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "지원자 ID",
                },
            },
            "required": ["application_id"],
        },
    },
    {
        "name": "list_postings",
        "description": (
            "채용공고 목록을 조회합니다. "
            "공고별 지원자 수를 포함하며, 공고 이름으로 posting_id를 찾을 때 씁니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_availability",
        "description": (
            "면접관의 가용 시간(면접 가능한 시간대)을 조회합니다. "
            "면접관 ID가 필수이며, from/to로 기간을 좁힐 수 있습니다. "
            "일정 제안을 만들기 전에 면접관의 빈 시간을 확인할 때 씁니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "interviewer_id": {
                    "type": "integer",
                    "description": "면접관 사용자 ID",
                },
                "from": {
                    "type": "string",
                    "description": "이 시각 이후 종료분만 (ISO 8601)",
                },
                "to": {
                    "type": "string",
                    "description": "이 시각 이전 시작분만 (ISO 8601)",
                },
            },
            "required": ["interviewer_id"],
        },
    },
    {
        "name": "get_schedule_status",
        "description": (
            "지원자의 최신 면접 일정 제안 상태를 조회합니다. "
            "상태는 none(제안 없음), proposed(제안됨), confirmed(확정), "
            "expired(만료), canceled(취소) 중 하나입니다. "
            "confirmed이면 확정된 면접 시간과 면접관 이름을 포함합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "지원자 ID",
                },
            },
            "required": ["application_id"],
        },
    },
    {
        "name": "list_interviews",
        "description": (
            "확정된 면접 일정 목록을 조회합니다. "
            "from/to로 기간을 좁히고, mine=true로 내 면접만 볼 수 있습니다. "
            "면접관은 항상 본인 건만 조회됩니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "from": {
                    "type": "string",
                    "description": "이 시각 이후 시작분만 (ISO 8601)",
                },
                "to": {
                    "type": "string",
                    "description": "이 시각 이전 시작분만 (ISO 8601)",
                },
                "mine": {
                    "type": "boolean",
                    "description": "내가 면접관인 건만 (기본: false)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "search_users",
        "description": (
            "내부 사용자(면접관, 어드민 등)를 검색합니다. "
            "이름이나 이메일 키워드(q)로 찾고, 역할(role)로 필터할 수 있습니다. "
            "면접관을 이름으로 찾아 ID를 확인할 때 씁니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "q": {
                    "type": "string",
                    "description": "이름 또는 이메일 검색어 (부분 일치)",
                },
                "role": {
                    "type": "string",
                    "enum": ["admin", "member"],
                    "description": "역할 필터",
                },
                "limit": {
                    "type": "integer",
                    "description": "최대 결과 수 (기본 20, 최대 50)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "change_stage",
        "description": (
            "지원자의 단계를 변경합니다. "
            "applied→screening→interview→accepted 순서로 전진하며, "
            "rejected는 어느 단계에서든 가능합니다. 한 칸씩만 전진할 수 있습니다. "
            "이 도구는 사용자 확인 후에만 실행됩니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "지원자 ID",
                },
                "to_stage": {
                    "type": "string",
                    "enum": ["applied", "screening", "interview", "accepted", "rejected"],
                    "description": "변경할 단계",
                },
                "reason": {
                    "type": "string",
                    "description": (
                        "단계 변경 사유. to_stage 가 rejected 이면 필수입니다 (D8) — "
                        "없으면 사용자에게 사유를 되물으세요."
                    ),
                },
            },
            "required": ["application_id", "to_stage"],
        },
    },
    {
        "name": "create_schedule_proposal",
        "description": (
            "지원자에게 면접 일정 후보를 제안합니다. "
            "배정된 면접관의 가용 시간에서 후보 슬롯을 자동 생성하고, "
            "지원자에게 선택 링크가 담긴 메일을 보냅니다. "
            "면접관이 배정돼 있고 가용 시간이 등록돼 있어야 합니다. "
            "이 도구는 사용자 확인 후에만 실행됩니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "지원자 ID",
                },
                "slot_minutes": {
                    "type": "integer",
                    "description": "슬롯 길이(분). 기본 60, 15~240",
                },
                "max_slots": {
                    "type": "integer",
                    "description": "최대 후보 슬롯 수. 기본 5, 1~20",
                },
            },
            "required": ["application_id"],
        },
    },
    {
        "name": "assign_interviewer",
        "description": (
            "지원자에게 면접관을 배정합니다. 어드민 권한이 필요합니다. "
            "이 도구는 사용자 확인 후에만 실행됩니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "지원자 ID",
                },
                "interviewer_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "배정할 면접관 ID 목록",
                },
            },
            "required": ["application_id", "interviewer_ids"],
        },
    },
    {
        "name": "draft_email",
        "description": (
            "지원자에게 보낼 이메일 초안을 생성합니다. "
            "목적(purpose)에 따라 면접 안내, 합격, 불합격 등의 템플릿을 사용합니다. "
            "이 도구는 사용자 확인 후에만 실행됩니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "application_id": {
                    "type": "integer",
                    "description": "지원자 ID",
                },
                "purpose": {
                    "type": "string",
                    "enum": ["interview", "accepted", "rejected", "general"],
                    "description": "이메일 목적 (기본: general)",
                },
            },
            "required": ["application_id"],
        },
    },
]


_DISPATCH = {
    "search_applications": search_applications,
    "get_application": get_application,
    "list_postings": list_postings,
    "search_users": search_users,
    "list_availability": list_availability,
    "get_schedule_status": get_schedule_status,
    "list_interviews": list_interviews,
    "change_stage": change_stage,
    "create_schedule_proposal": create_schedule_proposal,
    "assign_interviewer": assign_interviewer,
    "draft_email": draft_email,
}


def execute_tool(
    name: str, arguments: dict, db: Session, user: User
) -> str:
    """도구를 실행하고 결과를 JSON 문자열로 반환한다."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return json.dumps({"error": f"알 수 없는 도구: {name}"}, ensure_ascii=False)
    result = fn(db, user, arguments)
    return json.dumps(result, ensure_ascii=False, default=str)
