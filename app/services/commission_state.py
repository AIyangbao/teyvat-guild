from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import BizError
from app.core.state_machine import IllegalTransition, next_status
from app.core.time_utils import now_plus, utcnow
from app.models import Commission, CommissionLog
from app.config import settings
# 事件 → 该记的时间戳字段。只列「需要记时刻」的，其余不填
_EVENT_TIMESTAP = {
    "支付成功": "paid_at",
    "抢单成功": "accepted_at",
    "提交交付": "finished_at",
    "结算": "settled_at",
}

async def transition(db: AsyncSession, order_id: int, event: str, *,
                      operator_id: int | None = None,
                      operator_role: str = "system") -> Commission:
    """状态流转唯一入口：锁行 → 算目标态 → 改字段 → 记日志。不 commit。"""
    order = (await db.execute(
        select(Commission).where(Commission.id == order_id).with_for_update()
    )).scalar_one_or_none()
    if order is None:
        raise BizError("委托不存在", code="ORDER_NOT_FOUND")

    prev = order.status
    try:
        target = next_status(prev,event)
    except IllegalTransition as e:
        raise BizError(str(e), code="STATE_ILLEGAL") from e
    order.status = target

    if prev == target: # 自转移：超时无人接，只累加重试次数
        order.pool_retry += 1
    else:
        field = _EVENT_TIMESTAP.get(event)
        if field:
            setattr(order, field, utcnow())

    if event == "支付成功":
        order.accept_deadline = now_plus(minutes=settings.order_accept_timeout_min)

    db.add(CommissionLog(
        commission_id=order.id,
        from_status=prev,
        to_status=target,
        event=event,
        operator_id=operator_id,
        operator_role=operator_role,
    ))
    await db.flush()
    return order
