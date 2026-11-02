"""超时判定 + 流转的单测。

直接调 services/commission_timeout，不起扫描循环 —— 这样 db fixture 的
事务内数据才可见。调度壳 scan_once 的正确性由「手动跑一轮」验收。
"""
from datetime import timedelta

from sqlalchemy import select

from app.config import settings
from app.core.time_utils import utcnow
from app.models import CommissionLog
from app.services import commission_service, commission_state
from app.services.commission_timeout import close_pay_timeout, retry_accept_timeout

async def _make_order(db, item, *, paid: bool = False):
     """造一张单：默认待支付；paid=True 则推到待接单。"""
     order = await commission_service.create_order(
          db, player_id=1,
          item_inputs=[{"service_item_id": item.id, "qty": 1}],
          game_uid="100000001", server="天空岛",
     )
     if paid:
          await commission_state.transition(db, order.id, "支付成功",
                                            operator_id=1, operator_role="player")
     await db.flush()
     return order

async def _events(db, order_id):
    rows = (await db.execute(
          select(CommissionLog).where(CommissionLog.commission_id == order_id)
     )).scalars().all()
    return [r.event for r in rows]

class TestPayTimeout:
     async def test_closes_expired_order(self, db, on_shelf_item):
          order = await _make_order(db, on_shelf_item)
          order.pay_deadline = utcnow() - timedelta(seconds=1)

          assert await close_pay_timeout(db, order.id) is True
          assert order.status == "已关闭"
          assert await _events(db, order.id) == ["支付超时"]

     async def test_ignores_unexpired_order(self, db, on_shelf_item):
          order = await _make_order(db, on_shelf_item)

          assert await close_pay_timeout(db, order.id) is False
          assert order.status == "待支付"

     async def test_paid_order_not_closed(self, db, on_shelf_item):
          order = await _make_order(db, on_shelf_item,paid=True)
          order.pay_deadline = utcnow() - timedelta(seconds=1)

          assert await close_pay_timeout(db,order.id) is False
          assert order.status == "待接单"

class TestAcceptTimeout:
    async def test_self_transition_bumps_retry_and_deadline(self, db, on_shelf_item):
         order = await _make_order(db, on_shelf_item, paid=True)
         order.accept_deadline = utcnow() - timedelta(seconds=1)

         assert await retry_accept_timeout(db, order.id) is True
         assert order.status == "待接单"
         assert order.pool_retry == 1
         assert order.accept_deadline > utcnow()
         assert await _events(db, order.id) == ["支付成功", "超时无人接"]

    async def test_second_call_is_noop(self, db, on_shelf_item):
         """第一次已把 deadline 推走，同一轮再扫必须不动 —— 防重复的关键。"""
         order = await _make_order(db, on_shelf_item, paid=True)
         order.accept_deadline = utcnow() - timedelta(seconds=1)

         assert await retry_accept_timeout(db, order.id) is True
         assert await retry_accept_timeout(db, order.id) is False
         assert order.pool_retry == 1

    async def test_closes_after_max_retry(self, db, on_shelf_item):
         order = await _make_order(db, on_shelf_item, paid=True)
         order.pool_retry = settings.max_pool_retry
         order.accept_deadline = utcnow() - timedelta(seconds=1)

         assert await retry_accept_timeout(db, order.id) is True
         assert order.status == "已取消"
         assert (await _events(db, order.id))[-1] == "无人接单关闭"

    async def test_pending_pay_order_untouched(self, db, on_shelf_item):
        """未支付单没有 accept_deadline，不能被接单超时逻辑碰到。"""
        order = await _make_order(db, on_shelf_item)

        assert await retry_accept_timeout(db, order.id) is False
        assert order.status == "待支付"
        assert order.pool_retry == 0