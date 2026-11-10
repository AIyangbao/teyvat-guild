"""支付单：发起（幂等）与回调（验签在路由层，幂等/金额校验/推进在 service）。

真实链路：我们 → 第三方收银台 → 第三方异步回调我们。
模拟环境省掉收银台页面，回调由 curl/脚本直接打我们的回调接口。
"""
import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.time_utils import utcnow
from app.models import Commission, Payment
from app.services.commission_state import transition

def _gen_out_trade_no() -> str:
    """与订单号同风格：时间戳+随机尾巴。真实支付单号是给 DBA 排障看的，
    纯 uuid 查日志时无从下手，这和 order_no 的 TODO 是同一个问题。"""
    return f"PAY{utcnow():%Y%m%d%H%M%S}{uuid.uuid4().hex[:8].upper()}"

async def create_payment(db: AsyncSession, order_id: int, player_id: int) -> Payment:
    """发起支付。只建支付单，订单仍是待支付——发起 ≠ 支付成功。"""
    order = (await db.execute(
        select(Commission).where(Commission.id == order_id).with_for_update()
    )).scalar_one_or_none()
    if order is None:
        raise BizError("委托不存在", code="ORDER_NOT_FOUND")
    if order.player_id != player_id:
        raise BizError("不能支付他人的委托", code="FORBIDDEN")
    if order.status != "待支付":
         raise BizError("当前状态不可支付", code="STATE_ILLEGAL")
    if order.pay_deadline is not None and order.pay_deadline < utcnow():
         # 提前拦截，缩小「支付 vs 超时关单」的竞态窗口（不能消除，见文档）
         raise BizError("支付期限已过", code="PAY_EXPIRED")

    # 发起幂等：已有未完成支付单 → 复用它，不新建
    # （防玩家狂点支付按钮，一单建出一堆 pending）
    existing = (await db.execute(
        select(Payment).where(Payment.commission_id == order.id,
                              Payment.status == "pending")
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    payment = Payment(commission_id=order_id,
                      out_trade_no=_gen_out_trade_no(),
                      amount=order.total_amount,
                      channel="mock",
                      status="pending")
    db.add(payment)
    await db.flush()
    return payment

async def handle_callback(db: AsyncSession, out_trade_no: str,
                          amount: Decimal, payload: dict) -> dict:
        """第三方回调处理。整个函数一个事务，中途任何失败全回滚。

    幂等三层：
      ① 金额校验不一致 → 拒绝（风控线索，什么都不推进）
      ② payment 已 success → 直接按成功返回（第三方重试不炸）
      ③ CAS 抢单式占坑 pending→success，抢不到 = 并发回调，同样幂等返回
    """
        payment = (await db.execute(
             select(Payment).where(Payment.out_trade_no == out_trade_no)
        )).scalar_one_or_none()
        if payment is None:
             raise BizError("支付单不存在", code="PAYMENT_NOT_FOUND")

        # ① 金额比对：放在占坑之前——金额创建后不变，先查后 CAS 无竞态
        if payment.amount != amount:
             raise BizError("回调金额与支付单不符", code="PAYMENT_AMOUNT_MISMATCH")

        # ② 已处理过：幂等返回。注意这里 rowcount 逻辑还没跑，
        # 先查快照是为了区分「已成功」和「已关闭」两种语义
        if payment.status == "success":
             return {"payment": payment, "first": False}
        if payment.status != "pending":
             raise BizError("支付单已关闭", code="PAYMENT_CLOSED")

        # ③ CAS 占坑：单语句完成「判断+修改」，并发回调只有一个能赢
        result = await db.execute(
         update(Payment)
         .where(Payment.out_trade_no == out_trade_no,
               Payment.status == "pending")
         .values(status="success", paid_at=utcnow(),
                callback_payload=payload),
         execution_options={"synchronize_session":"fetch"},    # 让内存里的 payment 对象同步成新值
        )
        if result.rowcount == 0:
             # 快照读之后被人抢先了 → 同样幂等返回
             return {"payment": payment, "first": False}
        # 占坑成功 → 推进订单（同事务：transition 失败则 payment 的 success 也回滚
        order = await transition(db, payment.commission_id, "支付成功",
                                 operator_role="system")
        return {"payment": payment, "first": True, "order": order}
    