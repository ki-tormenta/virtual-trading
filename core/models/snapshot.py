from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class DailySnapshot(Base):
    __tablename__ = "daily_snapshots"
    __table_args__ = {"extend_existing": True}

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    cash: Mapped[float] = mapped_column(Float, nullable=False)
    market_value: Mapped[float] = mapped_column(Float, nullable=False)
    total_assets: Mapped[float] = mapped_column(Float, nullable=False)
    jp_market_value: Mapped[float] = mapped_column(Float, default=0)
    us_market_value: Mapped[float] = mapped_column(Float, default=0)
