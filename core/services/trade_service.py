from datetime import date

from core.auth import get_current_user_id
from core.exceptions import InsufficientFundsError, InsufficientSharesError, StockNotFoundError
from core.models.position import Position
from core.models.transaction import Transaction
from core.repositories.account_repo import AccountRepo
from core.repositories.position_repo import PositionRepo
from core.repositories.transaction_repo import TransactionRepo
from core.services.price_service import PriceService
from infrastructure.db.connection import SessionLocal

# 米国株手数料: 約定代金の 0.495%、上限 22 ドル（SBI証券スタイル）
_US_FEE_RATE = 0.00495
_US_FEE_CAP_USD = 22.0

# 譲渡所得税率（所得税 + 復興特別所得税 + 住民税）
_TAX_RATE = 0.20315


def normalize_ticker(code: str) -> str:
    """銘柄コードをtickerに変換する。

    Args:
        code: ユーザー入力の証券コード（例: '6501', 'AAPL'）

    Returns:
        tickerシンボル（例: '6501.T', 'AAPL'）
    """
    code = code.strip().upper()
    if code.isdigit() and len(code) == 4:
        return f"{code}.T"
    return code


def _calc_fee_jpy(is_us: bool, total_native: float, usd_jpy: float) -> float:
    """手数料を円で返す。日本株は0円、米国株は約定代金の0.495%（上限22ドル）→ JPY換算。"""
    if not is_us:
        return 0.0
    fee_usd = min(total_native * _US_FEE_RATE, _US_FEE_CAP_USD)
    return fee_usd * usd_jpy


def _append_tag(existing: str | None, new_tag: str) -> str:
    """既存タグ文字列に新しいタグを追加する。"""
    return f"{existing},{new_tag}" if existing else new_tag


class TradeService:
    """売買ロジックを担当するサービス。"""

    def __init__(self) -> None:
        self._price_service = PriceService()

    def buy(
        self,
        ticker: str,
        quantity: int,
        memo: str | None = None,
        tags: str | None = None,
        trade_date: date | None = None,
    ) -> list[Transaction]:
        """銘柄を買付する。日本株は100株単位で分割し、端数はS株タグを付ける。

        Args:
            ticker: 銘柄ティッカー
            quantity: 購入数量
            memo: メモ
            tags: タグ（カンマ区切り）
            trade_date: 売買日。Noneなら当日

        Returns:
            作成されたTransactionのリスト（S株分割時は2件）

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
            InsufficientFundsError: 残高不足の場合
        """
        if trade_date is None:
            trade_date = date.today()

        self._price_service.get_or_register_stock(ticker)

        is_jp = ticker.endswith(".T")
        is_us = not is_jp

        # S株分割（日本株のみ）
        lot_qty = (quantity // 100) * 100 if is_jp else quantity
        sunit_qty = (quantity % 100) if is_jp else 0

        price = self._price_service.get_close_price(ticker, trade_date)
        total_amount = price * quantity          # ネイティブ通貨
        usd_jpy = self._price_service.get_usd_jpy_rate() if is_us else 1.0
        total_amount_jpy = total_amount * usd_jpy
        fee_jpy = _calc_fee_jpy(is_us, total_amount, usd_jpy)
        total_cost_jpy = total_amount_jpy + fee_jpy

        user_id = get_current_user_id()

        with SessionLocal() as session:
            account_repo = AccountRepo(session)
            position_repo = PositionRepo(session)
            tx_repo = TransactionRepo(session)

            account = account_repo.get_main_account(user_id)
            if account is None:
                raise StockNotFoundError("口座が見つかりません")

            if account.current_cash < total_cost_jpy:
                raise InsufficientFundsError(
                    f"残高不足: 必要額 {total_cost_jpy:,.0f}円（手数料含む）、"
                    f"残高 {account.current_cash:,.0f}円"
                )

            # ポジション更新（合計数量で加重平均を再計算）
            position = position_repo.get(user_id, account.id, ticker)
            if position is None:
                position_repo.upsert(Position(
                    user_id=user_id,
                    account_id=account.id,
                    ticker=ticker,
                    quantity=quantity,
                    avg_buy_price=price,
                ))
            else:
                total_qty = position.quantity + quantity
                new_avg = (
                    position.quantity * position.avg_buy_price + quantity * price
                ) / total_qty
                position.quantity = total_qty
                position.avg_buy_price = new_avg

            # トランザクション作成（S株分割あり）
            txs: list[Transaction] = []

            if lot_qty > 0:
                txs.append(Transaction(
                    user_id=user_id,
                    account_id=account.id,
                    ticker=ticker,
                    type="BUY",
                    quantity=lot_qty,
                    price=price,
                    total_amount=price * lot_qty,
                    fee=fee_jpy,   # 手数料は通常株側に記録（JP=0、US=全額）
                    transaction_date=trade_date,
                    memo=memo,
                    tags=tags,
                ))

            if sunit_qty > 0:
                txs.append(Transaction(
                    user_id=user_id,
                    account_id=account.id,
                    ticker=ticker,
                    type="BUY",
                    quantity=sunit_qty,
                    price=price,
                    total_amount=price * sunit_qty,
                    fee=0.0,
                    transaction_date=trade_date,
                    memo=memo,
                    tags=_append_tag(tags, "S株"),
                ))

            for tx in txs:
                tx_repo.add(tx)

            account_repo.update_cash(account.id, account.current_cash - total_cost_jpy)

            session.commit()
            for tx in txs:
                session.refresh(tx)
            return txs

    def sell(
        self,
        ticker: str,
        quantity: int,
        memo: str | None = None,
        tags: str | None = None,
        trade_date: date | None = None,
    ) -> Transaction:
        """銘柄を売却する。手数料・税金を差し引いた手取り額を現金に加算する。

        Args:
            ticker: 銘柄ティッカー
            quantity: 売却数量
            memo: メモ
            tags: タグ（カンマ区切り）
            trade_date: 売買日。Noneなら当日

        Returns:
            作成されたTransactionオブジェクト

        Raises:
            StockNotFoundError: 銘柄が見つからない場合
            InsufficientSharesError: 保有数不足の場合
        """
        if trade_date is None:
            trade_date = date.today()

        is_jp = ticker.endswith(".T")
        is_us = not is_jp

        price = self._price_service.get_close_price(ticker, trade_date)
        total_amount = price * quantity          # ネイティブ通貨
        usd_jpy = self._price_service.get_usd_jpy_rate() if is_us else 1.0
        total_amount_jpy = total_amount * usd_jpy
        fee_jpy = _calc_fee_jpy(is_us, total_amount, usd_jpy)

        user_id = get_current_user_id()

        with SessionLocal() as session:
            account_repo = AccountRepo(session)
            position_repo = PositionRepo(session)
            tx_repo = TransactionRepo(session)

            account = account_repo.get_main_account(user_id)
            if account is None:
                raise StockNotFoundError("口座が見つかりません")

            position = position_repo.get(user_id, account.id, ticker)
            if position is None or position.quantity < quantity:
                held = position.quantity if position else 0
                raise InsufficientSharesError(
                    f"保有数不足: 売却希望 {quantity}株、保有 {held}株"
                )

            # 実現損益（円換算・グロス）
            realized_pnl = (price - position.avg_buy_price) * quantity * usd_jpy

            # 譲渡所得税（利益のみ課税）
            tax = max(0.0, realized_pnl) * _TAX_RATE

            # 手取り = 売却代金 - 手数料 - 税金
            net_proceeds_jpy = total_amount_jpy - fee_jpy - tax

            # ポジション更新（avg_buy_priceは売却時不変）
            new_qty = position.quantity - quantity
            if new_qty == 0:
                position_repo.delete(user_id, account.id, ticker)
            else:
                position.quantity = new_qty

            tx = Transaction(
                user_id=user_id,
                account_id=account.id,
                ticker=ticker,
                type="SELL",
                quantity=quantity,
                price=price,
                total_amount=total_amount,
                fee=fee_jpy,
                tax=tax,
                realized_pnl=realized_pnl,
                transaction_date=trade_date,
                memo=memo,
                tags=tags,
            )
            tx_repo.add(tx)

            account_repo.update_cash(account.id, account.current_cash + net_proceeds_jpy)

            session.commit()
            session.refresh(tx)
            return tx
