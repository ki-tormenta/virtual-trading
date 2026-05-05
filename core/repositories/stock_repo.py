from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models.stock import Stock


class StockRepo:
    """銘柄マスタのリポジトリ。CRUD操作のみ担当。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_ticker(self, ticker: str) -> Stock | None:
        """tickerで銘柄を取得する。"""
        return self._session.get(Stock, ticker)

    def get_by_tickers(self, tickers: list[str]) -> list[Stock]:
        """複数tickerを1クエリで一括取得する。"""
        if not tickers:
            return []
        stmt = select(Stock).where(Stock.ticker.in_(tickers))
        return list(self._session.execute(stmt).scalars())

    def get_by_code(self, code: str) -> Stock | None:
        """証券コードで銘柄を取得する。"""
        stmt = select(Stock).where(Stock.code == code)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_all(self) -> list[Stock]:
        """全銘柄を取得する。"""
        return list(self._session.execute(select(Stock)).scalars())

    def upsert(self, stock: Stock) -> Stock:
        """銘柄を追加または更新する。"""
        existing = self._session.get(Stock, stock.ticker)
        if existing is None:
            self._session.add(stock)
            return stock
        existing.name = stock.name
        existing.sector = stock.sector
        existing.market = stock.market
        return existing

    def exists(self, ticker: str) -> bool:
        """銘柄が存在するか確認する。"""
        return self._session.get(Stock, ticker) is not None
