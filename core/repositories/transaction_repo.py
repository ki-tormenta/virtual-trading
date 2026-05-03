from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models.transaction import Transaction


class TransactionRepo:
    """取引履歴リポジトリ。CRUD操作のみ担当。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, transaction: Transaction) -> Transaction:
        """取引を追加する。"""
        self._session.add(transaction)
        return transaction

    def get_by_account(
        self,
        user_id: int,
        account_id: int,
        ticker: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        trade_type: str | None = None,
        tag: str | None = None,
    ) -> list[Transaction]:
        """口座の取引履歴を取得する。各フィルタはAND条件。"""
        stmt = select(Transaction).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
        )
        if ticker is not None:
            stmt = stmt.where(Transaction.ticker == ticker)
        if from_date is not None:
            stmt = stmt.where(Transaction.transaction_date >= from_date)
        if to_date is not None:
            stmt = stmt.where(Transaction.transaction_date <= to_date)
        if trade_type is not None:
            stmt = stmt.where(Transaction.type == trade_type)
        stmt = stmt.order_by(Transaction.transaction_date.desc(), Transaction.created_at.desc())
        results = list(self._session.execute(stmt).scalars())
        if tag:
            results = [
                tx for tx in results
                if tx.tags and tag in [t.strip() for t in tx.tags.split(",")]
            ]
        return results

    def update_memo(self, transaction_id: int, memo: str | None) -> None:
        """取引のメモを更新する。"""
        tx = self._session.get(Transaction, transaction_id)
        if tx is not None:
            tx.memo = memo

    def get_all_tags(self, user_id: int, account_id: int) -> list[str]:
        """使用済みタグを昇順で返す。"""
        stmt = select(Transaction.tags).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
            Transaction.tags.isnot(None),
        )
        rows = list(self._session.execute(stmt).scalars())
        tags: set[str] = set()
        for row in rows:
            for t in row.split(","):
                t = t.strip()
                if t:
                    tags.add(t)
        return sorted(tags)

    def get_tickers_with_tag(self, user_id: int, account_id: int, tag: str) -> set[str]:
        """指定タグが付いた取引のティッカー集合を返す。"""
        stmt = select(Transaction.ticker, Transaction.tags).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
            Transaction.tags.isnot(None),
        )
        rows = list(self._session.execute(stmt).all())
        return {
            ticker for ticker, tags_str in rows
            if tags_str and tag in [t.strip() for t in tags_str.split(",")]
        }

    def get_realized_pnl_sum(self, user_id: int, account_id: int) -> float:
        """実現損益の累計を返す。"""
        from sqlalchemy import func

        stmt = select(func.sum(Transaction.realized_pnl)).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
            Transaction.type == "SELL",
        )
        result = self._session.execute(stmt).scalar()
        return float(result) if result is not None else 0.0

    def get_fee_sum(self, user_id: int, account_id: int) -> float:
        """累計手数料（円）を返す。"""
        from sqlalchemy import func

        stmt = select(func.sum(Transaction.fee)).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
        )
        result = self._session.execute(stmt).scalar()
        return float(result) if result is not None else 0.0

    def get_tax_sum(self, user_id: int, account_id: int) -> float:
        """累計税金（円）を返す。"""
        from sqlalchemy import func

        stmt = select(func.sum(Transaction.tax)).where(
            Transaction.user_id == user_id,
            Transaction.account_id == account_id,
            Transaction.type == "SELL",
        )
        result = self._session.execute(stmt).scalar()
        return float(result) if result is not None else 0.0
