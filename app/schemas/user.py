"""个人资料：只暴露自己的字段，phone 给本人看但不给外人。"""
from pydantic import BaseModel, Field

class ProfileOut(BaseModel):
    id: int
    nickname: str
    avatar: str
    role: str
    phone: str
    # 冒险家专属，玩家为 None
    game_nickname: str | None = None
    server: str | None = None
    skill_tags: list | None = None
    online_status: str | None = None

class ProfileUpdate(BaseModel):
    nickname: str = Field(min_length=1, max_length=50)

class AdventurerUpdate(BaseModel):
    game_nickname: str = Field(min_length=1, max_length=50)
    skill_tags: list[str] = Field(default_factory=list, max_length=10)
    online_status: str = Field(default="online", pattern="^(online|offline)$")