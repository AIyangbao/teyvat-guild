from datetime import timedelta
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from app.core.exceptions import BizError
from app.core.state_machine import SETTLED
from app.core.time_utils import utcnow
from app.models import Adventurer
from app.services import commission_service, commission_state, review_service
from app.tasks.timeout_scanner import _candidates

async def _completed_order(db, item, player, adventurer):
    """走到「已完成」的最小路径：下单 → 支付 → 接单 → 交付 → 确认。"""
    order = await commission_service.create_order(
        db, player.id, [{"service_item_id": item.id, "qty": 1}], "1", "天空岛")
    await commission_state.transition(db, order.id, "支付成功")
    await commission_state.accept_order(db, order.id, adventurer_id=adventurer.id)
    await commission_state.deliver_by_adventurer(db, order.id, adventurer_id=adventurer.id)
    await commission_state.confirm_by_player(db, order.id, player_id=player.id)
    return order

async def _another_adventurer(db, another_player):
    """第二个冒险家：测列表隔离用，随机 game_uid 防撞唯一约束。"""
    adv = Adventurer(
        user_id=another_player.id,
        game_uid=uuid.uuid4().hex[:10],
        server="天空岛",
        game_nickname="另一个冒险家",
        audit_status="approved",
    )
    db.add(adv)
    await db.flush()
    return adv

async def test_settle_bumps_finished_count(db, on_shelf_item, player, adventurer_row):
    """结算三件套：状态归档 + 时间戳落位 + 完单数入账。"""
    order = await _completed_order(db, on_shelf_item, player, adventurer_row)
    settled = await commission_state.settle_order(db, order.id)

    assert settled.status == SETTLED
    assert settled.settled_at is not None
    adv = (await db.execute(
        select(Adventurer).where(Adventurer.id == adventurer_row.id)
    )).scalar_one()
    assert adv.finished_count == 1

async def test_settle_twice_blocked(db, on_shelf_item, player, adventurer_row):
     """重复结算被状态机挡住：COMPLETED→SETTLED 只能走一次。"""
     order = await _completed_order(db, on_shelf_item, player, adventurer_row)
     await commission_state.settle_order(db, order.id)

     with pytest.raises(BizError) as ei:
         await commission_state.settle_order(db, order.id)
     assert ei.value.code == "STATE_ILLEGAL"

     # 挡住之后计数也不能重复入账
     adv = (await db.execute(
         select(Adventurer).where(Adventurer.id == adventurer_row.id)
     )).scalar_one()
     assert adv.finished_count == 1

async def test_scan_finds_only_expired_completed(db, on_shelf_item, player, adventurer_row):
    """扫描器只捞过期单：finished_at 超 7 天的在候选里，刚完成的不在。"""
    old_order = await _completed_order(db, on_shelf_item, player, adventurer_row)
    old_order.finished_at = utcnow() - timedelta(days=8)
    await db.flush()

    fresh_order = await _completed_order(db, on_shelf_item, player, adventurer_row)
    _,_, settle_ids = await _candidates(db)
    assert old_order.id in settle_ids
    assert fresh_order.id not in settle_ids

async def test_accepted_list_isolated(db, on_shelf_item, player, another_player, adventurer_row):
    """冒险家只看到自己接的单；状态过滤生效。"""
    adv2 = await _another_adventurer(db, another_player)
    o1 = await _completed_order(db, on_shelf_item, player, adventurer_row)
    o2 = await _completed_order(db, on_shelf_item, player, adv2)

    total, rows = await commission_service.list_by_adventurer(
        db, adventurer_row.id, 1, 20)
    assert total == 1
    assert rows[0].id == o1.id

    _, rows_ing = await commission_service.list_by_adventurer(
        db, adv2.id, 1, 20, status="已完成"
    )
    assert [r.id for r in rows_ing] == [o2.id]

async def test_review_after_settle(db, on_shelf_item, player, adventurer_row):
    """结算后玩家仍可评价（评价系统支持 COMPLETED 和 SETTLED 两态）。"""
    order = await _completed_order(db, on_shelf_item, player, adventurer_row)
    await commission_state.settle_order(db, order.id)

    review, rating = await review_service.create_review(
        db, order.id, player.id, 5, "结算后补的评价")
    assert review.score == 5
    assert rating == Decimal("5.00")