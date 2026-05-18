from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = {"extend_existing": True}

    ticker: Mapped[str] = mapped_column(String, ForeignKey("stocks.ticker"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    close_price: Mapped[float] = mapped_column(Float, nullable=False)
