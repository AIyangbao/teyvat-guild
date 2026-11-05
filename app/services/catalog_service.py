"""服务目录的写操作。不 commit —— 事务边界归 get_db。"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Category, ServiceItem
from app.schemas.catalog import (
    CategoryIn, CategoryOut, CategoryUpdate, ItemIn, ItemOut, ItemUpdate,
)
from app.core.exceptions import BizError, ErrCode
async def create_category(db: AsyncSession, data: CategoryIn) -> CategoryOut:
    # 先查重只为给友好提示；真正的并发正确性由表上的 unique(name) 兜底。
    # 这里不 catch IntegrityError，因为 flush 失败后 session 处于失效状态，
    # 必须 rollback 才能复用——而 rollback 是事务边界，不归 service 管。
    dup =  (await db.execute(
        select(Category.id).where(Category.name == data.name)
    )).scalar_one_or_none()
    if dup is not None:
        raise BizError("分类名已存在", code="CATEGORY_DUPLICATE")

    cat = Category(name=data.name, sort=data.sort, status=data.status)
    db.add(cat)
    await db.flush()
    return CategoryOut.model_validate(cat)

async def list_categories(db: AsyncSession,
                          include_disabled: bool = True) -> list[CategoryOut]:
    cond = [] if include_disabled else [Category.status == 1]
    rows = (await db.execute(
        select(Category).where(*cond).order_by(Category.sort, Category.id)
        )).scalars().all()
    return [CategoryOut.model_validate(r) for r in rows]

async def update_category(db: AsyncSession, cat_id: int,
                          data: CategoryUpdate) -> CategoryOut:
    cat = (await db.execute(
        select(Category).where(Category.id == cat_id)
    )).scalar_one_or_none()
    if cat is None:
        raise BizError("分类不存在", code="CATEGORY_NOT_FOUND")

    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"] != cat.name:
        dup = (await db.execute(
            select(Category.id).where(Category.name == payload["name"])
        )).scalar_one_or_none()
        if dup is not None:
            raise BizError("分类名已存在", code="CATEGORY_DUPLICATE")

    for k,v in payload.items():
        setattr(cat, k, v)
    await db.flush()
    return CategoryOut.model_validate(cat)

async def delete_category(db: AsyncSession, cat_id: int) -> None:
    cat = (await db.execute(
        select(Category).where(Category.id == cat_id)
    )).scalar_one_or_none()
    if cat is None:
        raise BizError("分类不存在", code="CATEGORY_NOT_FOUND")

    # 物理删除前必须确认没有引用。注意 service_item.category_id 没建外键，
    # 数据库不会替你拦——这一层检查是唯一防线
    used = (await db.execute(
        select(func.count()).select_from(ServiceItem)
        .where(ServiceItem.category_id == cat_id)
    )).scalar_one()
    if used:
        raise BizError(f"该分类下还有{used}个服务项, 不能删除",
                       code="CATEGORY_IN_USE")

    await db.delete(cat)
    await db.flush()

# ---------------- 服务项 ----------------

async def create_item(db: AsyncSession, data: ItemIn) -> ItemOut:
    cat = (await db.execute(
        select(Category.id).where(Category.id == data.category_id)
    )).scalar_one_or_none()
    if cat is None:
        raise BizError("分类不存在", code="CATEGORY_NOT_FOUND")

    item = ServiceItem(**data.model_dump())
    db.add(item)
    await db.flush()
    return ItemOut.model_validate(item)

async def list_items(db: AsyncSession, category_id: int | None = None,
                     status: int | None = None) -> list[ItemOut]:
    cond = []
    if category_id is not None:
        cond.append(ServiceItem.category_id == category_id)
    if status is not None:
        cond.append(ServiceItem.status == status)
    rows = (await db.execute(
        select(ServiceItem).where(*cond).order_by(ServiceItem.id)
    )).scalars().all()
    return [ItemOut.model_validate(r) for r in rows]

async def update_item(db: AsyncSession, item_id: int,
                      data: ItemUpdate) -> ItemOut:
    item = (await db.execute(
        select(ServiceItem).where(ServiceItem.id == item_id)
    )).scalar_one_or_none()
    if item is None:
        raise BizError("服务项不存在", code="ITEM_NOT_FOUND")

    payload = data.model_dump(exclude_unset=True)
    if "category_id" in payload:
        exists = (await db.execute(
            select(Category.id).where(Category.id == payload["category_id"])
        )).scalar_one_or_none()
        if exists is None:
            raise BizError("分类不存在", code="CATEGORY_NOT_FOUND")

    for k, v in payload.items():
        setattr(item, k, v)
    await db.flush()
    return ItemOut.model_validate(item)