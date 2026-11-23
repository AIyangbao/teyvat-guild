"""评价：校验 → 落库 → 重算冒险家评分。不 commit —— 事务边界归调用方（路由）。"""
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.state_machine import COMPLETED, SETTLED
from app.models import Adventurer, Commission, Review
from app.schemas.adventurer import AdventurerProfileOut
from app.schemas.review import ReviewItemOut, ReviewReadOut
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

async def get_review_by_order(db: AsyncSession, order_id: int) -> ReviewReadOut | None:
    """查某单评价。没有评价返回 None —— 「未评价」是正常业务状态，不是错误。

    用 200 + null 而不是 404：前端刷新详情页要靠它恢复 reviewed 状态，
    404 会被 request.js 拦截器弹成红色报错，把正常状态当异常最烦人。
    """
    r = (await db.execute(
        select(Review).where(Review.commission_id == order_id)
    )).scalar_one_or_none() # commission_id 有 unique 约束，最多一条
    if r is None:
        return None
    return ReviewReadOut(
        id=r.id, commission_id=r.commission_id, score=r.score,
        content=r.content, created_at=r.created_at,
    )

async def list_reviews_by_adventurer(
        db: AsyncSession, adventurer_id: int, page: int, page_size: int
) -> tuple[int, list[ReviewItemOut]]:
    """冒险家评价分页。终于命中 idx_review_adventurer(adventurer_id, created_at)。

    order_no 用一条 inner join 取，不冗余存字段：order_no 下单后不变，
    join 一次搞定，比「加列 + alembic 迁移 + 回填」省一整条链路。
    """
    if await db.get(Adventurer, adventurer_id) is None:
        raise BizError("冒险家不存在", code="ADVENTURER_NOT_FOUND")

    total = (await db.execute(
        select(func.count()).select_from(Review)
        .where(Review.adventurer_id == adventurer_id)
    )).scalar_one()

    rows = (await db.execute(
        select(Review.id, Review.commission_id, Commission.order_no,
               Review.score, Review.content, Review.created_at)
        .join(Commission, Commission.id == Review.commission_id)
        .where(Review.adventurer_id == adventurer_id)
        .order_by(Review.created_at.desc(), Review.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).all()
    items = [ReviewItemOut(
        id=r.id, commission_id=r.commission_id, order_no=r.order_no,
        score=r.score, content=r.content, created_at=r.created_at,
    ) for r in rows]
    return total, items

async def get_adventurer_profile(
        db: AsyncSession, adventurer_id: int
) -> AdventurerProfileOut:
    """档案卡。评分 + 评价数必须成对返回。"""
    adv = (await db.execute(
        select(Adventurer).where(Adventurer.id == adventurer_id)
    )).scalar_one_or_none()
    if adv is None:
        raise BizError("冒险家不存在", code="ADVENTURER_NOT_FOUND")

    cnt = (await db.execute(
        select(func.count()).select_from(Review)
        .where(Review.adventurer_id == adventurer_id)
    )).scalar_one()

    return AdventurerProfileOut(
        id=adv.id, game_nickname=adv.game_nickname, server=adv.server,
        skill_tags=adv.skill_tags, rating=adv.rating,
        review_count=cnt, finished_count=adv.finished_count,
    )