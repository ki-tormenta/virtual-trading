import time
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd
import yfinance as yf

from config.settings import settings
from core.exceptions import PriceNotAvailableError, StockNotFoundError
from infrastructure.data_sources.base import PriceDataSource


class YfinanceSource(PriceDataSource):
    """yfinanceを使った株価データソース実装。"""

    def get_close_price(self, ticker: str, target_date: date | None = None) -> float:
        """指定日の終値を取得する。

        Args:
            ticker: 銘柄ティッカー
            target_date: 取得対象日。Noneなら最新営業日

        Returns:
            終値

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
            PriceNotAvailableError: 株価取得に失敗した場合
        """

        def _fetch() -> float:
            if target_date is None:
                df = yf.Ticker(ticker).history(period="5d")
            else:
                start = (target_date - timedelta(days=7)).isoformat()
                end = (target_date + timedelta(days=1)).isoformat()
                df = yf.Ticker(ticker).history(start=start, end=end)

            if df.empty:
                raise StockNotFoundError(f"価格データが見つかりません: {ticker}")

            df = self._normalize_index(df)

            if target_date is None:
                return float(df["Close"].iloc[-1])

            target_ts = pd.Timestamp(target_date)
            available = df[df.index <= target_ts]
            if available.empty:
                raise PriceNotAvailableError(
                    f"指定日以前の価格データがありません: {ticker} {target_date}"
                )
            return float(available["Close"].iloc[-1])

        return self._with_retry(_fetch, ticker)

    def get_price_history(
        self, ticker: str, period: str = "1y", include_ohlcv: bool = False
    ) -> pd.DataFrame:
        """株価履歴を取得する。

        Args:
            ticker: 銘柄ティッカー
            period: 取得期間 (例: '1mo', '3mo', '6mo', '1y', '2y', 'max')
            include_ohlcv: TrueのときOpen/High/Low/Close全列を返す

        Returns:
            日付インデックスのDataFrame（Close列を必ず含む）

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
            PriceNotAvailableError: 株価取得に失敗した場合
        """

        def _fetch() -> pd.DataFrame:
            df = yf.Ticker(ticker).history(period=period)
            if df.empty:
                raise StockNotFoundError(f"価格データが見つかりません: {ticker}")
            df = self._normalize_index(df)
            if include_ohlcv:
                cols = [c for c in ["Open", "High", "Low", "Close"] if c in df.columns]
                return df[cols].copy()
            return df[["Close"]].copy()

        return self._with_retry(_fetch, ticker)

    def get_stock_info(self, ticker: str) -> dict:
        """銘柄情報を取得する。

        Args:
            ticker: 銘柄ティッカー

        Returns:
            longName, shortName, sector等を含む辞書

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
        """

        def _fetch() -> dict:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info
            name = info.get("longName") or info.get("shortName") or info.get("displayName")
            if not name:
                # fast_info は軽量APIなので info 失敗時のフォールバックに使う
                try:
                    fi = ticker_obj.fast_info
                    name = getattr(fi, "display_name", None)
                except Exception:
                    pass
            if not name:
                raise StockNotFoundError(f"銘柄が見つかりません: {ticker}")
            if not info.get("longName") and not info.get("shortName"):
                info = dict(info)
                info["longName"] = name
            return info

        return self._with_retry(_fetch, ticker)

    def _normalize_index(self, df: pd.DataFrame) -> pd.DataFrame:
        """DataFrameのインデックスをタイムゾーンなしのDatetimeIndexに正規化する。"""
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df = df.copy()
            df.index = df.index.tz_convert(None)
        df.index = df.index.normalize()
        return df

    def _with_retry(self, func: Callable[[], Any], ticker: str) -> Any:
        """リトライ付きで関数を実行する。StockNotFoundErrorはリトライせず即再送出。

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
            PriceNotAvailableError: リトライ上限に達した場合
        """
        last_exc: Exception = RuntimeError("unknown")
        for attempt in range(settings.PRICE_FETCH_RETRY_MAX):
            try:
                return func()
            except (StockNotFoundError, PriceNotAvailableError):
                raise
            except Exception as e:
                last_exc = e
                if attempt < settings.PRICE_FETCH_RETRY_MAX - 1:
                    time.sleep(settings.PRICE_FETCH_RETRY_BACKOFF**attempt)
        raise PriceNotAvailableError(f"株価取得失敗（リトライ上限）: {ticker}") from last_exc
