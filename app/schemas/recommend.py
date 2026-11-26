from decimal import Decimal
from pydantic import BaseModel

class ScoreBreakdown(BaseModel):
     """推荐分拆解：让「为什么推荐他」可解释，而不是一个黑箱总分。"""
     same_server: int
     online: int
     rating: int
     experience: int
     load: int

class RecommendationOut(BaseModel):
     adventurer_id: int
     game_nickname: str
     server: str
     rating: Decimal
     review_count: int
     finished_count: int
     active_count: int
     online_status: str
     same_server: bool
     score: int
     reasons: ScoreBreakdown

