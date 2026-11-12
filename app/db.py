from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config import settings
from sqlalchemy import MetaData
engine = create_async_engine(
    settings.db_url,
    echo=settings.db_echo,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",                                # 索引
    "uq": "uq_%(table_name)s_%(column_0_name)s",                  # 唯一约束
    "ck": "ck_%(table_name)s_%(constraint_name)s",                # 检查约束
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # 外键
    "pk": "pk_%(table_name)s",                                    # 主键
}
class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

from fastapi import Depends

DB = Depends(get_db, scope="function")