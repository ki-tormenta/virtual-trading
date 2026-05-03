"""TradeService の単体テスト（Phase 2 対応）。"""
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import InsufficientFundsError, InsufficientSharesError
from core.services.trade_service import TradeService, _US_FEE_RATE, _US_FEE_CAP_USD, _TAX_RATE


def _make_service(jp_price: float = 3000.0, us_price: float = 200.0, usd_jpy: float = 150.0) -> TradeService:
    service = TradeService()
    mock_p = MagicMock()
    mock_p.get_close_price.side_effect = lambda ticker, *_: us_price if not ticker.endswith(".T") else jp_price
    mock_p.get_usd_jpy_rate.return_value = usd_jpy
    mock_p.get_or_register_stock.return_value = MagicMock()
    service._price_service = mock_p
    return service


# ─────────────────────────── BUY 基本 ──────────────────────────────────────

class TestBuy:
    def test_returns_list(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            txs = _make_service().buy("7203.T", 100)
        assert isinstance(txs, list)
        assert len(txs) == 1

    def test_first_buy_sets_avg_price(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            txs = _make_service(jp_price=3000.0).buy("7203.T", 100)
        assert txs[0].price == 3000.0
        assert txs[0].total_amount == 300_000.0

    def test_second_buy_updates_weighted_avg_price(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            svc = _make_service(jp_price=3000.0)
            svc.buy("7203.T", 100)
            svc._price_service.get_close_price.side_effect = lambda t, *_: 3500.0
            svc.buy("7203.T", 100)
            with test_sessionmaker() as session:
                from core.repositories.position_repo import PositionRepo
                pos = PositionRepo(session).get(1, 1, "7203.T")
                assert pos.quantity == 200
                assert pos.avg_buy_price == pytest.approx(3250.0)

    def test_buy_deducts_jpy_from_cash(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            _make_service(jp_price=3000.0).buy("7203.T", 100)
            with test_sessionmaker() as session:
                from core.repositories.account_repo import AccountRepo
                assert AccountRepo(session).get_main_account(1).current_cash == pytest.approx(
                    10_000_000.0 - 300_000.0
                )

    def test_buy_us_deducts_jpy_equivalent(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            _make_service(us_price=200.0, usd_jpy=150.0).buy("AAPL", 10)
            expected = 200.0 * 10 * 150.0
            with test_sessionmaker() as session:
                from core.repositories.account_repo import AccountRepo
                assert AccountRepo(session).get_main_account(1).current_cash == pytest.approx(
                    10_000_000.0 - expected - min(200.0 * 10 * _US_FEE_RATE, _US_FEE_CAP_USD) * 150.0
                )

    def test_buy_raises_insufficient_funds(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            with pytest.raises(InsufficientFundsError):
                _make_service(jp_price=3000.0).buy("7203.T", 10_000)

    def test_buy_us_fee_included_in_cost(self, test_sessionmaker):
        """米国株は手数料込みで残高チェックされること。"""
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            svc = _make_service(us_price=1000.0, usd_jpy=150.0)
            # 1000 * 9 * 150 = 1,350,000; fee = min(9000 * 0.00495, 22) * 150 = 3,217.5
            svc.buy("AAPL", 9)
            with test_sessionmaker() as session:
                from core.repositories.account_repo import AccountRepo
                acc = AccountRepo(session).get_main_account(1)
                fee_jpy = min(1000.0 * 9 * _US_FEE_RATE, _US_FEE_CAP_USD) * 150.0
                assert acc.current_cash == pytest.approx(10_000_000.0 - 1_350_000.0 - fee_jpy)


# ─────────────────────────── S株分割 ────────────────────────────────────────

class TestSUnitSplit:
    def test_exact_lot_returns_one_transaction(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            txs = _make_service().buy("7203.T", 200)
        assert len(txs) == 1
        assert txs[0].quantity == 200
        assert txs[0].tags is None

    def test_sunit_only_returns_one_transaction_with_tag(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            txs = _make_service().buy("7203.T", 50)
        assert len(txs) == 1
        assert txs[0].quantity == 50
        assert "S株" in (txs[0].tags or "")

    def test_mixed_splits_into_two_transactions(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            txs = _make_service().buy("7203.T", 103)
        assert len(txs) == 2
        lot_tx, sunit_tx = txs
        assert lot_tx.quantity == 100
        assert sunit_tx.quantity == 3
        assert "S株" in (sunit_tx.tags or "")
        assert "S株" not in (lot_tx.tags or "")

    def test_split_appends_to_existing_tags(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            txs = _make_service().buy("7203.T", 103, tags="成長株")
        lot_tx, sunit_tx = txs
        assert lot_tx.tags == "成長株"
        assert sunit_tx.tags == "成長株,S株"

    def test_split_position_uses_total_quantity(self, test_sessionmaker):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            _make_service(jp_price=3000.0).buy("7203.T", 103)
            with test_sessionmaker() as session:
                from core.repositories.position_repo import PositionRepo
                pos = PositionRepo(session).get(1, 1, "7203.T")
                assert pos.quantity == 103

    def test_us_stock_no_split(self, test_sessionmaker):
        """米国株はS株分割なし。"""
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            txs = _make_service().buy("AAPL", 50)
        assert len(txs) == 1
        assert "S株" not in (txs[0].tags or "")


# ─────────────────────────── SELL ──────────────────────────────────────────

class TestSell:
    def _setup_position(self, test_sessionmaker, ticker, qty, price, usd_jpy=150.0):
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            _make_service(jp_price=price, us_price=price, usd_jpy=usd_jpy).buy(ticker, qty)

    def test_sell_jp_realized_pnl(self, test_sessionmaker):
        self._setup_position(test_sessionmaker, "7203.T", 100, 3000.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            svc = _make_service(jp_price=3500.0)
            tx = svc.sell("7203.T", 100)
        assert tx.realized_pnl == pytest.approx((3500.0 - 3000.0) * 100)

    def test_sell_us_realized_pnl_in_jpy(self, test_sessionmaker):
        self._setup_position(test_sessionmaker, "AAPL", 10, 200.0, usd_jpy=150.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            svc = _make_service(us_price=250.0, usd_jpy=150.0)
            tx = svc.sell("AAPL", 10)
        assert tx.realized_pnl == pytest.approx((250.0 - 200.0) * 10 * 150.0)

    def test_sell_tax_applied_on_profit(self, test_sessionmaker):
        """利益確定時に tax = realized_pnl × 20.315% が記録されること。"""
        self._setup_position(test_sessionmaker, "7203.T", 100, 3000.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            tx = _make_service(jp_price=3500.0).sell("7203.T", 100)
        expected_pnl = (3500.0 - 3000.0) * 100
        assert tx.tax == pytest.approx(expected_pnl * _TAX_RATE)

    def test_sell_no_tax_on_loss(self, test_sessionmaker):
        """損失確定時は tax = 0 になること。"""
        self._setup_position(test_sessionmaker, "7203.T", 100, 3000.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            tx = _make_service(jp_price=2500.0).sell("7203.T", 100)
        assert tx.tax == pytest.approx(0.0)

    def test_sell_jp_fee_is_zero(self, test_sessionmaker):
        self._setup_position(test_sessionmaker, "7203.T", 100, 3000.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            tx = _make_service(jp_price=3500.0).sell("7203.T", 100)
        assert tx.fee == pytest.approx(0.0)

    def test_sell_us_fee_applied(self, test_sessionmaker):
        self._setup_position(test_sessionmaker, "AAPL", 10, 200.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            tx = _make_service(us_price=200.0, usd_jpy=150.0).sell("AAPL", 10)
        expected_fee = min(200.0 * 10 * _US_FEE_RATE, _US_FEE_CAP_USD) * 150.0
        assert tx.fee == pytest.approx(expected_fee)

    def test_sell_cash_net_of_fee_and_tax(self, test_sessionmaker):
        """現金への加算が (売却代金 - 手数料 - 税金) になること。"""
        self._setup_position(test_sessionmaker, "7203.T", 100, 3000.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            tx = _make_service(jp_price=3500.0).sell("7203.T", 100)
            with test_sessionmaker() as session:
                from core.repositories.account_repo import AccountRepo
                cash = AccountRepo(session).get_main_account(1).current_cash
        net = tx.total_amount - tx.fee - tx.tax
        assert cash == pytest.approx(10_000_000.0 - 300_000.0 + net)

    def test_sell_raises_insufficient_shares(self, test_sessionmaker):
        self._setup_position(test_sessionmaker, "7203.T", 50, 3000.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            with pytest.raises(InsufficientSharesError):
                _make_service(jp_price=3000.0).sell("7203.T", 100)

    def test_full_sell_deletes_position(self, test_sessionmaker):
        self._setup_position(test_sessionmaker, "7203.T", 100, 3000.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            _make_service(jp_price=3200.0).sell("7203.T", 100)
            with test_sessionmaker() as session:
                from core.repositories.position_repo import PositionRepo
                assert PositionRepo(session).get(1, 1, "7203.T") is None

    def test_partial_sell_keeps_avg_price(self, test_sessionmaker):
        self._setup_position(test_sessionmaker, "7203.T", 100, 3000.0)
        with patch("core.services.trade_service.SessionLocal", test_sessionmaker):
            _make_service(jp_price=3500.0).sell("7203.T", 50)
            with test_sessionmaker() as session:
                from core.repositories.position_repo import PositionRepo
                pos = PositionRepo(session).get(1, 1, "7203.T")
                assert pos.quantity == 50
                assert pos.avg_buy_price == pytest.approx(3000.0)
