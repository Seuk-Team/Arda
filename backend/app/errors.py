from enum import Enum
from pydantic import BaseModel


class ErrorCode(str, Enum):
    """에러 코드 — 프론트가 이 값으로 에러를 구분한다."""
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    CONFLICT = "CONFLICT"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL = "INTERNAL"


class ErrorResponse(BaseModel):
    """모든 에러 응답의 공통 형식."""
    code: str  # ErrorCode 값
    message: str  # 사용자가 읽을 메시지
    request_id: str  # 요청 추적 id
