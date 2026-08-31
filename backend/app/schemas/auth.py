from pydantic import BaseModel, ConfigDict


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


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
