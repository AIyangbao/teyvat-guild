"""派单推荐：只读，不碰状态机。

硬过滤：只推荐已审核的冒险家（和 accept_order 闸门同源）。
软打分：同服 / 在线 / 真实评分 / 经验 / 负载，逐项可解释。
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state_machine import IN_PROGRESS, PENDING_VERIFY
from app.models import Adventurer, Commission, Review
from app.schemas.recommend import RecommendationOut, ScoreBreakdown

# 权重集中放这里，调参不用翻逻辑
W_SAME_SERVER = 40
W_ONLINE = 20
W_RATING_PER_POINT = 10
RATING_BASELINE = Decimal("3.00")
W_EXPERIENCE_PER_ORDER = 2
EXPERIENCE_CAP = 10
W_LOAD_PENALTY = 8

def score_one(*, same_server: bool, online: bool, rating: Decimal,
              review_count: int, finished_count: int, active_count: int
              ) -> tuple[int, ScoreBreakdown]:
    """纯函数打分，不碰 DB —— 可以直接单测，改权重不怕误伤查询。"""
    parts = ScoreBreakdown(
        same_server=W_SAME_SERVER if same_server else 0,
        online=W_ONLINE if online else 0,
        # review_count=0 时 rating 是模型默认 5.00，不是真评分 → 按基准算 0 分
        rating=int((rating - RATING_BASELINE) * W_RATING_PER_POINT)
               if review_count > 0 else 0,
        # 经验加成封顶：防止老号靠历史单数无限霸榜
        experience=min(finished_count, EXPERIENCE_CAP) * W_EXPERIENCE_PER_ORDER,
        # 每有一单在途扣 8 分：手里活越多越不推荐
        load=-active_count * W_LOAD_PENALTY,
    )
    return sum(parts.model_dump().values()), parts

async def recommend_for_order(
        db: AsyncSession, order_id: int, limit: int = 5
) -> list[RecommendationOut]:
    """给定委托，返回 Top N 推荐冒险家。委托不存在返回空列表，路由层判 404。"""
    order = await db.get(Commission, order_id)
    if order is None:
        return []

    # 相关子查询：每个冒险家的在途单数 / 真实评价数。
    # 用子查询而不是 LEFT JOIN + COUNT(DISTINCT)，避免两个 join 产生笛卡尔积。
    active_sq = (
        select(func.count()).select_from(Commission)
        .where(Commission.adventurer_id == Adventurer.id,
               Commission.status.in_([IN_PROGRESS, PENDING_VERIFY]))
        .scalar_subquery()
    )
    review_sq = (
        select(func.count()).select_from(Review)
        .join(Commission, Commission.id == Review.commission_id)
        .where(Commission.adventurer_id == Adventurer.id)
        .scalar_subquery()
    )

    # WHERE 命中 idx_dispatch 最左前缀；排序放 Python（见文件头说明）
    rows = (await db.execute(
        select(Adventurer, active_sq.label("active"), review_sq.label("reviews"))
        .where(Adventurer.audit_status == "approved")
    )).all()

    result = []
    for adv, active, reviews in rows:
        same = adv.server == order.server
        score, parts = score_one(
            same_server=same, online=adv.online_status == "online",
            rating=adv.rating, review_count=reviews,
            finished_count=adv.finished_count, active_count=active, 
        )
        result.append(RecommendationOut(
            adventurer_id=adv.id, game_nickname=adv.game_nickname,
            server=adv.server, rating=adv.rating, review_count=reviews,
            finished_count=adv.finished_count, active_count=active,
            online_status=adv.online_status, same_server=same,
            score=score, reasons=parts,
        ))
    # 分数降序；同分按 id 升序 —— 稳定的 tie-break，翻页/刷新不跳位
    result.sort(key=lambda x: (-x.score, x.adventurer_id))
    return result[:limit]