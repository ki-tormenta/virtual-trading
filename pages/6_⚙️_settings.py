import streamlit as st

from config.ui_theme import inject_styles, bottom_nav
from core.auth import require_auth
from core.services.portfolio_service import PortfolioService

inject_styles()
require_auth()
st.title("⚙️ Settings")

psvc = PortfolioService()

st.subheader("Data Export")
st.caption("Download all transaction history as a CSV file.")

if st.button("Generate CSV"):
    csv_data = psvc.export_transactions_csv()
    st.download_button(
        label="💾 Download transactions.csv",
        data=csv_data.encode("utf-8-sig"),
        file_name="transactions.csv",
        mime="text/csv",
    )

st.divider()

st.subheader("Portfolio Reset")
st.warning(
    "Deletes all trades, positions, and snapshots and resets your cash to the initial value (¥10,000,000). "
    "This cannot be undone."
)

confirm = st.text_input(
    "Type RESET to confirm",
    placeholder="RESET",
)

if st.button("Execute Reset", disabled=(confirm != "RESET"), type="primary"):
    psvc.reset_portfolio()
    st.success("Reset complete. Cash balance restored to initial value.")
    st.rerun()

bottom_nav()
