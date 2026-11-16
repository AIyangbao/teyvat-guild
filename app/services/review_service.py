"""评价：校验 → 落库 → 重算冒险家评分。不 commit —— 事务边界归调用方（路由）。"""
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.state_machine import COMPLETED, SETTLED
from app.models import Adventurer, Commission, Review

async def create_review(
        db: AsyncSession, order_id: int, player_id: int,
        score: int, content: str = ""
) -> tuple[Review, Decimal]:
    """玩家评价已完成的委托，返回 (评价记录, 冒险家最新评分)。"""
    # 锁单：存在性 / 归属 / 状态，三关一次过（FOR UPDATE 同时挡住重复提交的竞态）
    order = (await db.execute(
        select(Commission).where(Commission.id == order_id).with_for_update()
    )).scalar_one_or_none()
    if order is None:
        raise BizError("委托不存在", code="ORDER_NOT_FOUND")
    if order.player_id != player_id:
        raise BizError("无权评价该委托", code="FORBIDDEN")
    if order.status not in (COMPLETED, SETTLED):
        raise BizError("该委托尚未完成, 暂不能评价", code="REVIEW_STATE_ILLEGAL")
    if order.adventurer_id is None:
        raise BizError("该委托没有接单冒险家", code="REVIEW_STATE_ILLEGAL")

    aid = order.adventurer_id

    # 锁冒险家行：同一冒险家的评分重算串行化，避免两个事务同时算 AVG 互相覆盖
    (await db.execute(
        select(Adventurer.id).where(Adventurer.id == aid).with_for_update()
    )).scalar_one()

    # 落库。唯一约束 uq_review_commission_id 是并发下的最后防线
    review = Review(
        commission_id=order_id, player_id=player_id,
        adventurer_id=aid, score=score, content=content,
    )
    
    db.add(review)
    try:
        await db.flush()
    except IntegrityError:
        raise BizError("该委托已评价", code="REVIEW_EXISTS")

    #  全量重算评分：AVG 比增量公式稳（无精度漂移），而且自带"自愈"——
    #  每次评价都按最新全量算，历史脏值会被下一次评价纠正
    avg = (await db.execute(
        select(func.avg(Review.score)).where(Review.adventurer_id == aid)
    )).scalar()
    rating = Decimal(str(avg)).quantize(Decimal("0.01"))
    await db.execute(
        update(Adventurer).where(Adventurer.id == aid)
        .values(rating=rating)
        .execution_options(synchronize_session="fetch")
    )
    return review, rating