from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models.position import Position


class PositionRepo:
    """ポジションリポジトリ。CRUD操作のみ担当。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: int, account_id: int, ticker: str) -> Position | None:
        """指定ポジションを取得する。"""
        return self._session.get(Position, (user_id, account_id, ticker))

    def get_all_by_account(self, user_id: int, account_id: int) -> list[Position]:
        """口座の全ポジションを取得する。"""
        stmt = select(Position).where(
            Position.user_id == user_id,
            Position.account_id == account_id,
        )
        return list(self._session.execute(stmt).scalars())

    def upsert(self, position: Position) -> Position:
        """ポジションを追加または更新する。"""
        existing = self._session.get(
            Position, (position.user_id, position.account_id, position.ticker)
        )
        if existing is None:
            self._session.add(position)
            return position
        existing.quantity = position.quantity
        existing.avg_buy_price = position.avg_buy_price
        return existing

    def delete(self, user_id: int, account_id: int, ticker: str) -> None:
        """ポジションを削除する（全売却時）。"""
        position = self._session.get(Position, (user_id, account_id, ticker))
        if position is not None:
            self._session.delete(position)
