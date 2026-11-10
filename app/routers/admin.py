"""管理端：分类与服务项的增删改查。

状态码约定（映射写在本层，不用全局异常处理器）：
400 参数/引用无效 ｜ 404 不存在 ｜ 409 唯一约束冲突、被引用不能删
"""
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.db import DB
from app.schemas.catalog import (
    CategoryIn, CategoryOut, CategoryUpdate, ItemIn, ItemOut, ItemUpdate,
)
from app.services import catalog_service

router = APIRouter(prefix="/admin", tags=["admin"])

_STATUS =  {
    "CATEGORY_NOT_FOUND": 404,
    "ITEM_NOT_FOUND": 404,
    "CATEGORY_DUPLICATE": 409,
    "CATEGORY_IN_USE": 409,
}

def _fail(e: BizError) -> NoReturn:
    raise HTTPException(status_code=_STATUS.get(e.code, 400),
                        detail={"code": e.code, "message": str(e)})

@router.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(data: CategoryIn, db:AsyncSession = DB):
    try:
        return await catalog_service.create_category(db, data)
    except BizError as e:
        _fail(e)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(include_disabled: bool = Query(True),
                          db: AsyncSession = DB):
    return await catalog_service.list_categories(db, include_disabled)

@router.put("/categories/{cat_id}", response_model=CategoryOut)
async def update_category(cat_id: int, data: CategoryUpdate,
                          db: AsyncSession = DB):
    try:
        return await catalog_service.update_category(db, cat_id, data)
    except BizError as e:
        _fail(e)

@router.delete("/categories/{cat_id}", status_code=204)
async def delete_category(cat_id: int, db: AsyncSession = DB):
    try:
        await catalog_service.delete_category(db, cat_id)
    except BizError as e:
        _fail(e)

@router.post("/items", response_model=ItemOut, status_code=201)
async def create__item(data:ItemIn, db: AsyncSession = DB):
    try:
        return await catalog_service.create_item(db, data)
    except BizError as e:
        _fail(e)

@router.get("/items", response_model=list[ItemOut])
async def list_items(category_id:int | None = Query(None),
                     status: int | None = Query(None),
                     db:AsyncSession = DB):
    return await catalog_service.list_items(db, category_id, status)

@router.put("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id:int, data: ItemUpdate,
                      db: AsyncSession = DB):
    try:
        return await catalog_service.update_item(db, item_id, data)
    except BizError as e:
        _fail(e)