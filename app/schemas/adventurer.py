from decimal import Decimal
from pydantic import BaseModel

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
