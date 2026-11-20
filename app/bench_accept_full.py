"""抢单压测 S1~S4：真实 HTTP + 真实 JWT + 自造身份，不依赖种子数据。

用法（仓库根目录，uvicorn 已在 127.0.0.1:8000 跑着）：
    python -m app.bench_accept_full

为什么必须加 -m：脚本要 `from app.db import ...` 连库造身份。
直接 `python app/bench_accept_full.py` 会把 sys.path[0] 设成 app/，
`import app` 就找不到了（ModuleNotFoundError: No module named 'app'）。

测什么（方法论照搬 my_blog 的 S1~S4）：
    S1 串行基线    单请求耗时，后面所有数字的分母
    S2 同单争用    N 并发抢一单：断言 1 成功 + N-1 冲突，且库里只有 1 个冒险家
    S3 无争用吞吐  多单并行抢，测 QPS（这才是「系统扛多少」的答案）
    S4 大厅读吞吐  缓存热态下的列表 QPS + 冷启动对比

注意：会往 dev 库写压测用户和订单，跑完想清就换库或手删——这是故意的，
「不删库不重置」才能测出真实行为。
"""
import asyncio
import os
import time
import uuid
from collections import Counter

import httpx

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.db import AsyncSessionLocal, engine
from app.models import Adventurer, User

BASE = os.getenv("BENCH_BASE", "http://127.0.0.1:8000")
N_CONTEND = 20        # S2 同单并发数
ROUNDS = 5            # S2 轮数
S1_SAMPLES = 10
S3_ORDERS = 30
S4_REQUESTS = 300
S4_CONCURRENCY = 20


def _pct(xs: list[float], p: float) -> float:
    """最朴素的百分位：排序后取第 k 个。样本少时够用，别指望它严谨。"""
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = min(len(s) - 1, max(0, round(p / 100 * (len(s) - 1))))
    return s[k]


async def _mk_identities(n_adv: int) -> tuple[str, list[tuple[str, int]]]:
    """造 1 个玩家 + n 个冒险家，直接签 token 不走登录（省一轮 IO）。

    为什么要碰数据库：注册接口只造 player，没有开通冒险家的入口，
    而抢单必须 role=adventurer + adventurer 档案行。
    """
    pw = hash_password("bench-pass-123")
    async with AsyncSessionLocal() as db:
        player = User(phone="170" + uuid.uuid4().hex[:8], nickname="压测玩家",
                      password_hash=pw, role="player")
        db.add(player)
        await db.flush()
        player_token = create_access_token(player.id, "player")

        advs: list[tuple[str, int]] = []
        for i in range(n_adv):
            u = User(phone="171" + uuid.uuid4().hex[:8],
                     nickname=f"压测冒险家{i}", password_hash=pw, role="adventurer")
            db.add(u)
            await db.flush()
            a = Adventurer(user_id=u.id, game_uid=uuid.uuid4().hex[:10],
                           server="天空岛", game_nickname=f"压测冒险家{i}")
            db.add(a)
            await db.flush()
            advs.append((create_access_token(u.id, "adventurer"), a.id))
        await db.commit()
    return player_token, advs


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _pick_item(client: httpx.AsyncClient) -> int:
    r = await client.get(f"{BASE}/admin/items", params={"status": 1})
    r.raise_for_status()
    items = r.json()
    if not items:
        raise SystemExit("库里没有在架服务项，先用 /admin/items 造一条")
    return items[0]["id"]


async def _paid_order(client: httpx.AsyncClient, ptoken: str, item_id: int) -> int:
    r = await client.post(
        f"{BASE}/commissions/create_order",
        json={"items": [{"service_item_id": item_id, "qty": 1}],
              "game_uid": "100000001", "server": "天空岛", "remark": "压测"},
        headers=_auth(ptoken))
    r.raise_for_status()
    oid = r.json()["order_id"]

    r = await client.post(f"{BASE}/commissions/{oid}/pay", headers=_auth(ptoken))
    r.raise_for_status()
    pay = r.json()

    # 关键：/pay 只是建支付单，订单状态由「支付回调」推进到待接单。
    # 少了这一步，抢单会因 status 仍是「待支付」而返回冲突。
    r = await client.post(
        f"{BASE}/payments/{pay['out_trade_no']}/callback",
        json={"amount": pay["amount"], "message": "bench"},
        headers={"X-Pay-Sign": settings.pay_callback_secret})
    r.raise_for_status()
    if r.json()["order_status"] != "待接单":
        raise SystemExit(f"支付回调后订单状态异常：{r.text}")
    return oid


async def _accept(client: httpx.AsyncClient, oid: int,
                  adv_token: str) -> tuple[int, float, str]:
    t0 = time.perf_counter()
    r = await client.post(f"{BASE}/commissions/{oid}/accept",
                          headers=_auth(adv_token))
    ms = (time.perf_counter() - t0) * 1000
    snippet = "" if r.status_code < 400 else r.text[:160]
    return r.status_code, ms, snippet


async def s1_baseline(client, ptoken, advs, item_id) -> dict:
    lat = []
    for _ in range(S1_SAMPLES):
        oid = await _paid_order(client, ptoken, item_id)
        code, ms, snippet = await _accept(client, oid, advs[0][0])
        if code != 200:
            raise SystemExit(f"S1 串行抢单失败，状态码 {code}：{snippet}")
        lat.append(ms)
    return {"n": len(lat), "p50": _pct(lat, 50), "p95": _pct(lat, 95),
            "p99": _pct(lat, 99)}


async def s2_contention(client, ptoken, advs, item_id) -> dict:
    bad = []
    by_code: dict[int, list[float]] = {}
    for i in range(ROUNDS):
        oid = await _paid_order(client, ptoken, item_id)
        res = await asyncio.gather(
            *[_accept(client, oid, t) for t, _ in advs[:N_CONTEND]])
        codes = Counter(c for c, _, _ in res)
        for c, ms, _ in res:
            by_code.setdefault(c, []).append(ms)

        detail = (await client.get(f"{BASE}/commissions/{oid}")).json()
        good = (codes.get(200, 0) == 1
                and codes.get(409, 0) == N_CONTEND - 1
                and detail["status"] == "进行中"
                and detail["adventurer_id"] is not None)
        if not good:
            bad.append((i + 1, dict(codes), detail["status"]))
        print(f"  S2 第{i + 1}轮 order={oid} 码分布={dict(codes)} "
              f"状态={detail['status']} 冒险家={detail['adventurer_id']}")
    return {"ok": not bad, "bad": bad,
            "p50_ok": _pct(by_code.get(200, []), 50),
            "p50_conflict": _pct(by_code.get(409, []), 50),
            "p99_conflict": _pct(by_code.get(409, []), 99)}


async def s3_throughput(client, ptoken, advs, item_id) -> dict:
    oids = [await _paid_order(client, ptoken, item_id) for _ in range(S3_ORDERS)]
    t0 = time.perf_counter()
    res = await asyncio.gather(
        *[_accept(client, oid, advs[i % len(advs)][0]) for i, oid in enumerate(oids)])
    elapsed = time.perf_counter() - t0
    lat = [ms for _, ms, _ in res]
    return {"orders": S3_ORDERS, "elapsed": elapsed,
            "qps": S3_ORDERS / elapsed,
            "codes": dict(Counter(c for c, _, _ in res)),
            "p50": _pct(lat, 50), "p99": _pct(lat, 99)}


async def s4_hall(client, ptoken: str, item_id: int) -> dict:
    # 先挂 20 单在架上：大厅为空时，冷查询的回表成本几乎为零，
    # 测出来的"缓存加速比"没有说服力（真实场景大厅总是有货的）
    for _ in range(20):
        await _paid_order(client, ptoken, item_id)

    async def one() -> tuple[bool, float]:
        t0 = time.perf_counter()
        r = await client.get(f"{BASE}/commissions/hall",
                             params={"page": 1, "page_size": 20})
        return r.status_code == 200, (time.perf_counter() - t0) * 1000

    cold_ms = (await one())[1]          # 冷启动：缓存 miss，要回表拼数据
    t0 = time.perf_counter()
    results = []
    for _ in range(S4_REQUESTS // S4_CONCURRENCY):
        results += await asyncio.gather(*[one() for _ in range(S4_CONCURRENCY)])
    elapsed = time.perf_counter() - t0
    lat = [ms for _, ms in results]

    # 关键：cold 是"单发"，并发那组是"20 路"，两者不可比——并发数字里混着排队时间。
    # 所以热态结束后再单发几次，拿同样"单发"条件下的热延迟，才能和 cold 对比出缓存收益
    hot_single = [(await one())[1] for _ in range(5)]

    return {"requests": len(results), "qps": len(results) / elapsed,
            "cold_ms": cold_ms, "hot_single_p50": _pct(hot_single, 50),
            "hot_p50": _pct(lat, 50), "hot_p99": _pct(lat, 99),
            "ok": sum(1 for ok, _ in results if ok)}


async def s4b_raw_qps(conns: int = 10, per_conn: int = 40) -> dict:
    """裸 socket 测大厅读上限——绕开压测客户端自身的开销。

    为什么需要它：httpx 客户端单进程在 ~250 QPS 就把一个核吃满（CPU 100%），
    再加并发 QPS 反而下降。那不是服务端饱和，是「尺子不够长」。
    这里预构造字节流 + keep-alive，客户端每请求开销降到微秒级。
    """
    host, port = BASE.split("//", 1)[1].rstrip("/").split(":")
    req = (f"GET /commissions/hall?page=1&page_size=20 HTTP/1.1\r\n"
           f"Host: {host}:{port}\r\nConnection: keep-alive\r\n\r\n").encode()

    async def worker(n, lat):
        r, w = await asyncio.open_connection(host, int(port))
        try:
            for _ in range(n):
                t0 = time.perf_counter()
                w.write(req)
                await w.drain()
                head = await r.readuntil(b"\r\n\r\n")
                cl = 0
                for line in head.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        cl = int(line.split(b":")[1])
                        break
                if cl:
                    await r.readexactly(cl)
                lat.append((time.perf_counter() - t0) * 1000)
        finally:
            w.close()

    lat: list[float] = []
    t0 = time.perf_counter()
    await asyncio.gather(*[worker(per_conn, lat) for _ in range(conns)])
    elapsed = time.perf_counter() - t0
    return {"conns": conns, "requests": len(lat), "qps": len(lat) / elapsed,
            "p50": _pct(lat, 50), "p99": _pct(lat, 99)}


async def main() -> None:
    async with httpx.AsyncClient(
            timeout=30, trust_env=False,
            limits=httpx.Limits(max_connections=64,
                                max_keepalive_connections=64)) as client:
        try:
            await client.get(f"{BASE}/health")
        except httpx.HTTPError:
            raise SystemExit(f"连不上 {BASE}，先起服务：uvicorn app.main:app --port 8000")

        print("[0] 造身份（1 玩家 + %d 冒险家）..." % N_CONTEND)
        ptoken, advs = await _mk_identities(N_CONTEND)
        item_id = await _pick_item(client)
        print(f"    服务项 id={item_id}")

        print("\n[S1] 串行基线（%d 次单请求）" % S1_SAMPLES)
        s1 = await s1_baseline(client, ptoken, advs, item_id)
        print(f"    p50={s1['p50']:.1f}ms p95={s1['p95']:.1f}ms p99={s1['p99']:.1f}ms")

        print("\n[S2] 同单争用（%d 轮 × %d 并发）" % (ROUNDS, N_CONTEND))
        s2 = await s2_contention(client, ptoken, advs, item_id)
        print(f"    成功 p50={s2['p50_ok']:.1f}ms | "
              f"冲突 p50={s2['p50_conflict']:.1f}ms p99={s2['p99_conflict']:.1f}ms")

        print("\n[S3] 无争用吞吐（%d 单并行抢）" % S3_ORDERS)
        s3 = await s3_throughput(client, ptoken, advs, item_id)
        print(f"    QPS={s3['qps']:.0f} 总耗时={s3['elapsed'] * 1000:.0f}ms "
              f"码分布={s3['codes']} p50={s3['p50']:.1f}ms p99={s3['p99']:.1f}ms")

        print("\n[S4] 大厅读吞吐（%d 请求 / %d 并发）" % (S4_REQUESTS, S4_CONCURRENCY))
        s4 = await s4_hall(client, ptoken, item_id)
        print(f"    单发：冷={s4['cold_ms']:.1f}ms 热={s4['hot_single_p50']:.1f}ms "
              f"（加速 {s4['cold_ms'] / max(s4['hot_single_p50'], 0.01):.1f}x，缓存收益看这行）")
        print(f"    并发：QPS={s4['qps']:.0f} p50={s4['hot_p50']:.1f}ms "
              f"p99={s4['hot_p99']:.1f}ms 成功={s4['ok']}/{s4['requests']}")
        print("    ↑ 这一行是「httpx 客户端」的成绩，超过 ~250 QPS 后测的就是客户端 CPU 了")

        raw = await s4b_raw_qps()
        print(f"    [S4b] 裸 socket 上限：连接={raw['conns']} QPS={raw['qps']:.0f} "
              f"p50={raw['p50']:.2f}ms p99={raw['p99']:.2f}ms "
              f"（服务端真实读能力，{raw['requests']} 请求）")

    print("\n=== 判定 ===")
    ok = s2["ok"] and s3["codes"].get(200, 0) == S3_ORDERS and s4["ok"] == S4_REQUESTS
    if not s2["ok"]:
        print("FAIL S2 争用结果不符合「1 成功 + N-1 冲突」：", s2["bad"])
    if s3["codes"].get(200, 0) != S3_ORDERS:
        print("FAIL S3 有订单没抢成功：", s3["codes"])
    if s4["ok"] != S4_REQUESTS:
        print("FAIL S4 大厅有请求失败：", s4["ok"], "/", s4["requests"])
    print("PASS" if ok else "FAIL")


async def _run() -> None:
    """dispose 放 finally：中途 SystemExit 也要关连接池，
    否则事件循环关闭时 aiomysql 的 __del__ 会刷 "Event loop is closed"。"""
    try:
        await main()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
