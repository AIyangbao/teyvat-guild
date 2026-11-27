"""管理端统计聚合：只读，所有口径集中在文件头注释，改口径只改这里。

口径约定（重要，别随手改）：
- 营业额 = Payment.status='success' 的 amount 之和。未支付/关闭的不算收入。
- 趋势按 Payment.paid_at（钱到账那天），不是 Commission.created_at（下单那天）。
  财务对账看的是前者，用后者会让跨天订单记错月份。
- 订单总量 = 全部 Commission，含未支付/取消 —— 这是「业务量」不是「收入」。
- 平均评分 = Review.score 全表平均；无评价返回 None，不返回 0 或默认 5。
"""
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state_machine import ALL_STATES
from app.core.time_utils import utcnow
from app.models import Adventurer, Commission, Payment, Review
from app.schemas.stats import (
    DailyTrend, ServerSlice, StatsOverviewOut, StatusSlice, TopAdventurer,
)

async  def get_overview(db: AsyncSession, days: int = 7) -> StatsOverviewOut:
    """一次聚合所有看板维度。days 控制趋势图天数（含今天）。"""
    # ---- KPI：营业额 / 支付笔数 ----
    pay_row = (await db.execute(
        select(func.coalesce(func.sum(Payment.amount),0),
               func.count())
        .where(Payment.status == "success")
    )).one()
    total_revenue, paid_orders = pay_row

    total_orders = (await db.execute(
        select(func.count()).select_from(Commission)
    )).scalar_one()

    # ---- KPI：平均评分（无评价 → None）----
    avg = (await db.execute(select(func.avg(Review.score)))).scalar()
    avg_rating = None if avg is None else Decimal(str(round(avg,2)))

    # ---- 趋势：按 paid_at 的日期分组，只取最近 days 天 ----
    since = utcnow() - timedelta(days=days - 1)
    trend_rows = (await db.execute(
        select(
            func.date(Payment.paid_at).label("day"),
            func.coalesce(func.sum(Payment.amount), 0).label("amount"),
            func.count().label("orders"),
        )
        .where(Payment.status == "success", Payment.paid_at >= since)
        .group_by(func.date(Payment.paid_at))
        .order_by(func.date(Payment.paid_at))
    )).all()
    # 数据库只返回「有数据的天」。前端 X 轴要连续，缺的天在 service 补齐 0，
    # 否则折线会把 3 号和 6 号直接连起来，掩盖中间两天的空档。
    by_day = {r.day: (r.amount, r.orders) for r in trend_rows}
    trend = []
    for i in range(days):
        d = (utcnow() - timedelta(days=days - 1 - i)).date()
        amount, orders = by_day.get(d,(0,0))
        trend.append(DailyTrend(date=d.isoformat(),
                                amount=Decimal(str(amount)),orders=orders))

    # ---- 状态分布 ----
    status_rows = (await db.execute(
        select(Commission.status, func.count())
        .group_by(Commission.status)
    )).all()
    counts = dict(status_rows)
    status_breakdown = [StatusSlice(name=s, count=counts.get(s,0))
                        for s in ALL_STATES if counts.get(s,0) > 0]

    # ---- 服务器分布（订单量 + 金额）----
    server_rows = (await db.execute(
        select(Commission.server, func.count(),
               func.coalesce(func.sum(Commission.total_amount),0))
        .group_by(Commission.server)
        .order_by(func.count().desc())
    )).all()
    server_breakdown = [ServerSlice(name=r[0], count=r[1],
                                    amount=Decimal(str(r[2])))
                                    for r in server_rows]

    # ---- Top 冒险家：按完成数排序 ----
    top_rows = (await db.execute(
        select(Adventurer.id, Adventurer.game_nickname,
               Adventurer.finished_count, Adventurer.rating,
               func.count(Review.id).label("reviews"))
        .outerjoin(Review, Review.adventurer_id == Adventurer.id)
        .group_by(Adventurer.id)
        .order_by(Adventurer.finished_count.desc(), Adventurer.id.asc())
        .limit(5)
    )).all()
    top_adventurers = [TopAdventurer(
        adventurer_id=r.id, game_nickname=r.game_nickname,
        finished_count=r.finished_count, rating=r.rating,
        review_count=r.reviews,
    ) for r in top_rows]

    return StatsOverviewOut(
        total_revenue=Decimal(str(total_revenue)),
        total_orders=total_orders, paid_orders=paid_orders,
        avg_rating=avg_rating, trend=trend,
        status_breakdown=status_breakdown,
        server_breakdown=server_breakdown,
        top_adventurers=top_adventurers,
    )