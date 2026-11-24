"""审核闭环：闸门拦人 + 状态机不可回转 + 队列过滤。"""
import pytest

from app.core.exceptions import BizError
from app.models import Adventurer
from app.services import audit_service, commission_service, commission_state

async def _paid_order(db, item, player):
    """只走到「待接单」——接单正是被闸门拦的那一步。"""
    o = await commission_service.create_order(
        db, player.id, [{"service_item_id": item.id, "qty": 1}], "1", "天空岛")
    await commission_state.transition(db, o.id, "支付成功")
    return o

async def test_pending_cannot_accept(db, on_shelf_item, player, adventurer_row):
    """默认 approved 的 fixture 改成 pending → 接单被拦，业务码精确。"""
    adventurer_row.audit_status = "pending"
    await db.flush()
    o = await _paid_order(db, on_shelf_item, player)
    with pytest.raises(BizError) as ei:
        await commission_state.accept_order(db, o.id, adventurer_row.id)
    assert ei.value.code == "ADVENTURER_NOT_APPROVED"

async def test_approved_can_accept(db, on_shelf_item, player, adventurer_row):
    """通过后立刻放行——证明拦的是审核状态，不是别的东西。"""
    o = await _paid_order(db, on_shelf_item, player)
    got = await commission_state.accept_order(db, o.id, adventurer_row.id)
    assert got.adventurer_id == adventurer_row.id

async def test_no_reverse_transition(db, adventurer_row):
    """fixture 默认 approved → 再拒绝必须 409，不能回转。"""
    with pytest.raises(BizError) as ei:
        await audit_service.set_audit_status(
            db, adventurer_row.id, audit_service.REJECTED
        )
    assert ei.value.code == "AUDIT_ALREADY_DONE"

async def test_pending_queue_excludes_approved(db, adventurer_row, another_player):
    """fixture 里的冒险家是 approved → 待审列表不该有他。"""
    total, items = await audit_service.list_pending_adventurer(db, 1, 50)
    assert all(x.id != adventurer_row.id for x in items)