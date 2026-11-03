import uuid
from decimal import Decimal
from sqlalchemy import func,select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.core.time_utils import now_plus, utcnow
from app.core.exceptions import BizError
from app.core.state_machine import PENDING_ACCEPT, ALL_STATES
from app.models import Commission, CommissionItem, ServiceItem, CommissionLog
from app.schemas.commission import (CommissionDetailOut, CommissionItemOut, CommissionLogOut,HallOrderOut)


def _gen_order_no() -> str:
    """时间戳 + 随机尾巴：可读、趋势递增、基本不撞。
    TODO: 想想为什么不只用 uuid4().hex（提示：DBA 排障时哪个好用？）
    """
    return f"{utcnow():%Y%m%d%H%M%S}{uuid.uuid4().hex[:8].upper()}"

async def create_order(db: AsyncSession, player_id:int,
                       item_inputs: list[dict], game_uid: str,
                       server: str, expect_time=None, remark: str = "") -> Commission:
    if not item_inputs:
        raise BizError("至少选择一项服务")
    # 一次把所有 service_item 查出来（注意 in_ 的用法），不在库里的/下架的 → BizError
    ids = [i["service_item_id"] for i in item_inputs]
    rows = (await db.execute(
        select(ServiceItem).where(ServiceItem.id.in_(ids), ServiceItem.status == 1)
    )).scalars().all()
    # 列表 → 字典索引：id 能直接取行，还顺便完成「查回数量校验」
    item_map = {r.id: r for r in rows}
    if len(item_map) != len(set(ids)):
        raise BizError("包含无效或已下架的服务项", code="ITEM_INVALID")
    # ② 服务端算钱 + 建快照列表
    items, total = [], Decimal("0")
    for i in item_inputs:
        row = item_map[i["service_item_id"]]
        qty = i["qty"]
        if not (1 <= qty <= 10):
          raise BizError("单件服务数量需在1~10之间", code="QTY_INVALID")
        subtotal = row.price * qty
        total += subtotal
        items.append(CommissionItem(
        service_item_id=row.id,
        snapshot_name=row.name,
        snapshot_price=row.price,
        quantity=qty,
        ))
    order = Commission(
        order_no=_gen_order_no(),
        player_id=player_id,
        game_uid=game_uid,
        server=server,
        expect_time=expect_time,
        total_amount=total,
        status="待支付",
        remark=remark,
        pay_deadline=now_plus(minutes=settings.order_pay_timeout_min),
    )
    db.add(order)
    await db.flush()

    for item in items:
        item.commission_id = order.id
        db.add(item)
    return order

async def _items_map(db:AsyncSession, ids: list[int]) -> dict[int, list[CommissionItemOut]]:
    """一次 IN 查询把多张单的明细全取回，按 commission_id 分组。"""
    result: dict[int, list[CommissionItemOut]] = {i: [] for i in ids}
    if not ids:
        return result
    rows = (await db.execute(select(CommissionItem).where(CommissionItem.commission_id.in_(ids))
                             )).scalars().all()
    for it in rows:
        result[it.commission_id].append(CommissionItemOut(
            name=it.snapshot_name,
            quantity=it.quantity,
            snapshot_price=it.snapshot_price,
        ))
    return result

async def get_detail(db: AsyncSession, order_id: int) -> CommissionDetailOut:
    """订单详情 + 明细 + 状态流转时间线。公开接口。"""
    order = (await db.execute(select(Commission).where(Commission.id == order_id)
                              )).scalar_one_or_none()
    if order is None:
        raise BizError("委托不存在", code="ORDER_NOT_FOUND")

    items_map = await _items_map(db,[order.id])
    logs = (await db.execute(
        select(CommissionLog)
        .where(CommissionLog.commission_id == order.id)
        # 按 id 兜底排序：DATETIME 只精确到秒，同一秒内的多条日志顺序会飘
        .order_by(CommissionLog.created_at, CommissionLog.id)
    )).scalars().all()

    return CommissionDetailOut(
        id=order.id, order_no=order.order_no, status=order.status,
        player_id=order.player_id, adventurer_id=order.adventurer_id,
        game_uid=order.game_uid, server=order.server,
        total_amount=order.total_amount, remark=order.remark,
        expect_time=order.expect_time, created_at=order.created_at,
        pay_deadline=order.pay_deadline, accept_deadline=order.accept_deadline,
        paid_at=order.paid_at, accepted_at=order.accepted_at,
        finished_at=order.finished_at, settled_at=order.settled_at,
        pool_retry=order.pool_retry,
        items=items_map[order.id],
        timeline=[CommissionLogOut(
            from_status=l.from_status, to_status=l.to_status, event=l.event,
            operator_role=l.operator_role, created_at=l.created_at,
        ) for l in logs],
    )


async def list_mine(db: AsyncSession, player_id: int, page: int, page_size: int, status: str | None = None) -> tuple[int, list[HallOrderOut]]:
    """我的委托：按玩家过滤，可选状态。命中 idx_player(player_id, created_at)。"""
    if status is not None and status not in ALL_STATES:
        raise BizError("非法状态筛选", code="STATE_INVALID")

    cond = [Commission.player_id == player_id]
    if status:
        cond.append(Commission.status == status)

    total = (await db.execute(
        select(func.count()).select_from(Commission).where(*cond)
    )).scalar_one()

    orders = (await db.execute(
        select(Commission).where(*cond)
        .order_by(Commission.created_at.desc())
        .offset((page-1) * page_size).limit(page_size)
    )).scalars().all()

    items_map = await _items_map(db,[o.id for o in orders])
    result = [HallOrderOut(
        id=o.id, order_no=o.order_no,total_amount=o.total_amount,
        remark=o.remark, expect_time=o.expect_time, created_at=o.created_at,
        items=items_map[o.id],
    ) for o in orders]
    return total, result

async def list_hall(db: AsyncSession, page: int, page_size: int) -> tuple[int, list[HallOrderOut]]:
    """委托大厅：待接单的分页列表，最新的在前。命中 idx_hall(status, created_at)。

    明细用第二条 IN 查询拼装，固定 2 条 SQL——循环内逐单查就是 N+1。
    """
    cond = Commission.status == PENDING_ACCEPT

    total = (await db.execute(
        select(func.count()).select_from(Commission).where(cond)
    )).scalar_one()

    orders = (await db.execute(
        select(Commission).where(cond)
        .order_by(Commission.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    # 收集本页订单 id，一次 IN 查询拿全部明细
    ids = [o.id for o in orders]
    items_map = await _items_map(db, ids)

    result = [HallOrderOut(
        id = o.id, order_no=o.order_no, total_amount=o.total_amount,
        remark=o.remark, expect_time=o.expect_time, created_at=o.created_at,
        items=items_map[o.id],
    ) for o in orders]
    return total, result
