from datetime import datetime
from sqlalchemy import BigInteger, DateTime, Integer, Numeric, Index,String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.time_utils import utcnow
from app.db import Base

class CommissionLog(Base):
    __tablename__ = "commission_log"
    __table_args__ = (Index("idx_commission", "commission_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commission_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_status: Mapped[str] = mapped_column(String(20), nullable=False)
    to_status: Mapped[str] = mapped_column(String(20), nullable=False)
    event: Mapped[str] = mapped_column(String(30), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_role: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)