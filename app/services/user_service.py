"""用户资料：数据访问 + ORM→DTO 转换。不 commit —— 事务边界归 get_db。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BizError
from app.models import Adventurer, User
from app.schemas.user import AdventurerUpdate, ProfileOut

async def get_my_adventurer(db: AsyncSession, user: User) -> Adventurer | None:
    """当前用户的冒险家档案。玩家返回 None —— 角色判断是业务规则。"""
    if user.role != "adventurer":
        return None
    return (await db.execute(
        select(Adventurer).where(Adventurer.user_id == user.id)
    )).scalar_one_or_none()

def to_profile_out(user: User, adv: Adventurer | None) -> ProfileOut:
    """纯转换：不碰 DB、不碰 Request，可单独单测。"""
    return ProfileOut(
        id=user.id, nickname=user.nickname, avatar=user.avatar,
        role=user.role, phone=user.phone,
        game_nickname=adv.game_nickname if adv else None,
        server=adv.server if adv else None,
        skill_tags=adv.skill_tags if adv else None,
        online_status=adv.online_status if adv else None,
    )

async def get_profile(db: AsyncSession, user: User) -> ProfileOut:
    return to_profile_out(user, await get_my_adventurer(db,user))

async def update_nickname(db: AsyncSession, user: User, nickname: str) -> ProfileOut:
    user.nickname = nickname
    await db.flush()
    return await get_profile(db, user)

async def set_avatar(db: AsyncSession, user: User, url: str) -> ProfileOut:
    user.avatar = url
    await db.flush()
    return await get_profile(db, user)

async def update_my_adventurer(
        db: AsyncSession, user: User, data: AdventurerUpdate
) -> ProfileOut:
    adv = await get_my_adventurer(db, user)
    if adv is None:
        raise BizError("需要冒险者身份", code="ROLE_FORBIDDEN")
    adv.game_nickname = data.game_nickname
    adv.skill_tags = data.skill_tags
    adv.online_status = data.online_status
    await db.flush()
    return await get_profile(db, user)
