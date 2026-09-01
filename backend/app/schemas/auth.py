from pydantic import BaseModel, ConfigDict, Field, model_validator


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str
    role: str = "member"


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeUpdate(BaseModel):
    """내 정보 수정 (G4). 셋 다 선택이지만 비밀번호는 짝으로만 바뀐다.

    email·role 은 여기서 못 바꾼다 — 로그인 식별자와 권한이라 본인이 스스로
    바꿀 것이 아니다. 역할 변경은 admin 의 사용자·권한 화면 소관이다.
    """

    name: str | None = Field(None, min_length=1, max_length=50)
    current_password: str | None = None
    new_password: str | None = Field(None, min_length=8)

    @model_validator(mode="after")
    def _check(self) -> "MeUpdate":
        if self.new_password is not None and not self.current_password:
            # 토큰만 있으면 비밀번호를 바꿀 수 있게 두면, 자리를 비운 사이
            # 화면을 잡은 사람이 계정을 통째로 가져간다.
            raise ValueError("비밀번호를 바꾸려면 현재 비밀번호가 필요합니다")
        if self.name is None and self.new_password is None:
            raise ValueError("바꿀 항목이 없습니다")
        return self


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    is_active: bool = True
