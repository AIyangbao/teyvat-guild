from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field

class OrderItemIn(BaseModel):
    service_item_id: int = Field(gt=0)
    qty: int = Field(ge=1, le=10)

class OrderCreateIn(BaseModel):
    items: list[OrderItemIn] = Field(min_length=1)
    game_uid: str = Field(min_length=1,max_length=20)
    server: str = Field(min_length=1, max_length=20)
    expect_time: datetime | None = None
    remark: str = Field(default="",max_length=255)

class CommissionItemOut(BaseModel):
    """大厅里一条订单的服务明细。"""
    name: str
    quantity: int
    snapshot_price: Decimal

class HallOrderOut(BaseModel):
    id: int
    order_no: str
    total_amount: Decimal
    remark: str
    expect_time: datetime | None
    created_at: datetime
    items: list[CommissionItemOut]

class CommissionLogOut(BaseModel):
    from_status:str
    to_status: str
    event: str
    operator_role: str
    created_at: datetime

class CommissionDetailOut(BaseModel):
    id: int
    order_no: str
    status: str
    player_id: int
    adventurer_id: int | None
    game_uid: str
    server: str
    total_amount: Decimal
    remark: str
    expect_time: datetime | None
    created_at: datetime
    pay_deadline: datetime
    accept_deadline: datetime | None
    paid_at: datetime | None
    accepted_at: datetime | None
    finished_at: datetime | None
    settled_at: datetime | None
    pool_retry: int
    items: list[CommissionItemOut]
    timeline: list[CommissionLogOut]

class HallPageOut(BaseModel):
    total: int
    items: list[HallOrderOut]