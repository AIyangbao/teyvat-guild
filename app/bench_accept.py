import asyncio
import collections
import httpx

BASE = "http://127.0.0.1:8000"
ORDER_ID = 1
N = 20

async def grab(client: httpx.AsyncClient, adventurer_id: int):
    r = await client.post(f"{BASE}/commissions/{ORDER_ID}/accept",
                          headers={"X-Adventurer-Id": str(adventurer_id)})
    return r.status_code, adventurer_id

async def main():
    async with httpx.AsyncClient(timeout=10) as client:
        # gather = 同时发出，不是 for 循环串行
        results = await asyncio.gather(*[grab(client,100+i) for i in range(N)])

    codes = collections.Counter(c for c,_ in results)
    winners = [a for c,a in results if c == 200]
    print(f"状态码分布:{dict(codes)}")
    print(f"抢到的冒险家:{winners}")
    assert codes[200] == 1,f"应该只有一个成功, 实际{codes[200]}"
    assert codes[409] == N - 1, f"应该{N-1}个4-9,实际{codes[409]}"
    print("PASS:并发下只有1人抢到")

asyncio.run(main())