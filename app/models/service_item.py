from datetime import datetime
from decimal import Decimal
from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String, Text,Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.time_utils import utcnow
from app.db import Base

class ServiceItem(Base):
    __tablename__ = "service_item"
    __table_args__ = (Index("idx_cat_status", "category_id", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description:Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    