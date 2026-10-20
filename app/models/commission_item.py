from decimal import Decimal
from sqlalchemy import BigInteger, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
# 价格快照
class CommissionItem(Base):
    __tablename__ = "commission_item"
    __table_args__ = (Index("idx_commission", "commission_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    commission_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    service_item_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot_name: Mapped[str] =  mapped_column(String(80), nullable=False)
    snapshot_price: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    