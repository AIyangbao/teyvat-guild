"""评价读侧闭环：写进去的东西，换个请求能不能原样读回来。"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.exceptions import BizError
from app.models import Adventurer
from app.services import (adventurer_service, commission_service,
                          commission_state, review_service)

async def _done(db, item, player, adv):
    """走到「已完成」的最小路径。故意复制而不是 import test_review 的 helper：
    测试文件之间互相 import 会让 fixture 作用域变乱。"""
    o = await commission_service.create_order(
        db, player.id, [{"service_item_id": item.id, "qty": 1}], "1", "天空岛")
    await commission_state.transition(db, o.id, "支付成功")
    await commission_state.accept_order(db, o.id, adventurer_id=adv.id)
    await commission_state.deliver_by_adventurer(db, o.id, adventurer_id=adv.id)
    await commission_state.confirm_by_player(db, o.id, player_id=player.id)
    return o

async def test_read_none_when_unreviewed(db, on_shelf_item, player, adventurer_row):
    """没评价 → None（200+null），不是异常、不是 404。"""
    o = await _done(db, on_shelf_item, player, adventurer_row)
    assert await review_service.get_review_by_order(db, o.id) is None

async def test_read_back_written_content(db, on_shelf_item, player , adventurer_row):
    """写 4 分+内容，读出来逐字段一致。"""
    o = await _done(db, on_shelf_item, player, adventurer_row)
    await review_service.create_review(db, o.id, player.id, 4, "读回测试")
    r = await review_service.get_review_by_order(db, o.id)
    assert r.commission_id == o.id and r.score == 4 and r.content == "读回测试"

async def test_list_pagination_and_order_no(db, on_shelf_item, player, adventurer_row):
    """两单两评：total=2，page_size=1 只回 1 条，order_no 是 join 出来的真单号。"""
    o1 = await _done(db, on_shelf_item, player, adventurer_row)
    o2 = await _done(db, on_shelf_item, player, adventurer_row)
    await review_service.create_review(db, o1.id, player.id, 5, "第一单")
    await review_service.create_review(db, o2.id, player.id, 3, "第二单")
    total, items = await review_service.list_reviews_by_adventurer(
        db, adventurer_row.id, 1, 1)
    assert total == 2 and len(items) == 1
    assert items[0].score == 3              # created_at desc，新评价在前
    assert items[0].order_no == o2.order_no # 这行证明 join 生效、不是空串

async def test_profile_count_paired_with_rating(db, on_shelf_item, player, adventurer_row):
    """档案卡：0 条时 rating 是默认 5.00，review_count 才是真假判据。"""
    before = await review_service.get_adventurer_profile(db, adventurer_row.id)
    assert before.review_count == 0 and before.rating == Decimal("5.00")
    o = await _done(db, on_shelf_item, player, adventurer_row)
    await review_service.create_review(db, o.id, player.id, 2, "")
    after = await review_service.get_adventurer_profile(db, adventurer_row.id)
    assert after.review_count == 1 and after.rating == Decimal("2.00")

async def test_public_list_keeps_card_fields(db, adventurer_row):
    total, cards = await adventurer_service.list_public_adventurers(db, 1, 10000)
    my_id = adventurer_row.id
    got_ids = [c.id for c in cards]
    assert my_id in got_ids, (
        f"total={total}, my_id={my_id}, got_ids={got_ids[:5]}...(共{len(got_ids)}条)"
    )
    mine = next(c for c in cards if c.id == my_id)
    assert mine.finished_count == adventurer_row.finished_count
