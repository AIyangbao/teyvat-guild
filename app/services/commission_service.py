import uuid
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from app.core.time_utils import now_plus, utcnow
from app.core.exceptions import BizError
from app.models import Commission, CommissionItem, ServiceItem


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