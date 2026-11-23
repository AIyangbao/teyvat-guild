from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

class ReviewIn(BaseModel):
    score: int = Field(ge=1, le=5)
    content: str = Field(default="", max_length=500)

class ReviewOut(BaseModel):
    id: int
    commission_id: int
    score: int
    content: str
    created_at: datetime
    adventurer_rating: Decimal # 评价后的最新评分（前端可直接刷新展示）

class ReviewReadOut(BaseModel):
    """单条评价（读侧）。刻意不含 adventurer_rating：那是写入时刻的快照。"""
    id: int
    commission_id: int
    score: int
    content: str
    created_at: datetime

class ReviewItemOut(BaseModel):
    """评价列表的一行。不返回 player_id / 昵称：
    评价内容公开可读，但「谁下的单」属于交易关系，没必要暴露给大厅游客。"""
    id: int
    commission_id: int
    order_no: str
    score: int
    content: str
    created_at: datetime

class ReviewPageOut(BaseModel):
    total: int
    items: list[ReviewItemOut]
