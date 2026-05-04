from datetime import date

import pandas as pd

from core.models.price_history import PriceHistory
from core.models.stock import Stock
from core.repositories.stock_repo import StockRepo
from core.exceptions import PriceNotAvailableError, StockNotFoundError
from infrastructure.data_sources.yfinance_source import YfinanceSource
from infrastructure.db.connection import SessionLocal


class PriceService:
    """株価取得サービス。price_historyテーブルをキャッシュとして使う。"""

    def __init__(self) -> None:
        self._source = YfinanceSource()

    def get_close_price(self, ticker: str, target_date: date | None = None) -> float:
        """終値を取得する。DBキャッシュがあればそれを返し、なければyfinanceから取得してキャッシュする。

        Args:
            ticker: 銘柄ティッカー
            target_date: 取得対象日。Noneなら最新営業日

        Returns:
            終値

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
            PriceNotAvailableError: 株価取得に失敗した場合
        """
        if target_date is None:
            # 最新終値はキャッシュせず常に取得（当日の場合は変動しうる）
            return self._source.get_close_price(ticker)

        with SessionLocal() as session:
            cached = session.get(PriceHistory, (ticker, target_date))
            if cached is not None:
                return cached.close_price

            price = self._source.get_close_price(ticker, target_date)
            session.add(PriceHistory(ticker=ticker, date=target_date, close_price=price))
            session.commit()
            return price

    def get_usd_jpy_rate(self) -> float:
        """USD/JPY レートを取得する。取得失敗時は150.0を返す。

        Returns:
            1ドルあたりの円換算レート
        """
        try:
            return self._source.get_close_price("USDJPY=X")
        except Exception:
            return 150.0

    def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """株価履歴DataFrameを取得する。

        Args:
            ticker: 銘柄ティッカー
            period: 取得期間 (例: '1mo', '3mo', '6mo', '1y', '2y', 'max')

        Returns:
            日付インデックス、'Close'列を含むDataFrame
        """
        return self._source.get_price_history(ticker, period)

    def get_or_register_stock(self, ticker: str) -> Stock:
        """銘柄をDBから取得する。未登録の場合はyfinanceから情報を取得してDBに登録する。

        Args:
            ticker: 銘柄ティッカー

        Returns:
            Stockモデル

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
        """
        with SessionLocal() as session:
            repo = StockRepo(session)
            stock = repo.get_by_ticker(ticker)
            if stock is not None:
                return stock

            name = ticker
            sector = None
            try:
                info = self._source.get_stock_info(ticker)
                name = info.get("longName") or info.get("shortName") or ticker
                sector = info.get("sector")
            except StockNotFoundError:
                raise
            except PriceNotAvailableError:
                # .info 取得失敗（レート制限等）→ history() で存在確認してフォールバック登録
                self._source.get_close_price(ticker)  # 存在しなければここで StockNotFoundError

            market = "JP" if ticker.endswith(".T") else "US"
            code = ticker.replace(".T", "")

            stock = Stock(ticker=ticker, code=code, name=name, market=market, sector=sector)
            repo.upsert(stock)
            session.commit()
            session.refresh(stock)
            return stock
