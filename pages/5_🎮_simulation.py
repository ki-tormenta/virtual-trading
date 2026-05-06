from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.ui_theme import inject_styles, bottom_nav, COLOR_PROFIT, PLOTLY_FONT, PLOTLY_BG
from core.auth import require_auth
from core.exceptions import (
    InsufficientFundsError,
    InsufficientSharesError,
    PriceNotAvailableError,
    StockNotFoundError,
)
from core.services.portfolio_service import PortfolioService
from core.services.price_service import PriceService
from core.services.trade_service import TradeService, normalize_ticker, _TAX_RATE

inject_styles()
require_auth()
st.title("🎮 Simulation")
st.caption("Trade in a virtual account by scenario. Changes don't affect your real portfolio.")

_MAX_SCENARIOS = 4
_SIM = "simulation"

psvc_base = PortfolioService()
scenarios = psvc_base.get_simulation_scenarios()

col_sel, col_new = st.columns([3, 1])

with col_sel:
    if scenarios:
        selected_scenario = st.selectbox(
            "Scenario",
            scenarios,
            key="sim_scenario_select",
        )
    else:
        selected_scenario = None
        st.info("No scenarios yet. Create one with the + New button.")

with col_new:
    if len(scenarios) < _MAX_SCENARIOS:
        if st.button("+ New", width="stretch"):
            st.session_state.sim_creating = True
    else:
        st.caption(f"Max {_MAX_SCENARIOS} / {_MAX_SCENARIOS}")

if st.session_state.get("sim_creating"):
    with st.form("sim_new_scenario_form"):
        new_name = st.text_input(
            "Scenario Name",
            placeholder="e.g. High-dividend, Growth focus",
            max_chars=20,
        )
        c1, c2 = st.columns(2)
        submitted = c1.form_submit_button("Create", type="primary", width="stretch")
        cancelled = c2.form_submit_button("Cancel", width="stretch")

        if submitted:
            name = new_name.strip()
            if not name:
                st.error("Please enter a scenario name")
            elif name in scenarios:
                st.error("A scenario with that name already exists")
            else:
                try:
                    psvc_base.create_simulation_scenario(name)
                    st.session_state.sim_creating = False
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        if cancelled:
            st.session_state.sim_creating = False
            st.rerun()

if not selected_scenario:
    bottom_nav()
    st.stop()

psvc = PortfolioService(account_type=_SIM, scenario_name=selected_scenario)

with st.expander("⚙️ Scenario Options", expanded=False):
    with st.form("sim_rename_form"):
        new_name_input = st.text_input(
            "Rename Scenario",
            value=selected_scenario,
            max_chars=20,
        )
        if st.form_submit_button("Rename", width="stretch"):
            new_name = new_name_input.strip()
            if not new_name:
                st.error("Please enter a name")
            elif new_name == selected_scenario:
                st.info("No changes")
            else:
                try:
                    psvc_base.rename_simulation_scenario(selected_scenario, new_name)
                    st.success(f"Renamed to '{new_name}'")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    st.divider()

    st.warning(f"This will delete all trades, positions, and snapshots for '{selected_scenario}' and reset it.")
    if st.button("🔄 Reset This Scenario", type="primary"):
        st.session_state.sim_confirm_reset = selected_scenario

if st.session_state.get("sim_confirm_reset") == selected_scenario:
    st.error(f"Are you sure you want to reset '{selected_scenario}'? This cannot be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, Reset", type="primary"):
        psvc.reset_portfolio()
        st.session_state.sim_confirm_reset = None
        st.success("Reset complete")
        st.rerun()
    if c2.button("Cancel"):
        st.session_state.sim_confirm_reset = None
        st.rerun()

st.divider()

tab_trade, tab_positions, tab_history = st.tabs(["📈 Trade", "📋 Positions", "📜 History"])

with tab_trade:
    sim_key = selected_scenario.replace(" ", "_")

    ticker_key = f"sim_ticker_{sim_key}"
    name_key = f"sim_name_{sim_key}"
    if ticker_key not in st.session_state:
        st.session_state[ticker_key] = None
    if name_key not in st.session_state:
        st.session_state[name_key] = None

    col1, col2 = st.columns([4, 1])
    with col1:
        code_input = st.text_input(
            "Ticker Symbol",
            placeholder="e.g. 7203 (Toyota) / AAPL",
            label_visibility="collapsed",
            key=f"sim_code_{sim_key}",
        )
    with col2:
        if st.button("🔍 Search", key=f"sim_search_{sim_key}", width="stretch"):
            if code_input:
                ticker_norm = normalize_ticker(code_input)
                with st.spinner("Fetching stock info..."):
                    try:
                        stock = PriceService().get_or_register_stock(ticker_norm)
                        st.session_state[ticker_key] = ticker_norm
                        st.session_state[name_key] = stock.name
                    except (StockNotFoundError, PriceNotAvailableError) as e:
                        st.error(f"Stock not found: {e}")
                        st.session_state[ticker_key] = None

    if st.session_state[ticker_key]:
        ticker: str = st.session_state[ticker_key]
        is_jp = ticker.endswith(".T")
        currency = "JPY" if is_jp else "USD"

        def fmt(p: float) -> str:
            return f"{p:,.0f}¥" if is_jp else f"${p:,.2f}"

        try:
            price_svc = PriceService()
            current_price = price_svc.get_close_price(ticker)

            st.subheader(f"{st.session_state[name_key]} ({ticker})")
            st.metric("Close Price", fmt(current_price))

            _PERIODS = {"1W": "5d", "1M": "1mo", "3M": "3mo", "1Y": "1y", "3Y": "3y"}
            period_label = st.radio(
                "Period", list(_PERIODS.keys()), index=3, horizontal=True,
                label_visibility="collapsed", key=f"sim_period_{sim_key}",
            )
            df_chart = price_svc.get_price_history(ticker, period=_PERIODS[period_label])
            fig = go.Figure(go.Scatter(
                x=df_chart.index, y=df_chart["Close"], mode="lines",
                line=dict(color=COLOR_PROFIT, width=1.5),
            ))
            fig.update_layout(
                title=f"Price Chart ({period_label} · Close)",
                xaxis_title="Date", yaxis_title=f"Close ({currency})",
                height=280, font=dict(family=PLOTLY_FONT),
                margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
            )
            st.plotly_chart(fig, use_container_width=True)

            buy_tab, sell_tab = st.tabs(["📈 Buy", "📉 Sell"])

            with buy_tab:
                with st.form(f"sim_buy_{sim_key}"):
                    qty = st.number_input("Qty (shares)", min_value=1, value=100, step=1)
                    memo = st.text_area("Memo", placeholder="Strategy rationale, etc.")
                    tags = st.text_input("Tags", placeholder="e.g. value, long-term")

                    subtotal = current_price * qty
                    if is_jp:
                        st.caption(f"Required: {subtotal:,.0f}¥")
                    else:
                        fee_est = min(subtotal * 0.00495, 22.0)
                        st.caption(f"Required: ${subtotal:,.2f} (+ fee ${fee_est:.2f})")

                    if st.form_submit_button("Execute Buy Order", width="stretch", type="primary"):
                        try:
                            txs = TradeService(account_type=_SIM, scenario_name=selected_scenario).buy(
                                ticker, int(qty), memo=memo or None, tags=tags or None
                            )
                            st.success(f"Buy complete ✓  {txs[0].quantity:,d} shares @ {fmt(txs[0].price)}")
                            st.rerun()
                        except InsufficientFundsError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"Error: {e}")

            with sell_tab:
                positions = psvc.get_positions()
                pos = next((p for p in positions if p.ticker == ticker), None)
                if pos is None:
                    st.info("No holdings for this stock.")
                else:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Holdings", f"{pos.quantity:,d} shares")
                    c2.metric("Avg. Cost", fmt(pos.avg_buy_price))
                    c3.metric("Unrealized P&L", fmt(pos.unrealized_pnl),
                              delta=f"{pos.unrealized_pnl_rate:+.2f}%")

                    with st.form(f"sim_sell_{sim_key}"):
                        qty = st.number_input(
                            "Qty to Sell (shares)", min_value=1, max_value=pos.quantity,
                            value=pos.quantity, step=1,
                        )
                        memo = st.text_area("Memo", placeholder="Review, notes, etc.")
                        exp_pnl = (current_price - pos.avg_buy_price) * int(qty)
                        exp_tax = max(0.0, exp_pnl) * _TAX_RATE
                        st.caption(f"Est. Realized P&L: {exp_pnl:+,.0f}¥  Tax: {exp_tax:,.0f}¥")

                        if st.form_submit_button("Execute Sell Order", width="stretch", type="primary"):
                            try:
                                tx = TradeService(account_type=_SIM, scenario_name=selected_scenario).sell(
                                    ticker, int(qty), memo=memo or None
                                )
                                st.success(
                                    f"Sell complete ✓  {tx.quantity:,d} shares @ {fmt(tx.price)}  "
                                    f"Realized P&L: {tx.realized_pnl:+,.0f}¥"
                                )
                                st.rerun()
                            except InsufficientSharesError as e:
                                st.error(str(e))
                            except Exception as e:
                                st.error(f"Error: {e}")

        except (StockNotFoundError, PriceNotAvailableError) as e:
            st.error(f"Price fetch error: {e}")

with tab_positions:
    try:
        sim_summary = psvc.get_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("Cash Balance", f"¥{sim_summary.current_cash:,.0f}")
        c2.metric("Total Value", f"¥{sim_summary.market_value:,.0f}")
        c3.metric("Total P&L", f"¥{sim_summary.total_pnl:+,.0f}",
                  delta=f"{sim_summary.total_pnl_rate:+.2f}%")

        positions = psvc.get_positions()
        if not positions:
            st.info("No positions. Buy from the Trade tab.")
        else:
            view = st.radio("View", ["Simple", "Detail"], horizontal=True,
                            label_visibility="collapsed", key="sim_pos_view")
            rows_s, rows_d = [], []
            for p in positions:
                is_jp_p = p.market == "JP"
                cur = "¥" if is_jp_p else "USD"
                rows_s.append({
                    "Name": p.name,
                    "Value (JPY)": f"{p.market_value_jpy:,.0f}¥",
                    "Unrealized P&L (JPY)": f"{p.unrealized_pnl_jpy:+,.0f}¥",
                    "P&L %": f"{p.unrealized_pnl_rate:+.2f}%",
                })
                rows_d.append({
                    "Name": p.name,
                    "Ticker": p.ticker,
                    "Market": p.market,
                    "Qty": f"{p.quantity:,d} shares",
                    "Avg. Cost": f"{p.avg_buy_price:,.0f}¥" if is_jp_p else f"${p.avg_buy_price:,.2f}",
                    "Current Price": f"{p.current_price:,.0f}¥" if is_jp_p else f"${p.current_price:,.2f}",
                    "Unrealized P&L (JPY)": f"{p.unrealized_pnl_jpy:+,.0f}¥",
                    "P&L %": f"{p.unrealized_pnl_rate:+.2f}%",
                })
            st.dataframe(pd.DataFrame(rows_s if view == "Simple" else rows_d),
                         use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Data fetch error: {e}")

with tab_history:
    try:
        with st.expander("🔍 Filters", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                type_filter = st.selectbox("Type", ["All", "Buy (BUY)", "Sell (SELL)"],
                                           key="sim_type_filter")
                ticker_input_h = st.text_input("Ticker Symbol", placeholder="e.g. 7203 / AAPL",
                                               key="sim_ticker_filter")
            with col2:
                from_date = st.date_input("From", value=date.today() - timedelta(days=90),
                                          key="sim_from_date")
                to_date = st.date_input("To", value=date.today(), key="sim_to_date")

        trade_type = None
        if type_filter == "Buy (BUY)":
            trade_type = "BUY"
        elif type_filter == "Sell (SELL)":
            trade_type = "SELL"

        ticker_f = normalize_ticker(ticker_input_h) if ticker_input_h.strip() else None
        records = psvc.get_transaction_records(
            ticker=ticker_f, from_date=from_date, to_date=to_date, trade_type=trade_type,
        )

        if not records:
            st.info("No matching transactions.")
        else:
            st.caption(f"{len(records)} records")
            rows = []
            for r in records:
                is_jp_r = r.market == "JP"
                rows.append({
                    "Date": r.transaction_date.strftime("%Y-%m-%d"),
                    "Type": "Buy" if r.type == "BUY" else "Sell",
                    "Name": r.stock_name,
                    "Qty": f"{r.quantity:,d} shares",
                    "Price": f"{r.price:,.0f}¥" if is_jp_r else f"${r.price:,.2f}",
                    "Realized P&L (JPY)": f"{r.realized_pnl:+,.0f}¥" if r.realized_pnl is not None else "-",
                    "Memo": r.memo or "",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Data fetch error: {e}")

bottom_nav()
