"""JWT 与鉴权链路的 HTTP 冒烟脚本（临时文件，跑完即删）。"""
import asyncio
import random

import httpx
from sqlalchemy import text

from app.db import engine

BASE = "http://127.0.0.1:8000"
PHONE = "139" + str(random.randint(10000000, 99999999))
OTHER = "139" + str(random.randint(10000000, 99999999))
PWD = "test1234"
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


def msg_of(r):
    p = payload(r)
    return p.get("message") if isinstance(p, dict) else None


async def sql(stmt, **kw):
    async with engine.begin() as conn:
        await conn.execute(text(stmt), kw)


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=15) as c:
        # 1 注册
        r = await c.post("/auth/register",
                         json={"phone": PHONE, "password": PWD, "nickname": "冒烟玩家"})
        tok = body(r).get("access_token")
        uid = body(r).get("user_id")
        check(1, "注册返回 201 且直接发 token", r.status_code == 201 and bool(tok),
              f"{r.status_code} {r.text[:100]}")
        if not tok:
            lines.append("  注册失败，后续跳过")
            return

        # 2 重复注册
        r = await c.post("/auth/register",
                         json={"phone": PHONE, "password": PWD, "nickname": "冒烟玩家"})
        check(2, "重复手机号 409 PHONE_DUPLICATE",
              r.status_code == 409 and code_of(r) == "PHONE_DUPLICATE",
              f"{r.status_code} {code_of(r)}")

        # 3 正常登录
        r = await c.post("/auth/login", json={"phone": PHONE, "password": PWD})
        check(3, "登录成功 200 且 role=player",
              r.status_code == 200 and body(r).get("role") == "player",
              f"{r.status_code} {body(r).get('role')}")

        # 4 密码错误
        r = await c.post("/auth/login", json={"phone": PHONE, "password": "wrongpass1"})
        check(4, "密码错误 401 BAD_CREDENTIALS",
              r.status_code == 401 and code_of(r) == "BAD_CREDENTIALS",
              f"{r.status_code} {code_of(r)}")
        bad_msg = msg_of(r)

        # 5 手机号不存在（文案必须与 4 一致，防枚举）
        r = await c.post("/auth/login", json={"phone": OTHER, "password": "wrongpass1"})
        check(5, "未注册手机号 401 且文案与密码错误一致",
              r.status_code == 401 and msg_of(r) == bad_msg,
              f"{r.status_code} {msg_of(r)!r} vs {bad_msg!r}")

        # 6 不带 token
        r = await c.get("/commissions/mine")
        check(6, "无 token 401 + WWW-Authenticate",
              r.status_code == 401 and r.headers.get("www-authenticate") == "Bearer",
              f"{r.status_code} {r.headers.get('www-authenticate')}")

        # 7 篡改 token（改最后一位）
        fake = tok[:-1] + ("a" if tok[-1] != "a" else "b")
        r = await c.get("/commissions/mine", headers={"Authorization": f"Bearer {fake}"})
        check(7, "篡改 token 401", r.status_code == 401, f"{r.status_code}")

        # 8 正常带 token
        h = {"Authorization": f"Bearer {tok}"}
        r = await c.get("/commissions/mine", headers=h)
        check(8, "带合法 token 访问 /mine 200",
              r.status_code == 200 and "total" in body(r),
              f"{r.status_code} {r.text[:100]}")

        # 9 玩家身份越权：接口要求冒险者
        r = await c.post("/commissions/999999/accept", headers=h)
        check(9, "player 调 accept 403「需要冒险者身份」",
              r.status_code == 403 and "冒险者" in (msg_of(r) or ""),
              f"{r.status_code} {msg_of(r)}")

        # 10 造冒险者档案后，用同一枚旧 token 重试 -> 角色从库里读，无需重签
        await sql("UPDATE user SET role='adventurer' WHERE id=:uid", uid=uid)
        await sql("""INSERT INTO adventurer
                     (user_id, game_uid, server, game_nickname, rating,
                      finished_count, abandoned_count, max_concurrent,
                      audit_status, online_status, created_at)
                     VALUES (:uid, :gid, '天空岛', '冒烟冒险者', 5.00,
                             0, 0, 3, 'approved', 'online', NOW())""",
                  uid=uid, gid="9" + str(random.randint(100000000, 999999999)))
        r = await c.post("/commissions/999999/accept", headers=h)
        check(10, "改库升角色后同一 token 放行（404 订单不存在）",
              r.status_code == 404, f"{r.status_code} {msg_of(r)}")

        # 11 冒险者反向越权：/mine 要求玩家
        r = await c.get("/commissions/mine", headers=h)
        check(11, "adventurer 调 /mine 403「需要玩家身份」",
              r.status_code == 403 and "玩家" in (msg_of(r) or ""),
              f"{r.status_code} {msg_of(r)}")

        # 12 封号后 token 仍有效，但必须查库拦住
        await sql("UPDATE user SET status=0 WHERE id=:uid", uid=uid)
        r = await c.get("/commissions/mine", headers=h)
        check(12, "封号后旧 token 401「账号不存在或已禁用」",
              r.status_code == 401 and "禁用" in (msg_of(r) or ""),
              f"{r.status_code} {msg_of(r)}")

        # 清理冒烟数据
        await sql("DELETE FROM adventurer WHERE user_id=:uid", uid=uid)
        await sql("DELETE FROM user WHERE id=:uid", uid=uid)

    await engine.dispose()


try:
    asyncio.run(main())
except Exception as e:
    lines.append(f"  脚本异常: {type(e).__name__}: {e}")

print("\n".join(lines))
print(f"\n结果: {ok} passed, {fail} failed   (手机号 {PHONE})")
