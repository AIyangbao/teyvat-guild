from datetime import datetime
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