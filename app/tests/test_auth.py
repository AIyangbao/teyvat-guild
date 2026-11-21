"""注册接口测试: 把[选角色 + 建档案]链路顶死. 204 -> 209."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.security import decode_access_token
from app.db import get_db
from app.main import app
from app.models import Adventurer, User

def _payload(**kw):
    p = {"phone": "139" + str(uuid.uuid4().int)[:8], "password": "12345678",
         "nickname": "测试旅行者", "role": "player"}
    p.update(kw)
    return p

def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

@pytest.fixture
def override_db(db):
    """路由 get_db → 测试 session，故意不 commit。

    真 get_db 在 yield 后会 commit；一提交，db fixture 末尾的 rollback
    就撤不掉了，测试数据会永久留在 dev 库。
    """
    async def _get_db():
        try:
            yield db
        except Exception:
            await db.rollback()
            raise
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.clear()

async def test_register_player_ok_and_duplicate_phone_409(override_db, db):
    p = _payload()
    async with _client() as c:
        r = await c.post("/auth/register", json=p)
    assert r.status_code == 201
    data = r.json()
    assert data["role"] == "player"
    assert decode_access_token(data["access_token"])["role"] == "player"
    u = (await db.execute(select(User).where(User.phone == p["phone"]))).scalar_one()
    assert u.role == "player"
    assert (await db.execute(select(Adventurer).where(Adventurer.user_id == u.id))
                ).scalar_one_or_none() is None # 玩家不该有冒险家档案

    async with _client() as c: # 同手机号：走「先查重」分支
        again = await c.post("/auth/register", json=p)
    assert again.status_code == 409
    assert again.json()["detail"]["code"] == "PHONE_DUPLICATE"

async def test_register_adventurer_ok(override_db, db):
    uid = uuid.uuid4().hex[:10]
    p = _payload(role="adventurer", game_uid=uid, server="cn_gf01", game_nickname="空")
    async with _client() as c:
        r = await c.post("/auth/register", json=p)
    assert r.status_code == 201
    data = r.json()
    assert data["role"] == "adventurer"
    assert decode_access_token(data["access_token"])["role"] == "adventurer"
    u = (await db.execute(select(User).where(User.phone == p["phone"]))).scalar_one()
    assert u.role == "adventurer"
    adv = (await db.execute(select(Adventurer).where(Adventurer.user_id == u.id))
           ).scalar_one()
    assert (adv.game_uid, adv.server, adv.game_nickname) == (uid, "cn_gf01", "空")

async def test_register_adventurer_requires_profile():
     """纯内存：Pydantic 在进路由前就拒了，dev 栈没起也能跑。"""
     for missing in ("game_uid", "server", "game_nickname"):
         p = _payload(role="adventurer", game_uid="100000001",
                      server="cn_gf01", game_nickname="空")
         p.pop(missing)
         async with _client() as c:
             r = await c.post("/auth/register", json=p)
         assert r.status_code == 422, f"缺{missing} 竟被放行"

async def test_register_rejects_admin_role():
    async with _client() as c:
        r = await c.post("/auth/register", json=_payload(role="admin"))
    assert r.status_code == 422 # Literal 白名单：公开注册不能自造管理员

async def test_register_duplicate_game_uid_409(override_db, db, adventurer_row):
    p = _payload(role="adventurer", game_uid=adventurer_row.game_uid,
                 server=adventurer_row.server, game_nickname="另一个旅行者")
    async with _client() as c:
        r = await c.post("/auth/register", json=p)
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "GAME_UID_DUPLICATE"