"""大厅缓存冒烟（5 条）：回填 / 命中 / 失效(transition) / 失效(accept) / 降级。

单事件闭环：所有 await 都在同一个 loop 里——绕开 pytest 每测试换 loop 的
单例连接池陷阱，验证的是真实连接池下的缓存行为。
"""
import asyncio
import json
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redis import asyncio as aioredis

from app.core import cache as cache_mod
from app.core.cache import cache_delete_prefix, get_redis
from app.db import AsyncSessionLocal, engine
from app.models import Adventurer, Category, Commission, ServiceItem, User
from app.services import commission_service, commission_state
from app.services.cache_keys import HALL_CACHE_PREFIX

lines, ok, fail = [], 0, 0


def check(no, name, cond, got=""):
    global ok, fail
    if cond:
        ok += 1
        lines.append(f"  [{no:02d}] PASS  {name}")
    else:
        fail += 1
        lines.append(f"  [{no:02d}] FAIL  {name}   -> {got}")


async def main():
    tag = str(random.randint(100000, 999999))
    phone = "139" + tag
    await cache_delete_prefix(HALL_CACHE_PREFIX)

    # --- 造数据：玩家 + 分类 + 服务项 + 下单 + 支付（进入大厅） ---
    async with AsyncSessionLocal() as db:
        user = User(phone=phone, nickname="缓存冒烟", password_hash="x")
        db.add(user)
        await db.flush()
        adv = Adventurer(
            user_id=user.id, game_uid=f"9{tag}", server="天空岛",
            game_nickname="冒烟冒险家",
        )
        db.add(adv)
        await db.flush()
        cat = Category(name=f"冒烟分类{tag}", sort=99, status=1)
        db.add(cat)
        await db.flush()
        item = ServiceItem(
            category_id=cat.id, name=f"冒烟项{tag}",
            description="", price=Decimal("5.00"), duration_min=10, status=1,
        )
        db.add(item)
        await db.flush()
        order = await commission_service.create_order(
            db, player_id=user.id,
            item_inputs=[{"service_item_id": item.id, "qty": 1}],
            game_uid="100000000", server="天空岛",
        )
        await commission_state.transition(
            db, order.id, "支付成功",
            operator_id=user.id, operator_role="player",
        )
        await db.commit()
        player_id, adv_id, item_id, cat_id, order_id = user.id, adv.id, item.id, cat.id, order.id

    # [01] miss → 查库 → 回填
    async with AsyncSessionLocal() as db:
        total, items = await commission_service.list_hall(db, 1, 10)
    raw = await get_redis().get(f"{HALL_CACHE_PREFIX}:1:10")
    check(1, "miss 后回填缓存（redis 里有 key）", raw is not None,
          "redis 无 key")
    check(2, "大厅里能看到冒烟单", any(i.order_no == order.order_no for i in items),
          f"total={total}")

    # [03] 命中路径：往 key 里塞哨兵，再读应该吐哨兵（证明读的是缓存不是库）
    sentinel = json.dumps({"total": 999, "items": []})
    await get_redis().set(f"{HALL_CACHE_PREFIX}:1:10", sentinel, ex=30)
    async with AsyncSessionLocal() as db:
        total2, items2 = await commission_service.list_hall(db, 1, 10)
    check(3, "命中返回哨兵（读路径走缓存）", total2 == 999, f"total={total2}")

    # [04] 失效(accept)：accept_order 应删前缀 → 再读不能再是哨兵，且单已不在大厅
    async with AsyncSessionLocal() as db:
        await commission_state.accept_order(db, order_id, adventurer_id=adv_id)
        await db.commit()
        total3, items3 = await commission_service.list_hall(db, 1, 10)
    check(4, "accept 失效缓存（哨兵消失，回真数据）", total3 != 999,
          f"total={total3}")
    check(5, "接单后大厅不再显示该单", not any(i.order_no == order.order_no for i in items3))

    # [06] 降级：把连接池换成死端口，list_hall 应照常回库数据而不是抛错
    saved_pool = cache_mod._pool
    cache_mod._pool = aioredis.Redis(
        host="127.0.0.1", port=6390,          # 没人监听的端口
        socket_connect_timeout=0.3, decode_responses=True,
    )
    try:
        async with AsyncSessionLocal() as db:
            total4, items4 = await commission_service.list_hall(db, 1, 10)
        check(6, "Redis 挂了降级直查库", total4 == total3, f"total={total4}")
    except Exception as e:
        check(6, "Redis 挂了降级直查库", False, repr(e))
    finally:
        await cache_mod._pool.aclose()
        cache_mod._pool = saved_pool

    # --- 清理：先子后主 + 缓存前缀 ---
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.execute(text(
            "DELETE FROM commission_log WHERE commission_id=:oid"), {"oid": order_id})
        await conn.execute(text(
            "DELETE FROM commission_item WHERE commission_id=:oid"), {"oid": order_id})
        await conn.execute(text(
            "DELETE FROM commission WHERE id=:oid"), {"oid": order_id})
        await conn.execute(text(
            "DELETE FROM service_item WHERE id=:iid"), {"iid": item_id})
        await conn.execute(text(
            "DELETE FROM category WHERE id=:cid"), {"cid": cat_id})
        await conn.execute(text(
            "DELETE FROM adventurer WHERE id=:aid"), {"aid": adv_id})
        await conn.execute(text(
            "DELETE FROM user WHERE id=:uid"), {"uid": player_id})
    await cache_delete_prefix(HALL_CACHE_PREFIX)

    await get_redis().aclose()
    await engine.dispose()

    print("\n".join(lines))
    print(f"\n结果: {ok} 通过 / {fail} 失败")
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    asyncio.run(main())
