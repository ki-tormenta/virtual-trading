import streamlit as st
import plotly.graph_objects as go

from config.ui_theme import inject_styles, bottom_nav, COLOR_PROFIT, COLOR_LOSS, PLOTLY_FONT, PLOTLY_BG, PLOTLY_GRID, PLOTLY_TICK_COLOR
from core.exceptions import (
    InsufficientFundsError,
    InsufficientSharesError,
    PriceNotAvailableError,
    StockNotFoundError,
)
from core.auth import require_auth
from core.services.portfolio_service import PortfolioService
from core.services.price_service import PriceService
from core.services.trade_service import TradeService, normalize_ticker, _TAX_RATE

inject_styles()
require_auth()
st.title("🔍 Trade")

try:
    _cash = PortfolioService().get_summary().current_cash
    st.metric("Available Cash", f"¥{_cash:,.0f}")
except Exception:
    pass

if "trade_ticker" not in st.session_state:
    st.session_state.trade_ticker = None
if "trade_stock_name" not in st.session_state:
    st.session_state.trade_stock_name = None

col1, col2 = st.columns([4, 1])
with col1:
    code_input = st.text_input(
        "Ticker Symbol",
        placeholder="e.g. 7203 (Toyota) / AAPL (Apple)",
        label_visibility="collapsed",
    )
with col2:
    search_btn = st.button("🔍 Search", width="stretch")

if search_btn and code_input:
    ticker = normalize_ticker(code_input)
    with st.spinner("Fetching stock info..."):
        try:
            stock = PriceService().get_or_register_stock(ticker)
            st.session_state.trade_ticker = ticker
            st.session_state.trade_stock_name = stock.name
        except (StockNotFoundError, PriceNotAvailableError) as e:
            st.error(f"Stock not found: {e}")
            st.session_state.trade_ticker = None

if st.session_state.trade_ticker:
    ticker: str = st.session_state.trade_ticker
    is_jp = ticker.endswith(".T")
    is_us = not is_jp
    currency = "JPY" if is_jp else "USD"

    def fmt_price(p: float) -> str:
        return f"{p:,.0f}¥" if is_jp else f"${p:,.2f}"

    try:
        price_svc = PriceService()
        current_price = price_svc.get_close_price(ticker)

        st.subheader(f"{st.session_state.trade_stock_name} ({ticker})")
        st.metric("Close Price", fmt_price(current_price))

        _PERIODS = {"1W": "5d", "1M": "1mo", "3M": "3mo", "1Y": "1y", "3Y": "3y"}
        period_label = st.radio(
            "Period",
            list(_PERIODS.keys()),
            index=3,
            horizontal=True,
            label_visibility="collapsed",
        )
        period = _PERIODS[period_label]
        df = price_svc.get_price_history(ticker, period=period, include_ohlcv=True)

        fig = go.Figure()
        if all(c in df.columns for c in ["Open", "High", "Low", "Close"]):
            fig.add_trace(go.Candlestick(
                x=df.index,
                open=df["Open"], high=df["High"],
                low=df["Low"], close=df["Close"],
                name="Price",
                increasing=dict(line=dict(color=COLOR_PROFIT, width=1),
                                fillcolor="rgba(0,212,170,0.25)"),
                decreasing=dict(line=dict(color=COLOR_LOSS, width=1),
                                fillcolor="rgba(255,71,87,0.25)"),
                showlegend=False,
            ))
        else:
            fig.add_trace(go.Scatter(
                x=df.index, y=df["Close"], mode="lines",
                line=dict(color=COLOR_PROFIT, width=1.5),
            ))
        close = df["Close"]
        if len(close) >= 25:
            fig.add_trace(go.Scatter(
                x=df.index, y=close.rolling(25).mean(),
                mode="lines", name="MA25",
                line=dict(color="#4299e1", width=1.2, dash="dot"),
            ))
        if len(close) >= 75:
            fig.add_trace(go.Scatter(
                x=df.index, y=close.rolling(75).mean(),
                mode="lines", name="MA75",
                line=dict(color="#f6c90e", width=1.2, dash="dot"),
            ))
        tick_pfx = "¥" if is_jp else "$"
        fig.update_layout(
            title=f"Price Chart ({period_label} · OHLC)",
            xaxis_title="Date",
            yaxis_title=f"Price ({currency})",
            height=380,
            font=dict(family=PLOTLY_FONT, color=PLOTLY_TICK_COLOR),
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
            xaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID,
                       rangeslider=dict(visible=False),
                       showline=False, zeroline=False),
            yaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID,
                       showline=False, zeroline=False,
                       tickprefix=tick_pfx),
            legend=dict(orientation="h", y=-0.12, font=dict(size=11)),
            hovermode="x unified",
            dragmode="pan",
        )
        st.plotly_chart(fig, use_container_width=True,
                        config={"scrollZoom": True, "displayModeBar": False})

        buy_tab, sell_tab = st.tabs(["📈 Buy", "📉 Sell"])

        with buy_tab:
            with st.form("buy_form"):
                qty = st.number_input("Qty (shares)", min_value=1, value=100, step=1)
                memo = st.text_area("Memo", placeholder="Reason, outlook, etc.")
                tags = st.text_input("Tags (comma-separated)", placeholder="e.g. growth, long-term")

                subtotal = current_price * qty
                if is_jp:
                    lot_q = (int(qty) // 100) * 100
                    sunit_q = int(qty) % 100
                    if sunit_q > 0 and lot_q > 0:
                        st.caption(
                            f"Required: {subtotal:,.0f}¥  "
                            f"(Regular {lot_q} shares + **S-share {sunit_q} shares** split)"
                        )
                    elif sunit_q > 0:
                        st.caption(f"Required: {subtotal:,.0f}¥ (processed as **S-share**)")
                    else:
                        st.caption(f"Required: {subtotal:,.0f}¥")
                else:
                    fee_est = min(subtotal * 0.00495, 22.0)
                    st.caption(
                        f"Required: ${subtotal:,.2f}  (+ fee ${fee_est:.2f}, total ${subtotal + fee_est:,.2f})"
                    )

                if st.form_submit_button("Execute Buy Order", width="stretch", type="primary"):
                    try:
                        txs = TradeService().buy(
                            ticker, int(qty), memo=memo or None, tags=tags or None
                        )
                        if len(txs) == 1:
                            tx = txs[0]
                            fee_str = f"  Fee: {tx.fee:,.0f}¥" if tx.fee > 0 else ""
                            st.success(
                                f"Buy complete ✓  {tx.quantity:,d} shares @ {fmt_price(tx.price)}"
                                f" = {fmt_price(tx.total_amount)}{fee_str}"
                            )
                        else:
                            lot_tx, sunit_tx = txs[0], txs[1]
                            st.success(
                                f"Buy complete ✓  Regular {lot_tx.quantity:,d} shares + "
                                f"**S-share {sunit_tx.quantity:,d} shares** @ {fmt_price(lot_tx.price)}"
                            )
                        st.rerun()
                    except InsufficientFundsError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"Error: {e}")

        with sell_tab:
            positions = PortfolioService().get_positions()
            pos = next((p for p in positions if p.ticker == ticker), None)

            if pos is None:
                st.info("No holdings for this stock.")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Holdings", f"{pos.quantity:,d} shares")
                c2.metric("Avg. Cost", fmt_price(pos.avg_buy_price))
                c3.metric(
                    "Unrealized P&L",
                    fmt_price(pos.unrealized_pnl),
                    delta=f"{pos.unrealized_pnl_rate:+.2f}%",
                )

                with st.form("sell_form"):
                    qty = st.number_input(
                        "Qty to Sell (shares)",
                        min_value=1,
                        max_value=pos.quantity,
                        value=pos.quantity,
                        step=1,
                    )
                    memo = st.text_area("Memo", placeholder="Reason, review, etc.")
                    tags = st.text_input("Tags (comma-separated)", placeholder="e.g. take-profit, cut-loss")

                    exp_pnl = (current_price - pos.avg_buy_price) * int(qty)
                    if is_us:
                        usd_jpy_est = price_svc.get_usd_jpy_rate()
                        exp_pnl_jpy = exp_pnl * usd_jpy_est
                        exp_fee_jpy = min(current_price * int(qty) * 0.00495, 22.0) * usd_jpy_est
                    else:
                        exp_pnl_jpy = exp_pnl
                        exp_fee_jpy = 0.0
                    exp_tax = max(0.0, exp_pnl_jpy) * _TAX_RATE
                    exp_net = exp_pnl_jpy - exp_fee_jpy - exp_tax

                    st.caption(
                        f"Est. Realized P&L: {exp_pnl_jpy:+,.0f}¥  "
                        f"Fee: {exp_fee_jpy:,.0f}¥  "
                        f"Tax: {exp_tax:,.0f}¥  "
                        f"**Net P&L: {exp_net:+,.0f}¥**"
                    )

                    if st.form_submit_button(
                        "Execute Sell Order", width="stretch", type="primary"
                    ):
                        try:
                            tx = TradeService().sell(
                                ticker, int(qty), memo=memo or None, tags=tags or None
                            )
                            net = (tx.realized_pnl or 0) - tx.fee - tx.tax
                            st.success(
                                f"Sell complete ✓  {tx.quantity:,d} shares @ {fmt_price(tx.price)}  "
                                f"Realized P&L: {tx.realized_pnl:+,.0f}¥  "
                                f"Fee: {tx.fee:,.0f}¥  Tax: {tx.tax:,.0f}¥  "
                                f"**Net: {net:+,.0f}¥**"
                            )
                            st.rerun()
                        except InsufficientSharesError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"Error: {e}")

    except (StockNotFoundError, PriceNotAvailableError) as e:
        st.error(f"Price fetch error: {e}")

bottom_nav()
