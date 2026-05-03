"""テスト共通フィクスチャ。インメモリ SQLite DB を使う。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models.base import Base
from core.models.account import Account
from core.models.stock import Stock
from core.models.user import User


@pytest.fixture()
def test_sessionmaker():
    """インメモリ DB を初期化し、テスト用 sessionmaker を返す。"""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    with TestSession() as session:
        session.add(User(id=1, username="test", email="test@test.com"))
        session.add(Account(
            id=1, user_id=1, name="テスト口座",
            initial_cash=10_000_000.0, current_cash=10_000_000.0,
        ))
        session.add(Stock(ticker="7203.T", code="7203", name="トヨタ自動車", market="JP"))
        session.add(Stock(ticker="AAPL", code="AAPL", name="Apple Inc.", market="US"))
        session.commit()

    return TestSession
