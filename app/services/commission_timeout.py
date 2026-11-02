"""超时判定 + 流转。不 commit —— 事务边界归调用方（定时任务 / 将来的路由）。

为什么放 services 不放 tasks：
tasks 只管「多久跑一次、怎么开事务」，是调度壳；业务判定必须能被单测直接调用。
写在 tasks 里还硬编码 AsyncSessionLocal 的话，测试事务里的数据对另开的连接
不可见，这段逻辑永远测不到。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.state_machine import PENDING_ACCEPT, PENDING_PAY
from app.core.time_utils import now_plus, utcnow
from app.models import Commission
from app.services.commission_state import transition

async def _lock_order(db: AsyncSession, order_id: int)  -> Commission | None:
    """行锁取单。多个 worker 并发扫描时，这里是唯一的串行点。"""
    return (await db.execute(
        select(Commission).where(Commission.id == order_id).with_for_update()
    )).scalar_one_or_none()

async def close_pay_timeout(db: AsyncSession, order_id: int) -> bool:
    """支付超时 → 已关闭。真处理了 True；已被并发处理 / 已支付则 False。"""
    order = await _lock_order(db, order_id)
    if(order is None
           or order.status != PENDING_PAY
           or order.pay_deadline >= utcnow()):
        return False
    await transition(db, order_id, "支付超时", operator_role="system")
    return True

async def retry_accept_timeout(db: AsyncSession, order_id: int) -> bool:
    """接单超时：未到上限就自转移（顺带推开 deadline），到顶则关闭。"""
    order = await _lock_order(db, order_id)
    if (order is None
            or order.status != PENDING_ACCEPT
            or order.accept_deadline is None
            or order.accept_deadline >= utcnow()):
        return False
    if order.pool_retry >= settings.max_pool_retry:
        await transition(db, order_id, "无人接单关闭", operator_role="system")
    else:
        await transition(db, order_id, "超时无人接", operator_role="system")
        # 不推 deadline，下一轮扫描会立刻再命中同一单（pool_retry 一轮涨一）
        order.accept_deadline = now_plus(minutes=settings.order_accept_timeout_min)
    return True