"""注册/登录的出入参。"""
from pydantic import BaseModel, Field

class RegisterIn(BaseModel):
    phone: str = Field(pattern=r"^1\d{10}$")
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=1, max_length=50)

class LoginIn(BaseModel):
    phone: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    nickname: str