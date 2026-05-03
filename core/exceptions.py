class TradingError(Exception):
    """売買関連エラーの基底クラス"""


class InsufficientFundsError(TradingError):
    """残高不足"""


class InsufficientSharesError(TradingError):
    """保有数不足"""


class StockNotFoundError(TradingError):
    """銘柄が見つからない"""


class PriceNotAvailableError(TradingError):
    """株価取得失敗"""
