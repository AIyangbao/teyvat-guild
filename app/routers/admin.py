"""管理端：分类与服务项的增删改查。

状态码约定（映射写在本层，不用全局异常处理器）：
400 参数/引用无效 ｜ 404 不存在 ｜ 409 唯一约束冲突、被引用不能删
"""
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.core.deps import require_admin
from app.db import DB
from app.schemas.catalog import (
    CategoryIn, CategoryOut, CategoryUpdate, ItemIn, ItemOut, ItemUpdate,
)
from app.schemas.adventurer import AuditIn, PendingAdventurerPageOut
from app.schemas.stats import StatsOverviewOut
from app.services import audit_service,catalog_service, stats_service

router = APIRouter(prefix="/admin", tags=["admin"])
_write =  APIRouter(dependencies=[Depends(require_admin)])
_STATUS =  {
    "CATEGORY_NOT_FOUND": 404,
    "ITEM_NOT_FOUND": 404,
    "CATEGORY_DUPLICATE": 409,
    "CATEGORY_IN_USE": 409,
    "ADVENTURER_NOT_FOUND": 404,
    "AUDIT_ALREADY_DONE": 409,
}

def _fail(e: BizError) -> NoReturn:
    raise HTTPException(status_code=_STATUS.get(e.code, 400),
                        detail={"code": e.code, "message": str(e)})

@_write.post("/categories", response_model=CategoryOut, status_code=201)
async def create_category(data: CategoryIn, db:AsyncSession = DB):
    try:
        return await catalog_service.create_category(db, data)
    except BizError as e:
        _fail(e)


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(include_disabled: bool = Query(True),
                          db: AsyncSession = DB):
    return await catalog_service.list_categories(db, include_disabled)

@_write.put("/categories/{cat_id}", response_model=CategoryOut)
async def update_category(cat_id: int, data: CategoryUpdate,
                          db: AsyncSession = DB):
    try:
        return await catalog_service.update_category(db, cat_id, data)
    except BizError as e:
        _fail(e)

@_write.delete("/categories/{cat_id}", status_code=204)
async def delete_category(cat_id: int, db: AsyncSession = DB):
    try:
        await catalog_service.delete_category(db, cat_id)
    except BizError as e:
        _fail(e)

@_write.post("/items", response_model=ItemOut, status_code=201)
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

@_write.put("/items/{item_id}", response_model=ItemOut)
async def update_item(item_id:int, data: ItemUpdate,
                      db: AsyncSession = DB):
    try:
        return await catalog_service.update_item(db, item_id, data)
    except BizError as e:
        _fail(e)

@_write.get("/stats/overview", response_model=StatsOverviewOut)
async def stats_overview(days: int = Query(7, ge=1, le=90), db: AsyncSession = DB):
    """看板聚合：挂 _write 子路由 → require_admin 生效（经营数据不公开）。"""
    return await stats_service.get_overview(db, days)

@_write.get("/adventurers/pending", response_model=PendingAdventurerPageOut)
async def list_pending_adventurers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: AsyncSession = DB,
):
    """待审列表：挂 _write 子路由 → GET 也带 require_admin（敏感数据）。"""
    total, items = await audit_service.list_pending_adventurer(db, page, page_size)
    return PendingAdventurerPageOut(total=total, items=items)

@_write.put("/adventurers/{adv_id}/audit")
async def audit_adventurer(adv_id: int, data: AuditIn, db: AsyncSession = DB):
    try:
        adv = await audit_service.set_audit_status(db, adv_id, data.target)
        return {"id": adv.id, "audit_status": adv.audit_status}
    except BizError as e:
        _fail(e)
router.include_router(_write)