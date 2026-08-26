from enum import Enum
from pydantic import BaseModel


class ErrorCode(str, Enum):
    """에러 코드 — 프론트가 이 값으로 에러를 구분한다."""
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT = "CONFLICT"
    # 401 — 로그인이 안 됐거나 토큰이 유효하지 않다. 프론트는 로그인 화면으로 보낸다.
    UNAUTHORIZED = "UNAUTHORIZED"
    # 403 — 로그인은 됐지만 권한이 없다. 로그인 화면으로 보내면 안 된다 (#60)
    FORBIDDEN = "FORBIDDEN"
    # 410 — 있었지만 끝났다 (마감된 공고, B4). NOT_FOUND 와 섞으면 지원자가
    # "링크가 틀렸나" 와 "이미 끝났다" 를 구분하지 못한다.
    GONE = "GONE"
    INTERNAL = "INTERNAL"


class ErrorResponse(BaseModel):
    """모든 에러 응답의 공통 형식."""
    code: str  # ErrorCode 값
    message: str  # 사용자가 읽을 메시지
    request_id: str  # 요청 추적 id
