"""PortfolioService の単体テスト。"""
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from core.services.portfolio_service import PortfolioService
from core.services.trade_service import TradeService, _US_FEE_RATE, _US_FEE_CAP_USD


def _patch_price(svc: PortfolioService, jp_price: float = 3500.0, usd_jpy: float = 150.0) -> None:
    mock = MagicMock()
    mock.get_close_price.return_value = jp_price
    mock.get_usd_jpy_rate.return_value = usd_jpy
    svc._price_service = mock


def _buy(session_factory, ticker: str, qty: int, price: float, usd_jpy: float = 150.0):
    svc = TradeService()
    mock_p = MagicMock()
    mock_p.get_close_price.return_value = price
    mock_p.get_usd_jpy_rate.return_value = usd_jpy
    mock_p.get_or_register_stock.return_value = MagicMock()
    svc._price_service = mock_p
    with patch("core.services.trade_service.SessionLocal", session_factory):
        svc.buy(ticker, qty)


class TestGetSummary:
    def test_no_positions_returns_initial_cash(self, test_sessionmaker):
        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            psvc = PortfolioService()
            _patch_price(psvc)
            summary = psvc.get_summary()

        assert summary.current_cash == pytest.approx(10_000_000.0)
        assert summary.market_value == pytest.approx(0.0)
        assert summary.total_assets == pytest.approx(10_000_000.0)
        assert summary.unrealized_pnl == pytest.approx(0.0)
        assert summary.total_fee == pytest.approx(0.0)
        assert summary.total_tax == pytest.approx(0.0)

    def test_total_assets_equals_cash_plus_market_value(self, test_sessionmaker):
        """総資産 = 現金 + 評価額 になること。"""
        _buy(test_sessionmaker, "7203.T", 100, 3000.0)

        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            psvc = PortfolioService()
            _patch_price(psvc, jp_price=3500.0)
            summary = psvc.get_summary()

        cash = 10_000_000.0 - 300_000.0  # 9,700,000
        market = 3500.0 * 100             # 350,000
        assert summary.current_cash == pytest.approx(cash)
        assert summary.market_value == pytest.approx(market)
        assert summary.total_assets == pytest.approx(cash + market)

    def test_unrealized_pnl_jp(self, test_sessionmaker):
        """日本株の含み損益が正しく計算されること。"""
        _buy(test_sessionmaker, "7203.T", 100, 3000.0)

        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            psvc = PortfolioService()
            _patch_price(psvc, jp_price=3500.0)
            summary = psvc.get_summary()

        assert summary.unrealized_pnl == pytest.approx((3500.0 - 3000.0) * 100)

    def test_us_stock_market_value_in_jpy(self, test_sessionmaker):
        """米国株の評価額が JPY 換算で集計されること。"""
        _buy(test_sessionmaker, "AAPL", 10, 200.0, usd_jpy=150.0)

        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            psvc = PortfolioService()
            mock_p = MagicMock()
            mock_p.get_close_price.return_value = 220.0
            mock_p.get_usd_jpy_rate.return_value = 150.0
            psvc._price_service = mock_p
            summary = psvc.get_summary()

        buy_jpy = 200.0 * 10 * 150.0  # 300,000
        fee_jpy = min(200.0 * 10 * _US_FEE_RATE, _US_FEE_CAP_USD) * 150.0
        market_jpy = 220.0 * 10 * 150.0  # 330,000
        assert summary.us_market_value == pytest.approx(market_jpy)
        assert summary.current_cash == pytest.approx(10_000_000.0 - buy_jpy - fee_jpy)

    def test_total_pnl_rate(self, test_sessionmaker):
        """総合損益率 = 総合損益 / 初期資金 × 100 になること。"""
        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            psvc = PortfolioService()
            _patch_price(psvc)
            summary = psvc.get_summary()

        expected_rate = summary.total_pnl / summary.initial_cash * 100
        assert summary.total_pnl_rate == pytest.approx(expected_rate)


class TestGetAllTags:
    def test_returns_empty_when_no_transactions(self, test_sessionmaker):
        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            psvc = PortfolioService()
            assert psvc.get_all_tags() == []

    def test_returns_sorted_unique_tags(self, test_sessionmaker):
        from core.models.transaction import Transaction

        with test_sessionmaker() as session:
            session.add(Transaction(
                user_id=1, account_id=1, ticker="7203.T",
                type="BUY", quantity=100, price=3000.0, total_amount=300_000.0,
                transaction_date=date.today(), tags="成長株,テック",
            ))
            session.add(Transaction(
                user_id=1, account_id=1, ticker="AAPL",
                type="BUY", quantity=10, price=200.0, total_amount=2000.0,
                transaction_date=date.today(), tags="テック,米国株",
            ))
            session.commit()

        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            psvc = PortfolioService()
            tags = psvc.get_all_tags()

        assert tags == sorted(["成長株", "テック", "米国株"])


class TestUpdateTransactionMemo:
    def test_memo_is_updated(self, test_sessionmaker):
        from core.models.transaction import Transaction

        with test_sessionmaker() as session:
            session.add(Transaction(
                id=99, user_id=1, account_id=1, ticker="7203.T",
                type="BUY", quantity=100, price=3000.0, total_amount=300_000.0,
                transaction_date=date.today(), memo="旧メモ",
            ))
            session.commit()

        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            PortfolioService().update_transaction_memo(99, "新メモ")

        with test_sessionmaker() as session:
            tx = session.get(Transaction, 99)
            assert tx.memo == "新メモ"


class TestResetPortfolio:
    def test_reset_clears_all_data_and_restores_cash(self, test_sessionmaker):
        _buy(test_sessionmaker, "7203.T", 100, 3000.0)

        with patch("core.services.portfolio_service.SessionLocal", test_sessionmaker):
            PortfolioService().reset_portfolio()

        with test_sessionmaker() as session:
            from core.repositories.account_repo import AccountRepo
            from core.models.transaction import Transaction
            from core.models.position import Position
            from sqlalchemy import select, func

            acc = AccountRepo(session).get_main_account(1)
            assert acc.current_cash == pytest.approx(10_000_000.0)
            assert session.execute(select(func.count()).select_from(Transaction)).scalar() == 0
            assert session.execute(select(func.count()).select_from(Position)).scalar() == 0
