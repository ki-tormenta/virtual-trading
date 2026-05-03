from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models.account import Account


class AccountRepo:
    """口座リポジトリ。CRUD操作のみ担当。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, account_id: int) -> Account | None:
        """IDで口座を取得する。"""
        return self._session.get(Account, account_id)

    def get_by_user(self, user_id: int) -> list[Account]:
        """ユーザーの全口座を取得する。"""
        stmt = select(Account).where(Account.user_id == user_id)
        return list(self._session.execute(stmt).scalars())

    def get_main_account(self, user_id: int) -> Account | None:
        """ユーザーの最初の口座（メイン口座）を取得する。"""
        stmt = select(Account).where(Account.user_id == user_id).limit(1)
        return self._session.execute(stmt).scalar_one_or_none()

    def update_cash(self, account_id: int, new_cash: float) -> None:
        """口座の現金残高を更新する。"""
        account = self._session.get(Account, account_id)
        if account is not None:
            account.current_cash = new_cash
