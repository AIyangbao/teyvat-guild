from datetime import datetime
from decimal import Decimal
from sqlalchemy import JSON, BigInteger, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.core.time_utils import utcnow
from app.db import Base

class Payment(Base):
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commission_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    out_trade_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False) # 幂等键
    amount: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="mock")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    callback_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    