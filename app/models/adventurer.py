from decimal import Decimal
from sqlalchemy import JSON, BigInteger, DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.time_utils import utcnow
from datetime import datetime
from app.db import Base

class Adventurer(Base):
    __tablename__ = "adventurer"
    __table_args__ = (
        UniqueConstraint("game_uid","server", name="uk_game_uid"),
        Index("idx_dispatch", "audit_status", "online_status", "rating"), # 派单推荐用
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    game_uid: Mapped[str] = mapped_column(String(20), nullable=False)
    server: Mapped[str] = mapped_column(String(20), nullable=False)
    game_nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    skill_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    rating: Mapped[Decimal] = mapped_column(Numeric(3,2), nullable=False, default=Decimal("5.00"))
    finished_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    abandoned_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrent: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    audit_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    online_status: Mapped[str] = mapped_column(String(20), nullable=False, default="offline")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
