"""用户资料 + 头像上传：service 层 + 路由层闭环。

两个约定：
1. 路由层同时 override get_db 和 get_current_user，让接口拿到「测试 session + 该 session 里的 User」，
   写操作落在测试事务内，db fixture 的 rollback 能收干净。
2. 头像目录 monkeypatch 到 tmp_path，测试绝不写脏 app/data/avatars。
"""
import io

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps import get_current_user
from app.core.exceptions import BizError
from app.db import get_db
from app.main import app
from app.schemas.user import AdventurerUpdate
from app.services import storage_service, user_service

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
JPG = b"\xff\xd8\xff" + b"\x00" * 20
WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 8


class _Upload:
    """UploadFile 的最小替身：storage 只用到 async read(n)。"""

    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    async def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)


def _as_adventurer(db, player):
    """adventurer_row 只建档案行、不改 user.role；这里补上角色。"""
    player.role = "adventurer"
    db.add(player)


# ---------- storage：魔数 / 大小 / 落盘路径 ----------

@pytest.mark.parametrize("raw,ext", [(PNG, "png"), (JPG, "jpg"), (WEBP, "webp")])
async def test_save_avatar_detects_ext_by_magic(monkeypatch, tmp_path, raw, ext):
    monkeypatch.setattr(storage_service, "AVATAR_DIR", tmp_path)
    url = await storage_service.save_avatar(7, _Upload(raw))
    assert url == f"/api/avatars/7.{ext}"
    assert (tmp_path / f"7.{ext}").read_bytes() == raw


async def test_save_avatar_rejects_oversize(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "AVATAR_DIR", tmp_path)
    with pytest.raises(BizError) as e:
        await storage_service.save_avatar(7, _Upload(b"x" * (storage_service.MAX_BYTES + 1)))
    assert e.value.code == "FILE_TOO_LARGE"
    assert list(tmp_path.iterdir()) == []          # 失败不留文件


async def test_save_avatar_rejects_garbage(monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "AVATAR_DIR", tmp_path)
    with pytest.raises(BizError) as e:
        await storage_service.save_avatar(7, _Upload(b"not an image"))
    assert e.value.code == "FILE_TYPE_INVALID"


# ---------- service：读回 / 写入 / 越权 ----------

async def test_player_profile_has_no_adventurer_fields(db, player):
    p = await user_service.get_profile(db, player)
    assert p.id == player.id and p.role == "player"
    assert (p.game_nickname, p.server, p.skill_tags, p.online_status) == (None,) * 4


async def test_adventurer_profile_exposes_own_fields(db, player, adventurer_row):
    _as_adventurer(db, player)
    await db.flush()
    p = await user_service.get_profile(db, player)
    assert p.game_nickname == "测试冒险家"
    assert p.server == "天空岛"
    assert p.online_status == "offline"


async def test_update_nickname_reads_back(db, player):
    await user_service.update_nickname(db, player, "新昵称")
    assert (await user_service.get_profile(db, player)).nickname == "新昵称"


async def test_set_avatar_reads_back(db, player):
    await user_service.set_avatar(db, player, "/api/avatars/1.png")
    assert (await user_service.get_profile(db, player)).avatar == "/api/avatars/1.png"


async def test_player_cannot_update_adventurer_profile(db, player, adventurer_row):
    data = AdventurerUpdate(game_nickname="改不了", skill_tags=["风"], online_status="online")
    with pytest.raises(BizError) as e:
        await user_service.update_my_adventurer(db, player, data)
    assert e.value.code == "ROLE_FORBIDDEN"


async def test_adventurer_update_writes_fields(db, player, adventurer_row):
    _as_adventurer(db, player)
    await db.flush()
    data = AdventurerUpdate(game_nickname="旅行者", skill_tags=["风", "岩"], online_status="online")
    p = await user_service.update_my_adventurer(db, player, data)
    assert p.game_nickname == "旅行者"
    assert p.skill_tags == ["风", "岩"]
    assert p.online_status == "online"


# ---------- 路由层：真走一遍 HTTP ----------

@pytest.fixture
async def client(db, player):
    """接口拿到测试 session 和测试用户；退出清 override，防止污染后续测试。"""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: player
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


async def test_me_without_token_401():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/users/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "NOT_AUTHENTICATED"


async def test_get_me_route(client, player):
    r = await client.get("/users/me")
    assert r.status_code == 200
    assert r.json()["id"] == player.id
    assert set(r.json()) >= {"nickname", "avatar", "role", "phone", "game_nickname"}


async def test_put_me_route_updates_nickname(client, player):
    r = await client.put("/users/me", json={"nickname": "接口改名"})
    assert r.status_code == 200
    assert r.json()["nickname"] == "接口改名"
    assert player.nickname == "接口改名"          # 证明写的是同一个 ORM 对象


async def test_upload_avatar_route(client, player, monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "AVATAR_DIR", tmp_path)
    r = await client.post("/users/me/avatar",
                          files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200
    assert r.json()["avatar"] == f"/api/avatars/{player.id}.png"
    assert (tmp_path / f"{player.id}.png").exists()


async def test_upload_avatar_route_rejects_bad_bytes(client, monkeypatch, tmp_path):
    monkeypatch.setattr(storage_service, "AVATAR_DIR", tmp_path)
    r = await client.post("/users/me/avatar",
                          files={"file": ("a.txt", b"hello", "image/png")})
    assert r.status_code == 415
    assert r.json()["detail"]["code"] == "FILE_TYPE_INVALID"


async def test_player_put_adventurer_me_403(client, player, adventurer_row):
    r = await client.put("/users/adventurers/me", json={
        "game_nickname": "越权", "skill_tags": [], "online_status": "online"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "ROLE_FORBIDDEN"


async def test_adventurer_put_adventurer_me_route(client, db, player, adventurer_row):
    _as_adventurer(db, player)
    await db.flush()
    r = await client.put("/users/adventurers/me", json={
        "game_nickname": "接口改", "skill_tags": ["雷"], "online_status": "offline"})
    assert r.status_code == 200
    assert r.json()["game_nickname"] == "接口改"
    assert r.json()["skill_tags"] == ["雷"]
