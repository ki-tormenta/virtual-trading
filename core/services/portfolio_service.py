import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta

from core.auth import get_current_user_id
from core.models.position import Position
from core.models.snapshot import DailySnapshot
from core.models.transaction import Transaction
from core.repositories.account_repo import AccountRepo
from core.repositories.position_repo import PositionRepo
from core.repositories.snapshot_repo import SnapshotRepo
from core.repositories.stock_repo import StockRepo
from core.repositories.transaction_repo import TransactionRepo
from core.services.price_service import PriceService
from infrastructure.db.connection import SessionLocal


@dataclass
class PortfolioSummary:
    current_cash: float
    market_value: float
    total_assets: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    total_pnl_rate: float
    initial_cash: float
    jp_market_value: float
    us_market_value: float
    total_fee: float
    total_tax: float


@dataclass
class PositionSummary:
    ticker: str
    name: str
    market: str
    quantity: int
    avg_buy_price: float
    current_price: float
    market_value: float        # ネイティブ通貨（JP→円、US→ドル）
    unrealized_pnl: float      # ネイティブ通貨
    unrealized_pnl_rate: float
    market_value_jpy: float    # 円換算（JPはそのまま、USはUSDJPY換算）
    unrealized_pnl_jpy: float  # 円換算


@dataclass
class TransactionRecord:
    id: int
    ticker: str
    stock_name: str
    market: str
    type: str
    quantity: int
    price: float
    total_amount: float
    fee: float
    tax: float
    realized_pnl: float | None
    transaction_date: date
    memo: str | None
    tags: str | None


@dataclass
class SnapshotRecord:
    date: date
    cash: float
    market_value: float
    total_assets: float
    jp_market_value: float
    us_market_value: float


class PortfolioService:
    """損益計算・スナップショット管理を担当するサービス。"""

    def __init__(self, account_type: str = "real", scenario_name: str | None = None) -> None:
        self._price_service = PriceService()
        self._account_type = account_type
        self._scenario_name = scenario_name

    def _get_account(self, session):
        from config.settings import settings as _s
        user_id = get_current_user_id()
        repo = AccountRepo(session)
        if self._account_type == "simulation":
            name = self._scenario_name or "シナリオ1"
            return repo.get_or_create_simulation_account(user_id, _s.INITIAL_CASH, name)
        return repo.get_main_account(user_id)

    def get_summary(self) -> PortfolioSummary:
        """ポートフォリオのサマリーを計算して返す。"""
        user_id = get_current_user_id()

        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                raise RuntimeError("口座が見つかりません")
            tx_repo = TransactionRepo(session)
            positions = PositionRepo(session).get_all_by_account(user_id, account.id)
            realized_pnl = tx_repo.get_realized_pnl_sum(user_id, account.id)
            total_fee = tx_repo.get_fee_sum(user_id, account.id)
            total_tax = tx_repo.get_tax_sum(user_id, account.id)
            current_cash = account.current_cash
            initial_cash = account.initial_cash
            pos_data = [(p.ticker, p.quantity, p.avg_buy_price) for p in positions]

        has_us = any(not t.endswith(".T") for t, _, _ in pos_data)
        usd_jpy = self._price_service.get_usd_jpy_rate() if has_us else 1.0

        market_value_jpy = 0.0
        jp_market_value = 0.0
        us_market_value_jpy = 0.0
        unrealized_pnl_jpy = 0.0

        for ticker, quantity, avg_price in pos_data:
            current_price = self._price_service.get_close_price(ticker)
            value = current_price * quantity
            pnl = (current_price - avg_price) * quantity
            if ticker.endswith(".T"):
                market_value_jpy += value
                jp_market_value += value
                unrealized_pnl_jpy += pnl
            else:
                market_value_jpy += value * usd_jpy
                us_market_value_jpy += value * usd_jpy
                unrealized_pnl_jpy += pnl * usd_jpy

        total_assets = current_cash + market_value_jpy
        total_pnl = total_assets - initial_cash
        total_pnl_rate = total_pnl / initial_cash * 100 if initial_cash > 0 else 0.0

        return PortfolioSummary(
            current_cash=current_cash,
            market_value=market_value_jpy,
            total_assets=total_assets,
            unrealized_pnl=unrealized_pnl_jpy,
            realized_pnl=realized_pnl,
            total_pnl=total_pnl,
            total_pnl_rate=total_pnl_rate,
            initial_cash=initial_cash,
            jp_market_value=jp_market_value,
            us_market_value=us_market_value_jpy,
            total_fee=total_fee,
            total_tax=total_tax,
        )

    def get_positions(self) -> list[PositionSummary]:
        """全ポジションのサマリーリストを返す。"""
        user_id = get_current_user_id()

        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                return []
            positions = PositionRepo(session).get_all_by_account(user_id, account.id)
            tickers = [pos.ticker for pos in positions]
            stock_map = {s.ticker: s for s in StockRepo(session).get_by_tickers(tickers)}
            pos_data = []
            for pos in positions:
                stock = stock_map.get(pos.ticker)
                pos_data.append((
                    pos.ticker,
                    stock.name if stock else pos.ticker,
                    stock.market if stock else ("JP" if pos.ticker.endswith(".T") else "US"),
                    pos.quantity,
                    pos.avg_buy_price,
                ))

        has_us = any(m == "US" for _, _, m, _, _ in pos_data)
        usd_jpy = self._price_service.get_usd_jpy_rate() if has_us else 1.0

        result = []
        for ticker, name, market, quantity, avg_price in pos_data:
            current_price = self._price_service.get_close_price(ticker)
            market_value = current_price * quantity
            unrealized_pnl = (current_price - avg_price) * quantity
            pnl_rate = (current_price - avg_price) / avg_price * 100 if avg_price > 0 else 0.0
            rate = usd_jpy if market == "US" else 1.0
            result.append(PositionSummary(
                ticker=ticker,
                name=name,
                market=market,
                quantity=quantity,
                avg_buy_price=avg_price,
                current_price=current_price,
                market_value=market_value,
                unrealized_pnl=unrealized_pnl,
                unrealized_pnl_rate=pnl_rate,
                market_value_jpy=market_value * rate,
                unrealized_pnl_jpy=unrealized_pnl * rate,
            ))
        return result

    def get_transaction_records(
        self,
        ticker: str | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
        trade_type: str | None = None,
        tag: str | None = None,
    ) -> list[TransactionRecord]:
        """取引履歴を返す。"""
        user_id = get_current_user_id()
        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                return []
            txs = TransactionRepo(session).get_by_account(
                user_id, account.id,
                ticker=ticker,
                from_date=from_date,
                to_date=to_date,
                trade_type=trade_type,
                tag=tag,
            )
            result = []
            for tx in txs:
                stock = StockRepo(session).get_by_ticker(tx.ticker)
                name = stock.name if stock else tx.ticker
                market = stock.market if stock else ("JP" if tx.ticker.endswith(".T") else "US")
                result.append(TransactionRecord(
                    id=tx.id,
                    ticker=tx.ticker,
                    stock_name=name,
                    market=market,
                    type=tx.type,
                    quantity=tx.quantity,
                    price=tx.price,
                    total_amount=tx.total_amount,
                    fee=tx.fee or 0.0,
                    tax=tx.tax or 0.0,
                    realized_pnl=tx.realized_pnl,
                    transaction_date=tx.transaction_date,
                    memo=tx.memo,
                    tags=tx.tags,
                ))
            return result

    def get_snapshot_history(
        self,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[SnapshotRecord]:
        """スナップショット履歴を返す。"""
        user_id = get_current_user_id()
        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                return []
            snapshots = SnapshotRepo(session).get_history(
                user_id, account.id, from_date=from_date, to_date=to_date
            )
            return [
                SnapshotRecord(
                    date=s.date,
                    cash=s.cash,
                    market_value=s.market_value,
                    total_assets=s.total_assets,
                    jp_market_value=s.jp_market_value,
                    us_market_value=s.us_market_value,
                )
                for s in snapshots
            ]

    def get_all_tags(self) -> list[str]:
        """全取引で使用されたタグを昇順で返す。"""
        user_id = get_current_user_id()
        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                return []
            return TransactionRepo(session).get_all_tags(user_id, account.id)

    def get_tickers_with_tag(self, tag: str) -> set[str]:
        """指定タグが付いた取引のティッカー集合を返す。"""
        user_id = get_current_user_id()
        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                return set()
            return TransactionRepo(session).get_tickers_with_tag(user_id, account.id, tag)

    def update_transaction_memo(self, transaction_id: int, memo: str | None) -> None:
        """取引のメモを更新する。"""
        with SessionLocal() as session:
            TransactionRepo(session).update_memo(transaction_id, memo)
            session.commit()

    def get_simulation_scenarios(self) -> list[str]:
        """ユーザーの全シミュレーションシナリオ名を返す。"""
        user_id = get_current_user_id()
        with SessionLocal() as session:
            accounts = AccountRepo(session).get_simulation_accounts(user_id)
            return [a.name for a in accounts]

    def create_simulation_scenario(self, scenario_name: str) -> None:
        """シミュレーションシナリオ（口座）を作成してコミットする。

        Raises:
            RuntimeError: 上限4つに達している場合
        """
        from config.settings import settings as _s
        user_id = get_current_user_id()
        with SessionLocal() as session:
            AccountRepo(session).get_or_create_simulation_account(
                user_id, _s.INITIAL_CASH, scenario_name
            )
            session.commit()

    def take_all_simulation_snapshots(self) -> None:
        """全シミュレーションシナリオのスナップショットを取得する。"""
        user_id = get_current_user_id()
        with SessionLocal() as session:
            names = [a.name for a in AccountRepo(session).get_simulation_accounts(user_id)]
        for name in names:
            try:
                PortfolioService(account_type="simulation", scenario_name=name).take_snapshot()
            except Exception:
                pass

    def reset_portfolio(self) -> None:
        """全取引・ポジション・スナップショットを削除し、現金残高を初期値に戻す。"""
        from sqlalchemy import delete as sa_delete

        user_id = get_current_user_id()
        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                return
            session.execute(sa_delete(Transaction).where(Transaction.account_id == account.id))
            session.execute(sa_delete(Position).where(Position.account_id == account.id))
            session.execute(sa_delete(DailySnapshot).where(DailySnapshot.account_id == account.id))
            account.current_cash = account.initial_cash
            session.commit()

    def export_transactions_csv(self) -> str:
        """全取引履歴を CSV 文字列で返す。"""
        records = self.get_transaction_records()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "日付", "種別", "銘柄名", "ティッカー", "市場",
            "数量", "価格（現地通貨）", "合計金額（現地通貨）", "手数料(円)", "税金(円)", "実現損益(円)", "メモ", "タグ",
        ])
        for r in records:
            writer.writerow([
                r.transaction_date.strftime("%Y-%m-%d"),
                r.type,
                r.stock_name,
                r.ticker,
                r.market,
                r.quantity,
                r.price,
                r.total_amount,
                r.fee if r.fee else "",
                r.tax if r.tax else "",
                r.realized_pnl if r.realized_pnl is not None else "",
                r.memo or "",
                r.tags or "",
            ])
        return output.getvalue()

    _MAX_BACKFILL_DAYS = 30

    def take_snapshot(self, snapshot_date: date | None = None) -> None:
        """スナップショットを作成する。前回から今日まで欠けた日をバックフィルする。

        最大 _MAX_BACKFILL_DAYS 日分まで遡って補完する。
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        user_id = get_current_user_id()

        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                return
            latest = SnapshotRepo(session).get_latest(user_id, account.id)

        fill_from = (latest.date + timedelta(days=1)) if latest else snapshot_date
        dates_to_fill: list[date] = []
        d = fill_from
        while d <= snapshot_date:
            dates_to_fill.append(d)
            d += timedelta(days=1)

        # 上限を超えた場合は直近 _MAX_BACKFILL_DAYS 日だけ処理
        if len(dates_to_fill) > self._MAX_BACKFILL_DAYS:
            dates_to_fill = dates_to_fill[-self._MAX_BACKFILL_DAYS:]

        for fill_date in dates_to_fill:
            try:
                self._take_snapshot_at(fill_date)
            except Exception:
                pass  # 1日失敗しても残りの日を続ける

    def _take_snapshot_at(self, snap_date: date) -> None:
        """指定日時点の取引履歴からポートフォリオ状態を再構築してスナップショットを保存する。"""
        user_id = get_current_user_id()

        with SessionLocal() as session:
            account = self._get_account(session)
            if account is None:
                return
            txs = TransactionRepo(session).get_by_account(
                user_id, account.id, to_date=snap_date
            )
            initial_cash = account.initial_cash

        # 現金残高を再構築
        cash = initial_cash
        for tx in txs:
            if tx.type == "BUY":
                cash -= tx.total_amount + (tx.fee or 0.0)
            else:
                cash += tx.total_amount - (tx.fee or 0.0) - (tx.tax or 0.0)

        # ポジションを再構築（ticker → (quantity, avg_price)）
        positions: dict[str, tuple[int, float]] = {}
        for tx in sorted(txs, key=lambda x: (x.transaction_date, x.created_at)):
            if tx.type == "BUY":
                if tx.ticker in positions:
                    qty, avg = positions[tx.ticker]
                    new_qty = qty + tx.quantity
                    positions[tx.ticker] = (new_qty, (qty * avg + tx.quantity * tx.price) / new_qty)
                else:
                    positions[tx.ticker] = (tx.quantity, tx.price)
            else:
                qty, avg = positions.get(tx.ticker, (0, 0.0))
                new_qty = qty - tx.quantity
                if new_qty <= 0:
                    positions.pop(tx.ticker, None)
                else:
                    positions[tx.ticker] = (new_qty, avg)

        # 評価額を計算
        has_us = any(not t.endswith(".T") for t in positions)
        usd_jpy = self._price_service.get_usd_jpy_rate() if has_us else 1.0

        jp_market_value = 0.0
        us_market_value = 0.0
        for ticker, (quantity, _) in positions.items():
            try:
                price = self._price_service.get_close_price(ticker, snap_date)
                value = price * quantity
                if ticker.endswith(".T"):
                    jp_market_value += value
                else:
                    us_market_value += value * usd_jpy
            except Exception:
                pass

        market_value = jp_market_value + us_market_value

        with SessionLocal() as session:
            snap = DailySnapshot(
                user_id=user_id,
                account_id=account.id,
                date=snap_date,
                cash=cash,
                market_value=market_value,
                total_assets=cash + market_value,
                jp_market_value=jp_market_value,
                us_market_value=us_market_value,
            )
            SnapshotRepo(session).upsert(snap)
            session.commit()
