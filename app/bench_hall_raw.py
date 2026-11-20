"""大厅读上限：裸 socket 版，用来给 uvicorn worker 数做 A/B。

为什么不用 httpx：单进程 httpx 客户端在 ~250 QPS 就把一个核吃满，
之后再加并发 QPS 反而下降（排队），测到的是客户端而不是服务端。

用法（仓库根目录）：
    python -m app.bench_hall_raw 400 10        # 400 请求 / 10 条连接
    python -m app.bench_hall_raw 800 10,20     # 多档并发对比

A/B 怎么用：
    1. uvicorn app.main:app --port 8000                → 跑一次
    2. 停掉，起 uvicorn app.main:app --port 8000 --workers 4 → 再跑一次
    两次数值之比就是多进程带来的真实增益。
"""
import asyncio
import os
import sys
import time

BASE = os.getenv("BENCH_BASE", "http://127.0.0.1:8000")
HOST, PORT = BASE.split("//", 1)[1].rstrip("/").split(":")
PORT = int(PORT)
REQ_TIMEOUT = 5.0     # 单请求超时：正常应该 1~10ms，5s 没回就是服务端没应答
TOTAL_TIMEOUT = 90.0  # 一档的总闸，防止挂死
REQ = ("GET /commissions/hall?page=1&page_size=20 HTTP/1.1\r\n"
       f"Host: {HOST}:{PORT}\r\nConnection: keep-alive\r\n\r\n").encode()


async def _one(reader) -> None:
    head = await reader.readuntil(b"\r\n\r\n")
    cl = 0
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            cl = int(line.split(b":")[1])
            break
    if cl:
        await reader.readexactly(cl)


async def _worker(n: int, lat: list[float], fails: list[int]) -> None:
    reader, writer = await asyncio.open_connection(HOST, PORT)
    try:
        for _ in range(n):
            t0 = time.perf_counter()
            writer.write(REQ)
            await writer.drain()
            try:
                await asyncio.wait_for(_one(reader), timeout=REQ_TIMEOUT)
            except asyncio.TimeoutError:
                # 服务端接了连接却不回：连接已脏（响应可能在半路），
                # 继续复用只会连环超时，直接放弃这条连接
                fails.append(1)
                return
            lat.append((time.perf_counter() - t0) * 1000)
    finally:
        writer.close()


async def _run(total: int, conns: int) -> None:
    per = max(1, total // conns)
    lat: list[float] = []
    fails: list[int] = []
    t0 = time.perf_counter()
    cpu0 = time.process_time()
    try:
        await asyncio.wait_for(
            asyncio.gather(*[_worker(per, lat, fails) for _ in range(conns)]),
            timeout=TOTAL_TIMEOUT)
    except asyncio.TimeoutError:
        print(f"连接={conns:>3}  整体超过 {TOTAL_TIMEOUT}s 仍未完成，"
              f"已完成 {len(lat)} 个请求", flush=True)
    wall = time.perf_counter() - t0
    cpu = time.process_time() - cpu0
    if not lat:
        print(f"连接={conns:>3}  全部失败（{len(fails)} 条连接无响应）", flush=True)
        return
    lat.sort()
    print(f"连接={conns:>3}  请求={len(lat):>4}  QPS={len(lat) / wall:7.0f}  "
          f"p50={lat[len(lat) // 2]:7.2f}ms  p99={lat[int(len(lat) * .99)]:7.2f}ms  "
          f"客户端CPU={cpu / wall * 100:3.0f}%单核"
          + (f"  超时连接={len(fails)}" if fails else ""), flush=True)


async def main() -> None:
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    concs = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else [10]
    # 预热：先单发一次填上缓存，否则第一轮在测冷查询
    await _run(1, 1)
    for c in concs:
        await _run(total, c)


if __name__ == "__main__":
    asyncio.run(main())
