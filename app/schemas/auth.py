"""注册/登录的出入参。"""
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class RegisterIn(BaseModel):
    phone: str = Field(pattern=r"^1\d{10}$")
    password: str = Field(min_length=8, max_length=64)
    nickname: str = Field(min_length=1, max_length=50)

    # 白名单：客户端只能选这两种。绝不能放开成任意字符串，
    # 否则 role="admin" 可从公开注册接口自造管理员，绕过管理端鉴权
    role: Literal["player", "adventurer"] = "player"
    game_uid: str | None = Field(default=None, max_length=20)
    server: str | None = Field(default=None, max_length=20)
    game_nickname: str | None = Field(default=None, max_length=50) 
    @model_validator(mode="after")
    def _adventurer_needs_profile(self):
        if self.role == "adventurer" and not all(
            (self.game_uid, self.server, self.game_nickname)
        ):
            raise ValueError("冒险家注册需填写 game_uid / server / game_nickname")
        return self

class LoginIn(BaseModel):
    phone: str
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    role: str
    nickname: str