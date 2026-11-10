"""支付模块 HTTP 冒烟（9 条）：发起幂等 / 验签 / 金额篡改 / 回调幂等 / 状态机兜底。"""
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 支持从任意 cwd 运行

import httpx
from sqlalchemy import text

from app.db import engine

BASE = "http://127.0.0.1:8000"
PHONE = "139" + str(random.randint(10000000, 99999999))
PWD = "test1234"
SIGN = "mock-callback-secret-change-me"   # 与 config.py 默认值一致
lines, ok, fail = [], 0, 0


def check(no, name, cond, got=""):
    global ok, fail
    if cond:
        ok += 1
        lines.append(f"  [{no:02d}] PASS  {name}")
    else:
        fail += 1
        lines.append(f"  [{no:02d}] FAIL  {name}   -> {got}")


def body(r):
    try:
        return r.json()
    except Exception:
        return {}


def payload(r):
    d = body(r)
    return d.get("detail", d) if isinstance(d, dict) else {}


def code_of(r):
    p = payload(r)
    return p.get("code") if isinstance(p, dict) else None


async def sql(stmt, **kw):
    async with engine.begin() as conn:
        await conn.execute(text(stmt), kw)


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        # 1 注册
        r = await c.post("/auth/register",
                         json={"phone": PHONE, "password": PWD, "nickname": "支付冒烟"})
        tok = body(r).get("access_token")
        check(1, "注册 201 拿 token", r.status_code == 201 and bool(tok), r.text[:100])
        h = {"Authorization": f"Bearer {tok}"}

        # 2 下单（68.00 一件）
        r = await c.post("/commissions/create_order", headers=h,
                         json={"items": [{"service_item_id": 1, "qty": 1}],
                               "game_uid": "900000001", "server": "天空岛"})
        order_id = body(r).get("order_id")
        check(2, "下单 200 拿 order_id",
              r.status_code == 200 and order_id and body(r).get("total_amount") == "68.00",
              f"{r.status_code} {r.text[:120]}")

        # 3 发起支付
        r = await c.post(f"/commissions/{order_id}/pay", headers=h)
        p1 = body(r)
        check(3, "发起支付 200 返回收银台参数",
              r.status_code == 200 and p1.get("out_trade_no", "").startswith("PAY")
              and p1.get("amount") == "68.00",
              f"{r.status_code} {r.text[:120]}")

        # 4 狂点再发起：应复用同一支付单
        r = await c.post(f"/commissions/{order_id}/pay", headers=h)
        check(4, "重复发起返回同一个 out_trade_no",
              r.status_code == 200 and body(r).get("out_trade_no") == p1.get("out_trade_no"),
              f"{r.status_code} {r.text[:120]}")
        no = p1["out_trade_no"]

        # 5 伪造签名回调
        r = await c.post(f"/payments/{no}/callback", headers={"X-Pay-Sign": "wrong-secret"},
                         json={"amount": "68.00"})
        check(5, "伪造签名 401 BAD_SIGN",
              r.status_code == 401 and code_of(r) == "BAD_SIGN",
              f"{r.status_code} {code_of(r)}")

        # 6 金额篡改（签名对，金额错）
        r = await c.post(f"/payments/{no}/callback", headers={"X-Pay-Sign": SIGN},
                         json={"amount": "6.80"})
        check(6, "金额篡改 400 PAYMENT_AMOUNT_MISMATCH",
              r.status_code == 400 and code_of(r) == "PAYMENT_AMOUNT_MISMATCH",
              f"{r.status_code} {code_of(r)}")

        # 7 正确回调：first_time=True，订单推进待接单
        r = await c.post(f"/payments/{no}/callback", headers={"X-Pay-Sign": SIGN},
                         json={"amount": "68.00", "message": "pay-success"})
        d = body(r)
        check(7, "正确回调 200 first_time=True 且订单变待接单",
              r.status_code == 200 and d.get("first_time") is True
              and d.get("order_status") == "待接单"
              and d.get("payment_status") == "success",
              f"{r.status_code} {r.text[:150]}")

        # 8 第三方重试：重复回调幂等
        r = await c.post(f"/payments/{no}/callback", headers={"X-Pay-Sign": SIGN},
                         json={"amount": "68.00"})
        d = body(r)
        check(8, "重复回调 200 first_time=False 订单不重复推进",
              r.status_code == 200 and d.get("first_time") is False
              and d.get("order_status") is None,
              f"{r.status_code} {r.text[:150]}")

        # 9 已支付订单再发起：状态机拦截
        r = await c.post(f"/commissions/{order_id}/pay", headers=h)
        check(9, "支付成功后再发起 409 STATE_ILLEGAL",
              r.status_code == 409 and code_of(r) == "STATE_ILLEGAL",
              f"{r.status_code} {code_of(r)}")

        # 清理冒烟数据（无 FK，顺序随意）
        await sql("DELETE FROM payment WHERE commission_id=:oid", oid=order_id)
        await sql("DELETE FROM commission_item WHERE commission_id=:oid", oid=order_id)
        await sql("DELETE FROM commission_log WHERE commission_id=:oid", oid=order_id)
        await sql("DELETE FROM commission WHERE id=:oid", oid=order_id)
        await sql("DELETE FROM user WHERE phone=:ph", ph=PHONE)

    await engine.dispose()


try:
    asyncio.run(main())
except Exception as e:
    lines.append(f"  脚本异常: {type(e).__name__}: {e}")

print("\n".join(lines))
print(f"\n结果: {ok} passed, {fail} failed")
