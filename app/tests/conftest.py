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

import uuid
from app.models import ServiceItem, User, Adventurer

def _new_user() -> User:
    return User(
        phone="139" + uuid.uuid4().hex[:8],
        nickname="测试玩家",
        password_hash="x",
    )
@pytest.fixture
async def player(db):
    """测试玩家：随机手机号防撞种子数据，flush 拿 id 后返回。"""
    user = _new_user()
    db.add(user)
    await db.flush()
    return user

@pytest.fixture
async def another_player(db):
    """测试玩家：随机手机号防撞种子数据，flush 拿 id 后返回。"""
    user = _new_user()
    db.add(user)
    await db.flush()
    return user

@pytest.fixture
async def adventurer_row(db, player):
     """测试冒险家：挂在 player 上（user_id 唯一约束 + FK 都满足）。"""
     adv = Adventurer(
         user_id=player.id,
         game_uid=uuid.uuid4().hex[:10],
         server="天空岛",
         game_nickname="测试冒险家",
         audit_status="approved",
     )
     db.add(adv)
     await db.flush()
     return adv