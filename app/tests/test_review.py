from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import BizError
from app.models import Adventurer
from app.services import commission_service, commission_state, review_service

async def _completed_order(db, item, player, adventurer):
    """走到「已完成」的最小路径：下单 → 支付 → 接单 → 交付 → 确认。"""
    order = await commission_service.create_order(
        db, player.id, [{"service_item_id": item.id, "qty": 1}], "1", "天空岛")
    await commission_state.transition(db, order.id, "支付成功",
                                      )
    await commission_state.accept_order(db, order.id, adventurer_id=adventurer.id)
    await commission_state.deliver_by_adventurer(db, order.id, adventurer_id=adventurer.id)
    await commission_state.confirm_by_player(db, order.id, player_id=player.id)
    return order

async def test_review_updates_rating(db, on_shelf_item,player, adventurer_row):
    order = await _completed_order(db, on_shelf_item, player, adventurer_row)
    review, rating = await review_service.create_review(
        db, order.id, player.id, 4, "交付很稳"
    )

    assert review.score == 4
    assert rating == Decimal("4.00")
    adv = (await db.execute(
        select(Adventurer).where(Adventurer.id == adventurer_row.id)
    )).scalar_one()
    assert adv.rating == Decimal("4.00")

async def test_rating_is_average_not_last(db, on_shelf_item, player, adventurer_row):
    """两次评价：4 分 + 2 分 → 平均 3.00，证明是全量 AVG 不是覆盖。"""
    o1 = await _completed_order(db, on_shelf_item, player, adventurer_row)
    await review_service.create_review(db, o1.id, player.id, 4, "")

    o2 = await _completed_order(db, on_shelf_item, player, adventurer_row)
    _, rating = await review_service.create_review(db, o2.id, player.id, 2, "")

    assert rating == Decimal("3.00")

async def test_review_twice_conflict(db, on_shelf_item, player, adventurer_row):
    order = await _completed_order(db, on_shelf_item, player, adventurer_row)
    await review_service.create_review(db, order.id, player.id, 5, "")

    with pytest.raises(BizError) as ei:
        await review_service.create_review(db, order.id, player.id, 1, "")
    assert ei.value.code == "REVIEW_EXISTS"

async def test_review_requires_completed(db, on_shelf_item, player, adventurer_row):
    order = await commission_service.create_order(
        db, player.id, [{"service_item_id": on_shelf_item.id, "qty":1}], "1", "天空岛")

    with pytest.raises(BizError) as ei:
        await review_service.create_review(db, order.id, player.id, 5, "")
    assert ei.value.code == "REVIEW_STATE_ILLEGAL"

async def test_review_by_other_player_forbidden(db, on_shelf_item, player,
                                                another_player, adventurer_row):
    order = await _completed_order(db, on_shelf_item, player, adventurer_row)

    with pytest.raises(BizError) as ei:
        await review_service.create_review(db, order.id, another_player.id, 5, "")
    assert ei.value.code == "FORBIDDEN"