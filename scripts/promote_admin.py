"""把指定手机号提升为管理员 —— 管理端鉴权上线前的必要一步。

用法（仓库根目录、venv 内）：
    python -m scripts.promote_admin 139xxxxxxxx

为什么必须用 -m：直接 `python scripts/promote_admin.py` 会把 sys.path[0]
设成 scripts/，import app 就找不到包了（和昨天 bench 脚本同一个坑）。

设计要点：
- 只按 phone 精确定位一行，rowcount != 1 就抛异常让事务回滚，绝不批量改；
- engine.begin() 自带事务：正常退出自动提交，抛异常自动回滚；
- 幂等：已经是 admin 直接提示退出，重复跑不会出事；
- 改的是库里的 user.role。token payload 里的 role 只是展示用的快照，
  get_current_user 每次都会重新查库，所以旧 token 无需重签即刻生效。
"""
import asyncio
import sys

from sqlalchemy import text

from app.db import engine


async def promote(phone: str) -> None:
    async with engine.begin() as conn:
        row = (await conn.execute(
            text("SELECT id, phone, role, status FROM user WHERE phone = :p"),
            {"p": phone},
        )).mappings().one_or_none()
        if row is None:
            print(f"没找到手机号 {phone}，先去注册一个账号")
            return
        print(f"改前: id={row['id']} phone={row['phone']} "
              f"role={row['role']} status={row['status']}")
        if row["status"] != 1:
            print("该账号已禁用(status != 1)，拒绝提升")
            return
        if row["role"] == "admin":
            print("已经是 admin，无需改动")
            return

        res = await conn.execute(
            text("UPDATE user SET role = 'admin' "
                 "WHERE phone = :p AND role <> 'admin'"),
            {"p": phone},
        )
        if res.rowcount != 1:
            raise RuntimeError(f"预期影响 1 行，实际 {res.rowcount}；事务回滚")
        new_role = (await conn.execute(
            text("SELECT role FROM user WHERE phone = :p"), {"p": phone},
        )).scalar_one()
        print(f"改后: role={new_role}  (已提交)")


async def _run(phone: str) -> None:
    try:
        await promote(phone)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit("用法: python -m scripts.promote_admin <手机号>")
    asyncio.run(_run(sys.argv[1].strip()))
