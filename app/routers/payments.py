"""支付回调。

注意：这个路由**不能挂 JWT 鉴权**——第三方支付服务器没有我们的 token，
只认签名。这是支付模块最容易被新人写错的地方：给回调接口加 @Depends(get_current_user)，
线上必然收不到回调。
"""
from fastapi import APIRouter, Depends,Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BizError
from app.db import DB
from app.schemas.payment import CallbackIn, CallbackOut
from app.services import payment_service

router = APIRouter(prefix="/payments", tags=["支付"])

@router.post("/{out_trade_no}/callback", response_model=CallbackOut)
async def callback(out_trade_no: str,
                   data: CallbackIn,
                   x_pay_sign: str = Header(""),
                   db: AsyncSession = DB):
    # 验签：模拟环境比对共享密钥；真实是「body + 商户密钥」算出签名再比对
    if x_pay_sign != settings.pay_callback_secret:
        raise HTTPException(status_code=401,
                            detail={"code": "BAD_SIGN", "message": "签名校验失败"})
    try:
        # mode="json"：Decimal 转成字符串，否则 JSON 列序列化会报错
        r = await payment_service.handle_callback(
            db, out_trade_no, data.amount, data.model_dump(mode="json"))
    except BizError as e:
        status = (404 if e.code == "PAYMENT_NOT_FOUND"
                  else 409 if e.code in ("PAYMENT_CLOSED", "STATE_ILLEGAL")
                  else 400)
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})

    order = r.get("order")
    return CallbackOut(out_trade_no=out_trade_no,
                       payment_status=r["payment"].status,
                       first_time=r["first"],
                       order_id=r["payment"].commission_id,
                       order_status=order.status if order else None)