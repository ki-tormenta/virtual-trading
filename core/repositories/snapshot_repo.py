from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models.snapshot import DailySnapshot


class SnapshotRepo:
    """日次スナップショットリポジトリ。CRUD操作のみ担当。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, snapshot: DailySnapshot) -> DailySnapshot:
        """スナップショットを追加または更新する（UPSERT）。"""
        existing = self._session.get(
            DailySnapshot, (snapshot.user_id, snapshot.account_id, snapshot.date)
        )
        if existing is None:
            self._session.add(snapshot)
            return snapshot
        existing.cash = snapshot.cash
        existing.market_value = snapshot.market_value
        existing.total_assets = snapshot.total_assets
        existing.jp_market_value = snapshot.jp_market_value
        existing.us_market_value = snapshot.us_market_value
        return existing

    def get_history(
        self,
        user_id: int,
        account_id: int,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[DailySnapshot]:
        """スナップショット履歴を日付昇順で返す。"""
        stmt = select(DailySnapshot).where(
            DailySnapshot.user_id == user_id,
            DailySnapshot.account_id == account_id,
        )
        if from_date is not None:
            stmt = stmt.where(DailySnapshot.date >= from_date)
        if to_date is not None:
            stmt = stmt.where(DailySnapshot.date <= to_date)
        stmt = stmt.order_by(DailySnapshot.date.asc())
        return list(self._session.execute(stmt).scalars())

    def get_latest(self, user_id: int, account_id: int) -> DailySnapshot | None:
        """最新のスナップショットを返す。"""
        stmt = (
            select(DailySnapshot)
            .where(
                DailySnapshot.user_id == user_id,
                DailySnapshot.account_id == account_id,
            )
            .order_by(DailySnapshot.date.desc())
            .limit(1)
        )
        return self._session.execute(stmt).scalar_one_or_none()
