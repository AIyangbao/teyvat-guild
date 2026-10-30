"""超时扫描器：把 pay_deadline / accept_deadline / pool_retry 接上。

调用方只负责按节奏调 scan_once()，事务边界在这里面自己开（定时任务没有
get_db 依赖，每单自己 commit / rollback）。

设计要点（为什么这么写）：
1. 自转移必须推进 accept_deadline——否则下一轮扫描立刻再命中同一单，
   pool_retry 一轮涨一，很快爆掉。
2. 扫出来的 id 只是候选：真正的判定必须在 with_for_update 锁内重查。
   两个 worker 同时扫到同一单时，第一个处理完提交后，第二个进来状态
   仍然是「待接单」（自转移不抛 STATE_ILLEGAL），状态机拦不住，
   只能靠锁内重查 deadline（第一个已把它推到未来）。
3. 一单一个事务：一批共用 session 时，第 N 单抛 BizError 会把前面
   全部回滚，且长事务持有大量行锁。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BizError
from app.core.state_machine import PENDING_ACCEPT, PENDING_PAY
from app.core.time_utils import now_plus, utcnow
from app.db import AsyncSessionLocal
from app.models import Commission
from app.services.commission_state import transition

BATCH = 100 # 单轮上限：积压再多也分批消化，防止占满连接池

async def _find_pay_timeouts(db: AsyncSession,limit: int = BATCH) -> list[int]:
    """待支付且已过 pay_deadline。命中 idx_pay_timeout(status, pay_deadline)。"""
    rows = await db.execute(
        select(Commission.id)
        .where(Commission.status == PENDING_PAY,
               Commission.pay_deadline < utcnow())
        .order_by(Commission.pay_deadline)
        .limit(limit)
    )
    return list(rows.scalars().all())

async def _find_accept_timeouts(db: AsyncSession, limit: int = BATCH) -> list[int]:
    """待接单且已过 accept_deadline。NULL 必须排除（未支付的单没有这个值）。"""
    rows = await db.execute(
        select(Commission.id)
        .where(Commission.status == PENDING_ACCEPT,
               Commission.accept_deadline.is_not(None),
               Commission.accept_deadline < utcnow())
        .order_by(Commission.accept_deadline)
        .limit(limit)
    )
    return list(rows.scalars().all())

async def _close_pay_timeout(order_id: int) -> bool:
     """支付超时 → 已关闭。单订单一个事务。真处理了 True，被并发抢先 False。"""
     async with AsyncSessionLocal() as db:
        try:
             order = (await db.execute(
                 select(Commission).where(Commission.id == order_id).with_for_update()
             )).scalar_one_or_none()
             if (order is None
                      or order.status != PENDING_PAY
                      or order.pay_deadline >= utcnow()):
                 await db.rollback() # 显式回滚，提前释放行锁
                 return False
             await transition(db, order_id, "支付超时", operator_role="system")
             await db.commit()
             return True
        except BizError:
            await db.rollback()
            return False

async def _retry_accept_timeout(order_id: int) -> bool:
    async with AsyncSessionLocal() as db:
        try:
            order = (await db.execute(
                select(Commission).where(Commission.id == order_id).with_for_update()
            )).scalar_one_or_none()
            if (order is None
                     or order.status != PENDING_ACCEPT
                     or order.accept_deadline is None
                     or order.accept_deadline >= utcnow()):
                await db.rollback()
                return False
            if order.pool_retry >= settings.max_pool_retry:
                await transition(db, order_id, "无人接单关闭",operator_role="system")
            else:
                await transition(db, order_id, "超时无人接", operator_role="system")
                # 自转移后必须推进 deadline，否则下一轮立刻再命中
                order.accept_deadline = now_plus(
                    minutes=settings.order_accept_timeout_min
                )
            await db.commit()
            return True
        except BizError:
            await db.rollback()
            return False

async def scan_once() -> dict[str,int]:
    """跑一轮：拉候选 → 逐单开事务处理 → 返回统计。"""
    # 这个块只读候选 id，读完立刻退出；不要在这里面调 transition，
    # 否则又变回「一批一个事务」（要点 3）
    async with AsyncSessionLocal() as db:
        pay_ids = await _find_pay_timeouts(db)
        accept_ids = await _find_accept_timeouts(db)

    closed = retried = 0
    for oid in pay_ids:
        closed += await _close_pay_timeout(oid)
    for oid in accept_ids:
        retried += await _retry_accept_timeout(oid)
    return {"pay_timeout_closed": closed, "accept_timeout_retried": retried}

if __name__ == '__main__':
    import asyncio
    print(asyncio.run(scan_once()))