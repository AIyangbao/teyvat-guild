"""管理端鉴权测试：纯内存，不碰数据库。

401/403 在依赖链上就抛了，根本走不到 service 的 SQL；
role=admin 那条直接单测依赖函数本身。所以 dev 栈没起也能跑。

注意 FastAPI 0.150：include_router 不再把路由平铺进 app.routes，
而是包成 _IncludedRouter，必须递归展开才能自省。
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.deps import get_current_user, require_admin
from app.main import app
from app.models import User
from app.routers import admin
def _leaf_routes(routes, prefix=""):
    """产出 (完整路径, 方法集合, 依赖列表)。"""
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None: # _IncludedRouter 包装层
            ctx = getattr(r, "include_context", None)
            yield from _leaf_routes(inner.routes,
                                    prefix + (getattr(ctx, "prefix", "")or ""))
        elif hasattr(r, "dependant"): # 真正的 APIRoute
            yield prefix + r.path, r.methods, r.dependant.dependencies

def _admin_writes():
    for path, methods, deps in _leaf_routes(app.routes):
        if path.startswith("/admin") and (methods - {"GET", "HEAD"}):
            yield path, methods, deps

def test_every_admin_write_is_guarded():
    """以后谁新增写接口忘了挂依赖，这条立刻红 —— 这才是本文件的核心价值。"""
    writes = list(_admin_writes())
    assert writes, "没发现任何 /admin 写路由，自省逻辑可能失效了"
    missed = [f"{sorted(m)}{p}" for p, m, deps in writes
              if not any(d.call is require_admin for d in deps)]
    assert not missed, f"以下写接口没挂 require_admin:{missed}"

def test_admin_reads_stay_public():
    """前台游客靠这两个 GET 看商品，被误锁就白屏。"""
    reads = [(p, deps) for p, methods, deps in _leaf_routes(app.routes)
             if p.startswith("/admin") and methods <= {"GET", "HEAD"}]
    assert len(reads) == 2, f"预期2个公开读接口, 实际{len(reads)}"
    assert all(not any(d.call is require_admin for d in deps)
               for _, deps in reads)

def test_public_admin_router_has_no_writes():
    """把「管理写接口必须挂 _write」这个约定变成断言。

    只查 admin.router 的直属路由（不递归展开 _write 包装层）：
    公开 router 上只允许 GET。谁把新写接口挂到这里，这条立刻红，
    不管它路径叫什么、有没有 /admin 前缀。
    """
    direct = [r for r in admin.router.routes if hasattr(r, "dependant")]
    assert direct, "公开 router 上一个直属路由都没有，结构可能被改坏了"
    for r in direct:
        assert r.methods <= {"GET", "HEAD"}, \
        f"{r.path} 是写接口却挂在公开router上(应挂到 _write)"

@pytest.fixture
def clear_overrides():
    yield
    app.dependency_overrides.clear() #  不清会污染后面所有测试

async def test_write_without_token_401():
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r = await c.request("DELETE", "/admin/categories/1")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "NOT_AUTHENTICATED"

async def test_player_write_403(clear_overrides):
    app.dependency_overrides[get_current_user] = (
        lambda: User(id=1, role="player", status=1))
    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r = await c.request("DELETE", "/admin/categories/1")
    assert r.status_code == 403

async def test_require_admin_passes_admin_user():
    u = User(id=2, role="admin", status=1)
    assert await require_admin(user=u) is u