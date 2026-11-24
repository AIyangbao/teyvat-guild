"""冒险家审核：pending → approved / rejected。状态机极简，但转换要守住。"""
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.models import Adventurer
from app.schemas.adventurer import PendingAdventurerOut
PENDING = "pending"
APPROVED = "approved"
REJECTED = "rejected"

async def set_audit_status(
        db: AsyncSession, adventurer_id: int, target: str
) -> Adventurer:
    """管理员审核。只允许 pending → approved/rejected，其余状态不可回转。"""
    if target not in (APPROVED, REJECTED):
        raise BizError("目标状态非法", code="AUDIT_STATE_INVALID")

    adv = await db.get(Adventurer, adventurer_id)
    if adv is None:
        raise BizError("冒险家不存在", code="ADVENTURER_NOT_FOUND")
    if adv.audit_status != PENDING:
        raise BizError("该冒险家已审核, 不能重复操作", code="AUDIT_ALREADY_DONE")

    adv.audit_status = target
    await db.flush()
    return adv

async def require_approved(db: AsyncSession, adventurer_id: int) -> None:
    """接单前的闸门。未通过审核抛 403 对应的业务码。"""
    adv = await db.get(Adventurer, adventurer_id)
    if adv is None or adv.audit_status != APPROVED:
        raise BizError("账号未通过审核, 暂不能接单", code="ADVENTURER_NOT_APPROVED")

async def list_pending_adventurer(
        db: AsyncSession, page: int, page_size: int
) -> tuple[int, list[PendingAdventurerOut]]:
    """待审队列：先申请的排前面，id 兜底保证分页稳定。"""
    total = (await db.execute(
        select(func.count()).select_from(Adventurer)
        .where(Adventurer.audit_status == PENDING)
    )).scalar_one()

    rows = (await db.execute(
        select(Adventurer)
        .where(Adventurer.audit_status == PENDING)
        .order_by(Adventurer.created_at.asc(), Adventurer.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).scalars().all()

    return total, [PendingAdventurerOut(
        id=a.id, user_id=a.user_id, game_nickname=a.game_nickname,
        game_uid=a.game_uid, server=a.server, skill_tags=a.skill_tags,
        audit_status=a.audit_status, created_at=a.created_at,
    ) for a in rows]