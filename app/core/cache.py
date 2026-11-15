"""Redis 连接与语义化缓存函数。

三条设计红线（全部来自 my_blog 验证过的范式）：
1. get_redis() 动态取单例——别写 from app.core.cache import redis_client，
   模块级绑死旧对象，测试想替换都没抓手
2. 读函数故障返回 None（当缓存 miss），写函数静默失败——
   Redis 挂了业务照跑，只是退回直查库（降级路径）
3. decode_responses=True——拿到 str 而不是 bytes，省掉满代码库 decode
"""
import json
from redis import asyncio as aioredis

from app.config import settings

_pool: aioredis.Redis | None = None

def get_redis() -> aioredis.Redis:
    """惰性单例：首次调用才建连接池。"""
    global _pool
    if _pool is None:
        _pool = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password or None, # 空串转 None，否则会拿 "" 当密码
            decode_responses=True,
        )
    return _pool

async def cache_get_json(key: str):
    """命中返回反序列化对象，miss 或故障返回 None。"""
    try:
        raw = await get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None

async def cache_set_json(key: str, value, ttl: int) -> None:
    """写缓存，带 TTL。故障静默——缓存只是加速器，不配当故障源。"""
    try:
        await get_redis().set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
    except Exception:
        pass

async def cache_delete_prefix(prefix: str) -> None:
    """按前缀失效。用 SCAN 游标扫，绝不用 KEYS——
    KEYS 单线程阻塞，共享实例里一条 KEYS * 能让全场排队。"""
    try:
        r= get_redis()
        keys = [k async for k in r.scan_iter(match=f"{prefix}*", count=100)]
        if keys:
            await r.delete(*keys)
    except Exception:
        pass