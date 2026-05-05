import streamlit as st

from config.ui_theme import inject_styles, bottom_nav
from core.auth import require_auth
from core.services.portfolio_service import PortfolioService

inject_styles()
require_auth()
st.title("⚙️ 設定")

psvc = PortfolioService()

# ── CSV エクスポート ────────────────────────────────────────────────────────
st.subheader("データエクスポート")
st.caption("全取引履歴を CSV ファイルでダウンロードします。")

if st.button("CSV を生成"):
    csv_data = psvc.export_transactions_csv()
    st.download_button(
        label="💾 transactions.csv をダウンロード",
        data=csv_data.encode("utf-8-sig"),  # BOM 付きで Excel でも文字化けしない
        file_name="transactions.csv",
        mime="text/csv",
    )

st.divider()

# ── ポートフォリオリセット ────────────────────────────────────────────────
st.subheader("ポートフォリオリセット")
st.warning(
    "全取引履歴・ポジション・スナップショットを削除し、現金残高を初期値（1,000万円）に戻します。"
    "この操作は取り消せません。"
)

confirm = st.text_input(
    "確認のため「RESET」と入力してください",
    placeholder="RESET",
)

if st.button("リセットを実行", disabled=(confirm != "RESET"), type="primary"):
    psvc.reset_portfolio()
    st.success("リセットが完了しました。現金残高を初期値に戻しました。")
    st.rerun()

bottom_nav()
