r"""运维脚本：重置用户密码（模拟环境的「忘记密码」通道）。

用法（在项目根目录）：
    .\venv\Scripts\python.exe scripts\reset_password.py 18948197962 NewPass123

为什么要有这个脚本而不是手敲 SQL：
生成的 bcrypt 哈希形如 $2b$12$...，把它粘进 PowerShell 双引号会被当成变量展开
（$2b / $12 变成空），粘两遍还会变成 120 字符。走脚本参数，全程不经过 shell 展开。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db import engine  # noqa: E402


async def reset(phone: str, password: str) -> None:
    h = hash_password(password)
    async with engine.begin() as conn:
        # user 在部分数据库里是保留字，统一加反引号
        r = await conn.execute(
            text("UPDATE `user` SET password_hash = :h WHERE phone = :p"),
            {"h": h, "p": phone},
        )
        print(f"phone={phone} 影响行数={r.rowcount}")
        if r.rowcount == 0:
            print("⚠️ 该手机号不存在，未做任何修改")
    await engine.dispose()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("用法: python scripts/reset_password.py <手机号> <新密码>")
    asyncio.run(reset(sys.argv[1], sys.argv[2]))
