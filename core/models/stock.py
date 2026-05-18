from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class Stock(Base):
    __tablename__ = "stocks"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    code: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    market: Mapped[str] = mapped_column(String, nullable=False)  # 'JP' or 'US'
    sector: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    __table_args__ = (Index("idx_stocks_code", "code"), {"extend_existing": True})
