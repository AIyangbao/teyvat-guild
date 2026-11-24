from decimal import Decimal
from pydantic import BaseModel
from datetime import datetime
from typing import Literal

class AdventurerProfileOut(BaseModel):
    id: int
    game_nickname: str
    server: str
    skill_tags: list | None
    rating: Decimal
    review_count: int
    finished_count: int

class AdventurerCardOut(BaseModel):
    """大厅卡片。刻意不给 game_uid —— 那是身份/联系方式，不该公开展示。"""
    id: int
    game_nickname: str
    server: str
    skill_tags: list | None
    rating: Decimal
    finished_count: int

class AdventurerPageOut(BaseModel):
    total: int
    items: list[AdventurerCardOut]

class PendingAdventurerOut(BaseModel):
    """管理端待审卡片：和大厅名录不同，这里要暴露 game_uid 供管理员核对身份。"""
    id: int
    user_id: int
    game_nickname: str
    game_uid: str
    server: str
    skill_tags: list | None
    audit_status: str
    created_at: datetime

class PendingAdventurerPageOut(BaseModel):
    total: int
    items: list[PendingAdventurerOut]

class AuditIn(BaseModel):
    target: Literal["approved", "rejected"] # 白名单，杜绝自造状态