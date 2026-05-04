from sqlalchemy import select, text

import core.models  # noqa: F401 - 全モデルをBase.metadataに登録するために必要
from config.settings import settings
from core.models.account import Account
from core.models.base import Base
from core.models.user import User
from infrastructure.db.connection import SessionLocal, engine, _is_sqlite


def init_db() -> None:
    """テーブル作成と初期データ投入を行う。"""
    Base.metadata.create_all(bind=engine)
    if settings.SKIP_AUTH:
        _seed_local_user()


def _seed_local_user() -> None:
    """ローカル開発用 id=1 ユーザーとメイン口座を作成する（既存なら何もしない）。"""
    with SessionLocal() as session:
        if not session.get(User, 1):
            session.add(User(id=1, username="admin"))
            session.flush()

            # PostgreSQL はシーケンスを明示insertで進めないため手動でリセット
            if not _is_sqlite:
                session.execute(
                    text("SELECT setval('users_id_seq', (SELECT MAX(id) FROM users))")
                )

        stmt = select(Account).where(Account.user_id == 1)
        if not session.execute(stmt).scalar_one_or_none():
            session.add(
                Account(
                    user_id=1,
                    name="メイン口座",
                    initial_cash=settings.INITIAL_CASH,
                    current_cash=settings.INITIAL_CASH,
                )
            )

        session.commit()


if __name__ == "__main__":
    init_db()
    print("DB initialized.")
