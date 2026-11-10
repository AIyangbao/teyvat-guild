"""支付的出入参。"""
from decimal import Decimal
from pydantic import  BaseModel, Field

class PayCreateOut(BaseModel):
     """发起支付的返回：相当于收银台参数，拿它去「第三方」付款。"""
     out_trade_no: str
     amount: str
     channel: str

class CallbackIn(BaseModel):
     """第三方回调的 body：金额必带，真实支付还带签名串/交易号等。"""
     amount: Decimal = Field(gt=0)
     message: str = ""

class CallbackOut(BaseModel):
     out_trade_no: str
     payment_status: str
     first_time: bool # False = 重复回调（幂等生效）
     order_id: int
     order_status: str | None = None # 重复回调时为 None
     
