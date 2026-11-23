"""冒险家公开档案：只读列表，不碰状态机。"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Adventurer
from app.schemas.adventurer import AdventurerCardOut

async def list_public_adventurers(
        db: AsyncSession, page: int, page_size: int
) -> tuple[int, list[AdventurerCardOut]]:
     """大厅卡片列表：在线优先，评分高者靠前，id 兜底保证分页稳定。"""
     total = (await db.execute(
          select(func.count()).select_from(Adventurer)
     )).scalar_one()

     rows = (await db.execute(
          select(Adventurer)
          .order_by(
               (Adventurer.online_status == "online").desc(),
               Adventurer.rating.desc(),
               Adventurer.id.asc(),
          )
          .offset((page - 1) * page_size)
          .limit(page_size)
     )).scalars().all()

     return total, [AdventurerCardOut(
          id=a.id, game_nickname=a.game_nickname, server=a.server,
          skill_tags=a.skill_tags, rating=a.rating,
          finished_count=a.finished_count,
     ) for a in rows]