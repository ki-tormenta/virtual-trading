import pandas as pd
import streamlit as st

from config.ui_theme import inject_styles, bottom_nav
from core.auth import require_auth
from core.services.portfolio_service import PortfolioService

inject_styles()
require_auth()
st.title("📋 Positions")

try:
    with st.spinner("Loading..."):
        positions = PortfolioService().get_positions()

    if not positions:
        st.info("No positions. Buy stocks from the Trade page.")
    else:
        col_mf, col_tf = st.columns([2, 3])
        with col_mf:
            market_filter = st.selectbox("Market", ["All", "Japan (JP)", "US (US)"])
        with col_tf:
            tag_filter = st.text_input("Tag Filter", placeholder="e.g. growth")

        filtered = positions
        if market_filter == "Japan (JP)":
            filtered = [p for p in filtered if p.market == "JP"]
        elif market_filter == "US (US)":
            filtered = [p for p in filtered if p.market == "US"]

        if tag_filter.strip():
            from core.services.portfolio_service import PortfolioService as _PS
            tagged = _PS().get_tickers_with_tag(tag_filter.strip())
            filtered = [p for p in filtered if p.ticker in tagged]

        if not filtered:
            st.info("No matching positions.")
        else:
            total_value_jpy = sum(p.market_value_jpy for p in filtered)
            total_pnl_jpy = sum(p.unrealized_pnl_jpy for p in filtered)
            c1, c2, c3 = st.columns(3)
            c1.metric("# Holdings", f"{len(filtered)}")
            c2.metric("Total Value (JPY)", f"{total_value_jpy:,.0f}¥")
            c3.metric("Total Unrealized P&L (JPY)", f"{total_pnl_jpy:+,.0f}¥")

            st.divider()

            view = st.radio(
                "View Mode",
                ["Simple", "Detail"],
                horizontal=True,
                label_visibility="collapsed",
            )

            rows_simple = []
            rows_detail = []
            for p in filtered:
                is_jp = p.market == "JP"
                currency = "¥" if is_jp else "USD"
                pnl_str = (
                    f"{p.unrealized_pnl:+,.0f}¥"
                    if is_jp
                    else f"${p.unrealized_pnl:+,.2f}"
                )
                rows_simple.append({
                    "Name": p.name,
                    "Value (JPY)": f"{p.market_value_jpy:,.0f}¥",
                    "Unrealized P&L (JPY)": f"{p.unrealized_pnl_jpy:+,.0f}¥",
                    "P&L %": f"{p.unrealized_pnl_rate:+.2f}%",
                })
                rows_detail.append({
                    "Name": p.name,
                    "Ticker": p.ticker,
                    "Market": p.market,
                    "Qty": f"{p.quantity:,d} shares",
                    "Avg. Cost": f"{p.avg_buy_price:,.0f}¥" if is_jp else f"${p.avg_buy_price:,.2f}",
                    "Current Price": f"{p.current_price:,.0f}¥" if is_jp else f"${p.current_price:,.2f}",
                    "Value": f"{p.market_value:,.0f}¥" if is_jp else f"${p.market_value:,.2f}",
                    "Unrealized P&L": pnl_str,
                    "P&L %": f"{p.unrealized_pnl_rate:+.2f}%",
                })

            rows = rows_simple if view == "Simple" else rows_detail
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"Data fetch error: {e}")

bottom_nav()
