from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config.ui_theme import inject_styles, bottom_nav
from core.auth import require_auth
from core.services.portfolio_service import PortfolioService
from core.services.trade_service import normalize_ticker

inject_styles()
require_auth()
st.title("📜 History")

try:
    with st.expander("🔍 Filters", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            type_filter = st.selectbox("Type", ["All", "Buy (BUY)", "Sell (SELL)"])
            ticker_input = st.text_input("Ticker Symbol", placeholder="e.g. 7203 / AAPL")
            tag_input = st.text_input("Tag", placeholder="e.g. growth")
        with col2:
            from_date = st.date_input("From", value=date.today() - timedelta(days=90))
            to_date = st.date_input("To", value=date.today())

    trade_type: str | None = None
    if type_filter == "Buy (BUY)":
        trade_type = "BUY"
    elif type_filter == "Sell (SELL)":
        trade_type = "SELL"

    ticker_filter: str | None = normalize_ticker(ticker_input) if ticker_input.strip() else None
    tag_filter: str | None = tag_input.strip() or None

    records = PortfolioService().get_transaction_records(
        ticker=ticker_filter,
        from_date=from_date,
        to_date=to_date,
        trade_type=trade_type,
        tag=tag_filter,
    )

    if not records:
        st.info("No matching transactions.")
    else:
        st.caption(f"{len(records)} records")

        rows = []
        for r in records:
            is_jp = r.market == "JP"
            rows.append({
                "Date": r.transaction_date.strftime("%Y-%m-%d"),
                "Type": "Buy" if r.type == "BUY" else "Sell",
                "Name": r.stock_name,
                "Ticker": r.ticker,
                "Qty": f"{r.quantity:,d} shares",
                "Price": (
                    f"{r.price:,.0f}¥" if is_jp else f"${r.price:,.2f}"
                ),
                "Total": (
                    f"{r.total_amount:,.0f}¥"
                    if is_jp
                    else f"${r.total_amount:,.2f}"
                ),
                "Realized P&L (JPY)": (
                    f"{r.realized_pnl:+,.0f}¥"
                    if r.realized_pnl is not None
                    else "-"
                ),
                "Fee (JPY)": f"{r.fee:,.0f}¥" if r.fee else "-",
                "Tax (JPY)": f"{r.tax:,.0f}¥" if r.tax else "-",
                "Memo": r.memo or "",
                "Tags": r.tags or "",
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.divider()
        with st.expander("✏️ Edit Memo"):
            options = {
                f"{r.transaction_date.strftime('%Y-%m-%d')} "
                f"{'Buy' if r.type == 'BUY' else 'Sell'} "
                f"{r.stock_name} {r.quantity:,} shares": r
                for r in records
            }
            selected_label = st.selectbox("Select transaction", list(options.keys()))
            selected_record = options[selected_label]
            new_memo = st.text_area("Memo", value=selected_record.memo or "", height=100)
            if st.button("Save"):
                PortfolioService().update_transaction_memo(selected_record.id, new_memo or None)
                st.success("Memo saved")
                st.rerun()

except Exception as e:
    st.error(f"Data fetch error: {e}")

bottom_nav()
