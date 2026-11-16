from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time_utils import utcnow
from app.db import Base

class Review(Base):
    """玩家对已完成委托的评价。一单一评，由库层唯一约束兜底。"""

    __tablename__ = "review"
    __table_args__ = (
        Index("idx_review_adventurer", "adventurer_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commission_id: Mapped[int] = mapped_column(
        ForeignKey("commission.id"), unique=True, nullable=False)
    player_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    adventurer_id: Mapped[int] = mapped_column(ForeignKey("adventurer.id"), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)