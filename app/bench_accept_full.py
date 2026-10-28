"""全链路并发抢单压测：每轮真实下单 → 支付 → 20 并发抢，不删库不重置。"""
import asyncio
import collections

import httpx

BASE = "http://127.0.0.1:8000"
ROUNDS = 3
N = 20
ITEM_ID = 1 # 库里在架的商品 id

async def new_paid_order(client: httpx.AsyncClient) -> int:
    """下单 + 支付，返回 order_id。"""
    r = await client.post(f"{BASE}/commissions/create_order", json={
        "items": [{"service_item_id": ITEM_ID, "qty": 1}],
        "game_uid": "100000001", "server": "天空岛", "remark": "压测",
    }, headers={"X-Player-Id": "1"})
    r.raise_for_status()
    order_id = r.json()["order_id"]

    r = await client.post(f"{BASE}/commissions/{order_id}/pay",
                          headers={"X-Player-Id": "1"})
    r.raise_for_status()
    return order_id

async def grab(client, order_id, adventurer_id):
    r = await client.post(f"{BASE}/commissions/{order_id}/accept",
                          headers={"X-Adventurer-Id": str(adventurer_id)})
    return r.status_code

async def one_round(client, idx: int) -> dict:
    order_id = await new_paid_order(client)
    codes = await asyncio.gather(*[grab(client, order_id, 200 + i) for i in range(N)])
    dist = collections.Counter(codes)
    print(f"第{idx}论order_id={order_id}{dict(dist)}")
    return {"order_id": order_id, "code": dist}

async def main():
    # TODO: trust_env=False 绕开系统代理，否则 127.0.0.1 可能走代理 502
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        rounds = [await one_round(client, i + 1) for i in range(ROUNDS)]

    bad = [r for r in rounds if r["code"].get(200) != 1 or r["code"].get(409) != N - 1]
    print("FAIL" if bad else f"PASS: {ROUNDS}轮, 每轮1成功{N-1}冲突")
    print("order_ids",[r["order_id"] for r in rounds])

asyncio.run((main()))