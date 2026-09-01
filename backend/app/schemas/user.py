"""사용자 관리 (A4) 요청·응답 형태. 설정 화면 "사용자·권한" 탭이 쓴다."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator

from app.models import ROLES


class UserItemOut(BaseModel):
    """목록 한 줄. 비밀번호 해시는 당연히 나가지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class UserListOut(BaseModel):
    items: list[UserItemOut]
    count: int


class UserPatch(BaseModel):
    """역할·활성 변경. 둘 다 선택이지만 하나는 있어야 한다.

    이름·이메일·비밀번호는 여기서 못 바꾼다 — 남의 계정 정보를 admin 이 대신
    고치는 경로는 만들지 않는다. 본인이 `PATCH /auth/me` 로 바꾼다.
    """

    role: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _check(self) -> "UserPatch":
        if self.role is None and self.is_active is None:
            raise ValueError("바꿀 항목이 없습니다")
        if self.role is not None and self.role not in ROLES:
            raise ValueError(f"역할은 {' 또는 '.join(ROLES)} 여야 합니다")
        return self
