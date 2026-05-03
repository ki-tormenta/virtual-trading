from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.models.base import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("accounts.id"), nullable=False)
    ticker: Mapped[str] = mapped_column(String, ForeignKey("stocks.ticker"), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)  # 'BUY' or 'SELL'
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    fee: Mapped[float] = mapped_column(Float, default=0)   # Phase 2
    tax: Mapped[float] = mapped_column(Float, default=0)   # Phase 2
    realized_pnl: Mapped[float | None] = mapped_column(Float)  # 売却時のみ
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    memo: Mapped[str | None] = mapped_column(String)
    tags: Mapped[str | None] = mapped_column(String)  # カンマ区切り
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("type IN ('BUY', 'SELL')", name="chk_transaction_type"),
        Index("idx_transactions_user", "user_id"),
        Index("idx_transactions_account", "account_id"),
    )
