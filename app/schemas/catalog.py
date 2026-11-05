"""服务目录（分类 + 服务项）的入出参。

Update 模型全部字段可选，靠 model_dump(exclude_unset=True) 区分
「没传这个字段」和「传了 null」——前者不改，后者用于清空 description。
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    sort: int = 0
    status: int = Field(1, ge=0, le=1)


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=30)
    sort: int | None = None
    status: int | None = Field(None, ge=0, le=1)

class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort: int
    status: int

class ItemIn(BaseModel):
    category_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=80)
    description: str | None = None
    price:Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    duration_min: int = Field(60, ge=1)
    status: int = Field(1, ge=0, le=1)

class ItemUpdate(BaseModel):
    category_id: int | None = Field(None, gt=0)
    name: str | None = Field(None, min_length=1, max_length=80)
    description: str | None = None
    price: Decimal | None = Field(None, gt=0, max_digits=10, decimal_places=2)
    duration_min: int | None = Field(None, ge=1)
    status: int | None = Field(None, ge=0, le=1)
    
class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    name: str
    description: str | None
    price: Decimal
    duration_min: int
    status: int
    created_at: datetime