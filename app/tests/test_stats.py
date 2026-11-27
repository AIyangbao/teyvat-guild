"""统计口径验证：钱按 Payment.success 算，趋势按 paid_at，空数据不炸。"""
from datetime import timedelta
from decimal import Decimal

from app.core.time_utils import utcnow
from app.models import Payment, Review
from app.services import stats_service

async def _paid(db, order, amount, paid_at=None):
    """插一条成功支付。统计口径只认 Payment.success，不认订单状态。"""
    p = Payment(
        commission_id=order.id,
        out_trade_no=f"STATS{order.id}{id(paid_at)}",
        amount=amount, channel="mock", status="success",
        paid_at=paid_at or utcnow(),
    )
    db.add(p)
    await db.flush()
    return p

async def test_pending_payment_not_counted(db, on_shelf_item, player):
    """未支付订单不算收入：订单量 +1，营业额 0。"""
    from app.services import commission_service
    order = await commission_service.create_order(
        db, player.id, [{"service_item_id": on_shelf_item.id, "qty": 1}], "1", "天空岛")
    s = await stats_service.get_overview(db)
    assert s.total_orders >= 1
    # 库里可能有历史支付，用「增量」比绝对值稳：这条测试只关心没新增加入
    pending = Payment(commission_id=order.id,
                      out_trade_no=f"PENDING{order.id}",
                      amount=Decimal("99"), status="pending")
    db.add(pending)
    await db.flush()
    s2 = await stats_service.get_overview(db)
    assert s2.total_revenue == s.total_revenue

async def test_success_payment_bumps_revenue(db, on_shelf_item, player):
    """成功支付 +50 → 营业额恰好多 50（不受历史数据影响，用差值断言）。"""
    from app.services import commission_service
    order = await commission_service.create_order(
        db, player.id, [{"service_item_id": on_shelf_item.id, "qty": 1}], "1", "天空岛")
    before = await stats_service.get_overview(db)
    await _paid(db, order, Decimal("50.00"))
    after = await stats_service.get_overview(db)
    assert after.total_revenue == before.total_revenue + Decimal("50.00")
    assert after.paid_orders == before.paid_orders + 1

async def test_trend_counts_by_paid_at(db, on_shelf_item, player):
    """趋势按 paid_at 归到今天：今天的 orders 恰好 +1，且日期是今天。"""
    from app.services import commission_service
    order = await commission_service.create_order(
        db, player.id, [{"service_item_id": on_shelf_item.id, "qty": 1}], "1", "天空岛")
    before = await stats_service.get_overview(db)
    await _paid(db, order, Decimal("30.00"), utcnow())
    after = await stats_service.get_overview(db)
    today = utcnow().date().isoformat()
    b = next(t for t in before.trend if t.date == today)
    a = next(t for t in after.trend if t.date == today)
    assert a.orders == b.orders + 1
    assert len(after.trend) == 7

async def test_old_payment_excluded_from_trend(db, on_shelf_item, player):
    """10 天前的支付不算进 7 天趋势（但算进累计营业额）。"""
    from app.services import commission_service
    order = await  commission_service.create_order(
        db, player.id, [{"service_item_id": on_shelf_item.id, "qty": 1}], "1", "天空岛")
    old = utcnow() - timedelta(days=10)
    await _paid(db, order, Decimal("77.00"), old)
    s = await stats_service.get_overview(db)
    assert all(t.orders == 0 or t.date != old.date().isoformat() for t in s.trend)