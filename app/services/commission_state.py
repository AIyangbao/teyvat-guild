from sqlalchemy import select,update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import BizError
from app.core.state_machine import IllegalTransition, next_status,IN_PROGRESS,PENDING_ACCEPT
from app.core.time_utils import now_plus, utcnow
from app.core.cache import cache_delete_prefix
from app.services.cache_keys import HALL_CACHE_PREFIX
from app.services.audit_service import require_approved
from app.models import Commission, CommissionLog, Adventurer
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
    await cache_delete_prefix(HALL_CACHE_PREFIX)
    return order

async def accept_order(db: AsyncSession, order_id: int, adventurer_id: int) -> Commission:
    """抢单：单语句 CAS。条件不满足则 rowcount==0，说明被别人抢先。"""
    await require_approved(db, adventurer_id)
    result = await db.execute(
        update(Commission)
        .where(Commission.id == order_id,
               Commission.status == PENDING_ACCEPT)
        .values(status=IN_PROGRESS,
                adventurer_id=adventurer_id,
                accepted_at=utcnow())
    )
    if result.rowcount == 0:
        exists = (await db.execute(
            select(Commission.id).where(Commission.id == order_id)
        )).scalar_one_or_none()
        if exists is None:
            raise BizError("委托不存在", code="ORDER_NOT_FOUND")
        raise BizError("手慢了,该委托已被接走", code="ACCEPT_CONFLICT")

    order = (await db.execute(
        select(Commission).where(Commission.id == order_id)
    )).scalar_one()
    db.add(CommissionLog(
        commission_id=order.id,
        from_status=PENDING_ACCEPT,
        to_status=IN_PROGRESS,
        event="抢单成功",
        operator_id=adventurer_id,
        operator_role="adventurer",
    ))
    await db.flush()
    await cache_delete_prefix(HALL_CACHE_PREFIX)
    return order

async def confirm_by_player(db: AsyncSession, order_id: int, player_id: int) -> Commission:
    """玩家确认交付：先验归属，再走状态机。"""
    order = (await db.execute(
        select(Commission).where(Commission.id == order_id).with_for_update()
    )).scalar_one_or_none()
    if order is None:
        raise BizError("委托不存在", code="ORDER_NOT_FOUND")
    if order.player_id != player_id:
        raise BizError("无权操作该委托", code="FORBIDDEN")
    return await transition(db, order_id, "玩家确认",
                            operator_id=player_id, operator_role="player")

async def deliver_by_adventurer(db: AsyncSession, order_id: int, adventurer_id: int) -> Commission:
    """冒险家提交交付：先验这单是不是自己接的，再走状态机。"""
    order = (await db.execute
            (select(Commission).where(Commission.id == order_id).with_for_update()
            )).scalar_one_or_none()
    if order is None:
        raise BizError("委托不存在", code="ORDER_NOT_FOUND")
    if order.adventurer_id != adventurer_id:
        raise BizError("无权操作该委托", code="FORBIDDEN")
    return await transition(db, order_id, "提交交付",
                            operator_id=adventurer_id, operator_role="adventurer")

async def settle_order(db: AsyncSession, order_id: int) -> Commission:
    """结算 = 状态归档 + 完单数入账。由扫描器调用，每单独立事务，不 commit。"""
    order = await transition(db, order_id, "结算", operator_role="system")
    aid = order.adventurer_id
    # 防御：能走到 COMPLETED 的单必经抢单，理论上有冒险家。真没有就报错别硬撑
    if aid is None:
        raise BizError("该委托没有接单冒险家,无法结算", code="SETTLE_NO_ADVENTURER")

    # 原子自增：数据库内完成读改写，并发结算也不会丢计数
    await db.execute(
        update(Adventurer)
        .where(Adventurer.id == aid)
        .values(finished_count=Adventurer.finished_count + 1)
        .execution_options(synchronize_session="fetch")
    )
    return order

