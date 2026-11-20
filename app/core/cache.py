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
from redis.backoff import NoBackoff
from redis.retry import Retry
from app.config import settings

def _new_client() -> aioredis.Redis:
  """唯一的客户端构造入口——所有参数只在这里写一次，
  避免某条分支漏参数导致"配置漂移"（今天这个 26s 坑就是漂移的产物）"""
  return aioredis.Redis(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=settings.redis_password or None,
    decode_responses=True,
    # 降级必须"快失败"：0.5s 连不上就放弃，业务退回直查库
    socket_connect_timeout=0.5,
    socket_timeout=0.5,
    # redis-py 8 默认带指数退避重试，一次连不上会拖成 10~26s，必须显式关掉
    retry=Retry(NoBackoff(), 0),
    retry_on_error=[],
   )

_pool = _new_client()

def get_redis() -> aioredis.Redis:
    """惰性单例：首次调用才建连接池。"""
    global _pool
    if _pool is None:
        _pool = _new_client()
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