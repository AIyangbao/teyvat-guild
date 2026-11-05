"""服务目录写操作的测试。直调 service：db fixture 的事务内数据走 HTTP 看不到。"""
from decimal import Decimal

import pytest

from sqlalchemy import select

from app.core.exceptions import BizError
from app.models import CommissionItem
from app.schemas.catalog import CategoryIn, CategoryUpdate, ItemIn, ItemUpdate
from app.services import catalog_service, commission_service

async def _make_category(db, name="代打", sort=1):
    return await catalog_service.create_category(db, CategoryIn(name=name, sort=sort))

class TestCategory:
    async def test_create_and_list(self, db):
        await _make_category(db, "代打")
        await _make_category(db, "周本")
        names = [c.name for c in await catalog_service.list_categories(db)]
        assert "代打" in names and "周本" in names

    async def test_duplicate_name_rejected(self, db):
        await _make_category(db, "重名")
        with pytest.raises(BizError) as e:
            await _make_category(db, "重名")
        assert e.value.code == "CATEGORY_DUPLICATE"

    async def test_partial_update(self, db):
        cat = await _make_category(db, "旧名")
        out = await catalog_service.update_category(
            db, cat.id, CategoryUpdate(name="新名", status=0))
        assert out.name == "新名" and out.status == 0
        assert out.sort == cat.sort #没传的字段不动

    async def test_delete_blocked_when_items_exist(self, db):
        cat = await _make_category(db, "有商品")
        await catalog_service.create_item(db, ItemIn(
            category_id=cat.id, name="某服务", price=Decimal("10.00")))
        with pytest.raises(BizError) as e:
            await catalog_service.delete_category(db, cat.id)
        assert e.value.code == "CATEGORY_IN_USE"

    async def test_delete_empty_category(self, db):
        cat = await _make_category(db, "空分类")
        await catalog_service.delete_category(db, cat.id)
        assert all(c.id != cat.id for c in await catalog_service.list_categories(db))

    async def test_rename_to_existing_rejected(self, db):
        """改成别人已用的名字必须被拦在业务层，不能漏到 unique 约束变 500。"""
        await _make_category(db, "甲")
        cat = await _make_category(db, "乙")
        with pytest.raises(BizError) as e:
            await catalog_service.update_category(db, cat.id, CategoryUpdate(name="甲"))
        assert e.value.code == "CATEGORY_DUPLICATE"

class TestItem:
    async def test_create_requires_existing_category(self, db):
        with pytest.raises(BizError) as e:
            await catalog_service.create_item(db,ItemIn(
                category_id=999999, name="孤儿", price=Decimal("1.00")))
        assert e.value.code == "CATEGORY_NOT_FOUND"

    async def test_price_change_does_not_affect_history(self, db):
        """改价只影响新订单：历史明细存的是下单那一刻的快照价。"""
        cat = await _make_category(db, "快照")
        item = await catalog_service.create_item(db, ItemIn(
            category_id= cat.id, name="深渊代打", price=Decimal("68.00")))

        order = await commission_service.create_order(
            db, player_id=1,
            item_inputs=[{"service_item_id": item.id, "qty": 1}],
            game_uid="100000001", server="天空岛",
        )

        await catalog_service.update_item(
            db, item.id, ItemUpdate(price=Decimal("88.00")))

        snap = (await db.execute(
            select(CommissionItem).where(CommissionItem.commission_id == order.id)
        )).scalars().all()
        assert snap[0].snapshot_price == Decimal("68.00")
        assert order.total_amount == Decimal("68.00")

    async def test_list_items_filters(self, db):
        cat = await _make_category(db, "筛选")
        on = await catalog_service.create_item(db, ItemIn(
            category_id=cat.id, name="在架", price=Decimal("5.00"), status=1))
        off = await catalog_service.create_item(db, ItemIn(
            category_id=cat.id, name="下架", price=Decimal("6.00"), status=0))

        ids = [r.id for r in await catalog_service.list_items(db, category_id=cat.id, status=1)]
        assert on.id in ids and off.id not in ids
