"""Streamlit エントリポイント。認証フロー（PKCE Google OAuth）を管理する。"""
import urllib.parse

import streamlit as st

from config.settings import settings
from config.ui_theme import inject_styles
from infrastructure.db.init_db import init_db

st.set_page_config(
    page_title=settings.APP_TITLE,
    page_icon=settings.APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_styles()
init_db()


# ── OAuth コールバック処理 ────────────────────────────────────────────────────

def _handle_oauth_callback() -> bool:
    """?code=... が URL にあればコールバックを処理して True を返す。"""
    code = st.query_params.get("code")
    state = st.query_params.get("state")
    if not code or not state:
        return False

    try:
        from infrastructure.auth.oauth_flow import get_verifier
        from infrastructure.auth.supabase_client import get_supabase_client

        verifier = get_verifier(state)
        if verifier is None:
            st.error("認証フローが無効か期限切れです。もう一度ログインしてください。")
            st.query_params.clear()
            return True

        supabase = get_supabase_client()
        auth_resp = supabase.auth.exchange_code_for_session(
            {"auth_code": code, "code_verifier": verifier}
        )

        if auth_resp.user is None:
            st.error("認証に失敗しました。")
            st.query_params.clear()
            return True

        email = auth_resp.user.email
        user_id = _ensure_user_account(email)
        st.session_state["user_id"] = user_id
        st.session_state["user_email"] = email
        st.query_params.clear()
        st.rerun()

    except Exception as e:
        st.error(f"ログインエラー: {e}")
        st.query_params.clear()

    return True


def _ensure_user_account(email: str) -> int:
    """メールアドレスから User + Account を特定 / 作成してユーザーIDを返す。

    Args:
        email: Supabase から取得したメールアドレス

    Returns:
        DB 上のユーザーID

    Raises:
        PermissionError: 招待されていないメールアドレスの場合
    """
    from sqlalchemy import select

    from config.settings import settings
    from core.models.account import Account
    from core.models.user import User
    from infrastructure.db.connection import SessionLocal

    with SessionLocal() as session:
        user = session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if user is None:
            user = User(username=email.split("@")[0], email=email)
            session.add(user)
            session.flush()

            session.add(
                Account(
                    user_id=user.id,
                    name="メイン口座",
                    initial_cash=settings.INITIAL_CASH,
                    current_cash=settings.INITIAL_CASH,
                )
            )

        session.commit()
        return user.id


# ── ログインページ ────────────────────────────────────────────────────────────

def _show_login_page() -> None:
    """Google ログインボタンを表示する。"""
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            f"<h2 style='text-align:center'>{settings.APP_ICON} {settings.APP_TITLE}</h2>",
            unsafe_allow_html=True,
        )
        st.markdown("<br>", unsafe_allow_html=True)

        try:
            from infrastructure.auth.oauth_flow import create_verifier, store_verifier
            from infrastructure.auth.supabase_client import get_supabase_client

            verifier, challenge = create_verifier()
            supabase = get_supabase_client()

            oauth_resp = supabase.auth.sign_in_with_oauth(
                {
                    "provider": "google",
                    "options": {
                        "redirect_to": settings.APP_URL,
                        "query_params": {
                            "code_challenge": challenge,
                            "code_challenge_method": "S256",
                        },
                    },
                }
            )

            # Supabase が生成した state を URL からパースしてキーに使う
            parsed = urllib.parse.urlparse(oauth_resp.url)
            supabase_state = urllib.parse.parse_qs(parsed.query).get("state", [None])[0]
            if supabase_state:
                store_verifier(supabase_state, verifier)

            st.link_button(
                "🔐  Google でログイン",
                oauth_resp.url,
                use_container_width=True,
            )
            st.caption(
                "<div style='text-align:center'>招待されたアカウントでのみ利用できます</div>",
                unsafe_allow_html=True,
            )

        except Exception as e:
            st.error(f"ログインページの初期化に失敗しました: {e}")


# ── ログアウト（サイドバー） ──────────────────────────────────────────────────

def _render_sidebar_logout() -> None:
    with st.sidebar:
        email = st.session_state.get("user_email", "")
        if email:
            st.caption(f"ログイン中: {email}")
        if st.button("ログアウト", use_container_width=True):
            st.session_state.clear()
            st.rerun()


# ── メインロジック ────────────────────────────────────────────────────────────

if settings.SKIP_AUTH:
    # ローカル開発: 認証スキップ
    if "user_id" not in st.session_state:
        st.session_state["user_id"] = 1

elif _handle_oauth_callback():
    # コールバック処理中 → _handle_oauth_callback 内で rerun または error 表示
    st.stop()

elif "user_id" not in st.session_state:
    _show_login_page()
    st.stop()

else:
    _render_sidebar_logout()

# ── ログイン済み: 通常起動処理 ────────────────────────────────────────────────

if "snapshot_taken" not in st.session_state:
    st.session_state.snapshot_taken = False

if not st.session_state.snapshot_taken:
    try:
        from core.services.portfolio_service import PortfolioService

        PortfolioService().take_snapshot()
    except Exception:
        pass
    st.session_state.snapshot_taken = True

st.title(f"{settings.APP_ICON} {settings.APP_TITLE}")
st.info("サイドバーのメニューからページを選択してください。")
