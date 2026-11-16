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