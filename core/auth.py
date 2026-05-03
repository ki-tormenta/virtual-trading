"""認証ユーティリティ。SKIP_AUTH=true のときは user_id=1 を返す。"""
from config.settings import settings


def get_current_user_id() -> int:
    """現在のユーザーIDを返す。

    - SKIP_AUTH=true（ローカル開発）: 固定値 1
    - Streamlit コンテキスト外（テスト・スクリプト直接実行）: 固定値 1
    - 本番: st.session_state["user_id"] から取得

    Returns:
        ユーザーID

    Raises:
        RuntimeError: 本番環境で未ログイン状態の場合
    """
    if settings.SKIP_AUTH:
        return 1

    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        import streamlit as st

        if get_script_run_ctx() is None:
            # テスト・スクリプト直接実行など、Streamlit セッション外
            return 1

        user_id = st.session_state.get("user_id")
        if user_id is None:
            raise RuntimeError("未ログインです")
        return int(user_id)

    except ImportError:
        return 1


def require_auth() -> None:
    """未ログインの場合はエラーを表示して実行を停止する。

    各ページの先頭で呼ぶことで、未ログイン時のクラッシュを防ぐ。
    SKIP_AUTH=true のときは何もしない。
    """
    if settings.SKIP_AUTH:
        return

    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        import streamlit as st

        if get_script_run_ctx() is None:
            return

        if st.session_state.get("user_id") is None:
            st.error("ログインが必要です。トップページから Google でログインしてください。")
            st.stop()

    except ImportError:
        pass
