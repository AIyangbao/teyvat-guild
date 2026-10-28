from decimal import Decimal
from sqlalchemy import select
import pytest
from app.models import CommissionItem
from app.core.exceptions import BizError
from app.services import commission_service, commission_state

class TestCreateOrder:
    async def test_success(self, db, on_shelf_item):
        order = await commission_service.create_order(
            db, player_id=1,
            item_inputs=[{"service_item_id": on_shelf_item.id, "qty": 2}],
            game_uid="100000001", server="天空岛",
        )
        assert order.id is not None # flush 后主键已分配
        assert order.total_amount == Decimal("25.00")
        assert order.status == "待支付"
        assert order.pay_deadline is not None
        rows = (await db.execute(
            select(CommissionItem).where(CommissionItem.commission_id == order.id)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].snapshot_name == "测试服务"
        assert rows[0].snapshot_price == Decimal("12.50")
        assert rows[0].quantity == 2

    async def test_item_invalid_when_missing(self, db, on_shelf_item):
        with pytest.raises(BizError) as e:
            await commission_service.create_order(
                db, player_id=1,
                item_inputs=[{"service_item_id": 9999, "qty": 1}],
                game_uid="1", server="天空岛",
            )
        assert e.value.code == "ITEM_INVALID"

    async def test_item_invalid_when_off_shelf(self, db, on_shelf_item):
        on_shelf_item.status = 0
        with pytest.raises(BizError) as e:
            await commission_service.create_order(
                db, player_id=1,
                item_inputs=[{"service_item_id": on_shelf_item.id, "qty": 1}],
                game_uid="1", server="天空岛",
            )
        assert e.value.code == "ITEM_INVALID"

    @pytest.mark.parametrize("qty", [0, 11])   # 边界两端都要测
    async def test_qty_out_of_range(self, db, on_shelf_item, qty):
        with pytest.raises(BizError) as e:
            await commission_service.create_order(
                db, player_id=1,
                item_inputs=[{"service_item_id": on_shelf_item.id, "qty": qty}],
                game_uid="1", server="天空岛",
            )
        assert e.value.code == "QTY_INVALID"

    async def test_empty_items(self,db):
        with pytest.raises(BizError) as e:
          await commission_service.create_order(db,1,[], "1", "天空岛")
        assert e.value.code == "BIZ_ERROR"

    async def test_duplicate_items_tolerated(self,db, on_shelf_item):
        """玩家把同一服务买两次是合法的：两条明细、金额翻倍。"""
        order = await commission_service.create_order(
            db, 1,
            [{"service_item_id": on_shelf_item.id, "qty": 1}] * 2,
            "1", "天空岛",
        )
        assert order.total_amount == Decimal("25.00")

class TestTransition:
    async def test_pay_then_illegal_again(self, db, on_shelf_item):
        order = await commission_service.create_order(
            db, 1, [{"service_item_id": on_shelf_item.id, "qty": 1}], "1", "天空岛",
        )
        order = await commission_state.transition(db, order.id, "支付成功", operator_id=1, operator_role="player")

        assert order.status == "待接单"
        assert order.paid_at is not None
        assert order.accept_deadline is not None

        with pytest.raises(BizError) as e: #再付一次 -> 非法转移
            await commission_state.transition(db, order.id, "支付成功")
        assert e.value.code == "STATE_ILLEGAL"

    async def test_order_not_found(self, db):
        with pytest.raises(BizError) as e:
            await commission_state.transition(db, 999999, "支付成功")
        assert e.value.code == "ORDER_NOT_FOUND"

    async def test_accept_conflict(self, db, on_shelf_item):
        """抢完之后 CAS 条件不再满足 → 第二次必须 ACCEPT_CONFLICT。"""
        order = await commission_service.create_order(
            db, 1, [{"service_item_id": on_shelf_item.id, "qty": 1}], "1", "天空岛",
        )
        order = await commission_state.transition(db, order.id, "支付成功", operator_id=1, operator_role="player")

        order = await commission_state.accept_order(db,order.id, adventurer_id=1)
        assert order.adventurer_id == 1
        assert order.status == "进行中"
        assert order.accepted_at is not None

        with pytest.raises(BizError) as e:
            await commission_state.accept_order(db, order.id, adventurer_id=1)
        assert e.value.code == "ACCEPT_CONFLICT"
