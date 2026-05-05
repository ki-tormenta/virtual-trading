from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models.account import Account

_MAX_SIMULATION_ACCOUNTS = 4


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
        """ユーザーのメイン口座（account_type='real'）を取得する。"""
        stmt = select(Account).where(
            Account.user_id == user_id,
            Account.account_type == "real",
        ).limit(1)
        return self._session.execute(stmt).scalar_one_or_none()

    def get_simulation_accounts(self, user_id: int) -> list[Account]:
        """ユーザーの全シミュレーション口座を作成日順で返す。"""
        stmt = select(Account).where(
            Account.user_id == user_id,
            Account.account_type == "simulation",
        ).order_by(Account.created_at)
        return list(self._session.execute(stmt).scalars())

    def get_or_create_simulation_account(
        self, user_id: int, initial_cash: float, scenario_name: str
    ) -> Account:
        """指定名のシミュレーション口座を取得する。存在しなければ作成する。

        Args:
            user_id: ユーザーID
            initial_cash: 初期資金
            scenario_name: シナリオ名（口座の識別子）

        Returns:
            シミュレーション口座

        Raises:
            RuntimeError: 上限（4口座）に達しており、かつ指定名が存在しない場合
        """
        stmt = select(Account).where(
            Account.user_id == user_id,
            Account.account_type == "simulation",
            Account.name == scenario_name,
        ).limit(1)
        account = self._session.execute(stmt).scalar_one_or_none()
        if account is not None:
            return account

        existing = self.get_simulation_accounts(user_id)
        if len(existing) >= _MAX_SIMULATION_ACCOUNTS:
            raise RuntimeError(
                f"シミュレーション口座は最大{_MAX_SIMULATION_ACCOUNTS}つまでです"
            )

        account = Account(
            user_id=user_id,
            name=scenario_name,
            account_type="simulation",
            initial_cash=initial_cash,
            current_cash=initial_cash,
        )
        self._session.add(account)
        self._session.flush()
        return account

    def rename_simulation_account(self, user_id: int, old_name: str, new_name: str) -> None:
        """シミュレーション口座の名前を変更する。"""
        stmt = select(Account).where(
            Account.user_id == user_id,
            Account.account_type == "simulation",
            Account.name == old_name,
        ).limit(1)
        account = self._session.execute(stmt).scalar_one_or_none()
        if account is not None:
            account.name = new_name

    def update_cash(self, account_id: int, new_cash: float) -> None:
        """口座の現金残高を更新する。"""
        account = self._session.get(Account, account_id)
        if account is not None:
            account.current_cash = new_cash
