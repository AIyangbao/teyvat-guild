from datetime import datetime
from decimal import Decimal
from sqlalchemy import BigInteger, DateTime, Integer, Numeric, String,Index
from sqlalchemy.orm import Mapped, mapped_column
from app.core.time_utils import utcnow
from app.db import Base

class Commission(Base):
    __tablename__ = "commission"
    __table_args__ = (
        Index("idx_hall","status", "created_at"), # 委托大厅
        Index("idx_player", "player_id", "created_at"), # 我的委托
        Index("idx_adventurer", "adventurer_id", "status"), # 冒险家在途单
        Index("idx_pay_timeout", "status", "pay_deadline"), # 关单扫描
        Index("idx_accept_timeout", "status", "accept_deadline"), # 自动验收扫描
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    player_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    adventurer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    game_uid: Mapped[str] = mapped_column(String(20), nullable=False)
    server: Mapped[str] = mapped_column(String(20), nullable=False)
    expect_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(10,2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="待支付")
    remark: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    pay_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accept_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pool_retry: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
