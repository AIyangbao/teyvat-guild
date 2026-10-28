from decimal import Decimal

import pytest

from app.db import AsyncSessionLocal
from app.models import ServiceItem

@pytest.fixture
async def db():
    """每个测试独享一个 session，结束后 rollback —— 库永远不留痕。"""
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()

@pytest.fixture
async def on_shelf_item(db):
    """在架商品：flush 拿 id，但不 commit —— 随主 fixture 一起回滚。"""
    item = ServiceItem(
        category_id=1, name="测试服务",
        price=Decimal("12.50"), duration_min=60, status=1,
    )
    db.add(item)
    await db.flush()
    return item