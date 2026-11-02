"""超时扫描的调度壳：拉候选 → 逐单独立事务 → 统计。

业务判定在 services/commission_timeout.py。这里只负责三件事：
1. 一次捞多少候选（BATCH，防积压时占满连接池）；
2. 每单一个 session、一个事务 —— 一单失败不牵连其他单；
3. 汇总统计，方便日志里看效果。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BizError
from app.core.state_machine import PENDING_ACCEPT, PENDING_PAY
from app.core.time_utils import now_plus, utcnow
from app.db import AsyncSessionLocal, engine
from app.models import Commission
from app.services.commission_state import transition
from app.services.commission_timeout import close_pay_timeout, retry_accept_timeout

BATCH = 100 # 单轮上限：积压再多也分批消化，防止占满连接池

async def _candidates(db: AsyncSession) -> tuple[list[int],list[int]]:
    """只读 id，不加载 ORM 实体。两类过期单一次取回。"""
    pay = (await db.execute(
        select(Commission.id)
        .where(Commission.status == PENDING_PAY,
               Commission.pay_deadline < utcnow())
        .order_by(Commission.pay_deadline)
        .limit(BATCH)
    )).scalars().all()
    accept = (await db.execute(
        select(Commission.id)
        .where(Commission.status == PENDING_ACCEPT,
               Commission.accept_deadline.is_not(None),
               Commission.accept_deadline < utcnow())
        .order_by(Commission.accept_deadline)
        .limit(BATCH)
    )).scalars().all()
    return list(pay), list(accept)

async def _run_one(handler, order_id: int) -> bool:
     """单订单：独立 session + 独立事务。handler 是上面两个 service 函数之一。"""
     async with AsyncSessionLocal() as db:
         try:
             ok = await handler(db, order_id)
             await db.commit()
             return ok
         except BizError:
             await db.rollback()
             return False
         
async def scan_once() -> dict[str, int]:
    async with AsyncSessionLocal() as db:
        pay_ids, accept_ids = await _candidates(db)

    closed = 0
    for oid in pay_ids:
        closed += await _run_one(close_pay_timeout, oid)
    retried = 0
    for oid in accept_ids:
        retried += await _run_one(retry_accept_timeout, oid)
    return {"pay_timeout_closed": closed, "accept_timeout_retried": retried}

async def _main() -> None:
    try:
        print(await scan_once())
    finally:
        await engine.dispose()



if __name__ == '__main__':
    import asyncio
    asyncio.run(_main())