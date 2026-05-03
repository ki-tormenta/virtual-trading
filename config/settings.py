from pathlib import Path

from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _get_secret(key: str, default: str = "") -> str:
    """環境変数を取得する。Streamlit Secrets にも対応。"""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


class Settings:
    """アプリケーション設定。環境変数 / Streamlit Secrets から取得する。"""

    # 初期資金（円）
    INITIAL_CASH: float = float(os.getenv("INITIAL_CASH", "10000000"))

    # データベース（SQLite ローカル or PostgreSQL 本番）
    DB_PATH: str = os.getenv("DB_PATH", str(BASE_DIR / "data" / "trading.db"))

    @property
    def DATABASE_URL(self) -> str:
        url = _get_secret("DATABASE_URL")
        if url:
            # Heroku/Supabase が postgres:// を返す場合は postgresql:// に変換
            return url.replace("postgres://", "postgresql://", 1)
        return f"sqlite:///{self.DB_PATH}"

    # Supabase
    @property
    def SUPABASE_URL(self) -> str:
        return _get_secret("SUPABASE_URL")

    @property
    def SUPABASE_ANON_KEY(self) -> str:
        return _get_secret("SUPABASE_ANON_KEY")

    # アプリ公開 URL（OAuth リダイレクト先）
    APP_URL: str = os.getenv("APP_URL", "http://localhost:8501")

    # ローカル開発時に認証をスキップする（SKIP_AUTH=true）
    SKIP_AUTH: bool = os.getenv("SKIP_AUTH", "false").lower() == "true"

    # アプリ設定
    APP_TITLE: str = os.getenv("APP_TITLE", "仮想売買アプリ")
    APP_ICON: str = os.getenv("APP_ICON", "📈")

    # 株価取得設定
    PRICE_FETCH_RETRY_MAX: int = int(os.getenv("PRICE_FETCH_RETRY_MAX", "3"))
    PRICE_FETCH_RETRY_BACKOFF: float = float(os.getenv("PRICE_FETCH_RETRY_BACKOFF", "1.5"))

    # タイムゾーン
    TZ_JP: str = "Asia/Tokyo"
    TZ_US: str = "America/New_York"


settings = Settings()
