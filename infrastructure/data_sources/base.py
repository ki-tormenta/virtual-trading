from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class PriceDataSource(ABC):
    """株価データソースの抽象クラス。異なるデータプロバイダへの切替を可能にする。"""

    @abstractmethod
    def get_close_price(self, ticker: str, target_date: date | None = None) -> float:
        """指定日の終値を取得する。target_dateがNoneの場合は最新営業日の終値。

        Args:
            ticker: 銘柄ティッカー
            target_date: 取得対象日。Noneなら最新営業日

        Returns:
            終値

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
            PriceNotAvailableError: 株価取得に失敗した場合
        """

    @abstractmethod
    def get_price_history(self, ticker: str, period: str = "1y") -> pd.DataFrame:
        """株価履歴を取得する。

        Args:
            ticker: 銘柄ティッカー
            period: 取得期間 (例: '1mo', '3mo', '6mo', '1y', '2y', 'max')

        Returns:
            日付インデックス、'Close'列を含むDataFrame

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
            PriceNotAvailableError: 株価取得に失敗した場合
        """

    @abstractmethod
    def get_stock_info(self, ticker: str) -> dict:
        """銘柄情報を取得する。

        Args:
            ticker: 銘柄ティッカー

        Returns:
            longName, shortName, sector等を含む辞書

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
        """
