from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.ui_theme import inject_styles, bottom_nav, COLOR_PROFIT, COLOR_LOSS, PLOTLY_FONT, PLOTLY_BG, PLOTLY_GRID, PLOTLY_TICK_COLOR
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
st.title("🤖 AI Simulation")
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

# Shared state computed once — used across multiple tabs
_usd_jpy_rate = PriceService().get_usd_jpy_rate()
_today = date.today()
st.caption(f"💱 USD/JPY  **{_usd_jpy_rate:,.2f}**")

try:
    _sim_summary = psvc.get_summary()
except Exception:
    _sim_summary = None

tab_trade, tab_positions, tab_history, tab_analytics = st.tabs(
    ["📈 Trade", "📋 Positions", "📜 History", "📊 Analytics"]
)


# ---------------------------------------------------------------------------
# Cached helpers — yfinance external data (not DB data)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_analytics(ticker: str) -> dict:
    return PriceService().get_ticker_analytics(ticker)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_close_series(ticker: str) -> pd.Series | None:
    try:
        df = PriceService().get_price_history(ticker, period="2y")
        return df["Close"]
    except Exception:
        return None


def _lookup_rate(series: pd.Series | None, target: date) -> float | None:
    """seriesから target 日以前の直近レートを返す。"""
    if series is None:
        return None
    ts = pd.Timestamp(target)
    avail = series[series.index <= ts]
    return float(avail.iloc[-1]) if not avail.empty else None


# ---------------------------------------------------------------------------
# Tab: Trade
# ---------------------------------------------------------------------------

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
            df_chart = price_svc.get_price_history(
                ticker, period=_PERIODS[period_label], include_ohlcv=True
            )
            fig = go.Figure()
            if all(c in df_chart.columns for c in ["Open", "High", "Low", "Close"]):
                fig.add_trace(go.Candlestick(
                    x=df_chart.index,
                    open=df_chart["Open"], high=df_chart["High"],
                    low=df_chart["Low"], close=df_chart["Close"],
                    name="Price",
                    increasing=dict(line=dict(color=COLOR_PROFIT, width=1),
                                    fillcolor="rgba(0,212,170,0.25)"),
                    decreasing=dict(line=dict(color=COLOR_LOSS, width=1),
                                    fillcolor="rgba(255,71,87,0.25)"),
                    showlegend=False,
                ))
            else:
                fig.add_trace(go.Scatter(
                    x=df_chart.index, y=df_chart["Close"], mode="lines",
                    line=dict(color=COLOR_PROFIT, width=1.5),
                ))
            close_s = df_chart["Close"]
            if len(close_s) >= 25:
                fig.add_trace(go.Scatter(
                    x=df_chart.index, y=close_s.rolling(25).mean(),
                    mode="lines", name="MA25",
                    line=dict(color="#4299e1", width=1.2, dash="dot"),
                ))
            if len(close_s) >= 75:
                fig.add_trace(go.Scatter(
                    x=df_chart.index, y=close_s.rolling(75).mean(),
                    mode="lines", name="MA75",
                    line=dict(color="#f6c90e", width=1.2, dash="dot"),
                ))
            tick_pfx = "¥" if is_jp else "$"
            fig.update_layout(
                title=f"Price Chart ({period_label} · OHLC)",
                xaxis_title="Date", yaxis_title=f"Price ({currency})",
                height=300,
                font=dict(family=PLOTLY_FONT, color=PLOTLY_TICK_COLOR),
                margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
                xaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID,
                           rangeslider=dict(visible=False),
                           showline=False, zeroline=False),
                yaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID,
                           showline=False, zeroline=False, tickprefix=tick_pfx),
                legend=dict(orientation="h", y=-0.14, font=dict(size=10)),
                hovermode="x unified",
                dragmode="pan",
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"scrollZoom": True, "displayModeBar": False})

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


# ---------------------------------------------------------------------------
# Tab: Positions
# ---------------------------------------------------------------------------

with tab_positions:
    if _sim_summary is None:
        st.error("Failed to load portfolio data.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Cash Balance", f"¥{_sim_summary.current_cash:,.0f}")
        c2.metric("Total Value", f"¥{_sim_summary.market_value:,.0f}")
        c3.metric("Total P&L", f"¥{_sim_summary.total_pnl:+,.0f}",
                  delta=f"{_sim_summary.total_pnl_rate:+.2f}%")
        c4.metric("USD/JPY", f"{_usd_jpy_rate:,.2f}")

        try:
            positions = psvc.get_positions()
            if not positions:
                st.info("No positions. Buy from the Trade tab.")
            else:
                view = st.radio("View", ["Simple", "Detail"], horizontal=True,
                                label_visibility="collapsed", key="sim_pos_view")
                rows_s, rows_d = [], []
                for p in positions:
                    is_jp_p = p.market == "JP"
                    rows_s.append({
                        "Name": p.name,
                        "Value (JPY)": f"{p.market_value_jpy:,.0f}¥",
                        "Unrealized P&L (JPY)": f"{p.unrealized_pnl_jpy:+,.0f}¥",
                        "P&L %": f"{p.unrealized_pnl_rate:+.2f}%",
                    })
                    days_held = (_today - p.first_buy_date).days if p.first_buy_date else None
                    rows_d.append({
                        "Name": p.name,
                        "Ticker": p.ticker,
                        "Market": p.market,
                        "Qty": f"{p.quantity:,d} shares",
                        "Since": p.first_buy_date.strftime("%Y-%m-%d") if p.first_buy_date else "N/A",
                        "Days Held": f"{days_held}d" if days_held is not None else "N/A",
                        "Avg. Cost": f"{p.avg_buy_price:,.0f}¥" if is_jp_p else f"${p.avg_buy_price:,.2f}",
                        "Current Price": f"{p.current_price:,.0f}¥" if is_jp_p else f"${p.current_price:,.2f}",
                        "Unrealized P&L (JPY)": f"{p.unrealized_pnl_jpy:+,.0f}¥",
                        "P&L %": f"{p.unrealized_pnl_rate:+.2f}%",
                    })
                st.dataframe(pd.DataFrame(rows_s if view == "Simple" else rows_d),
                             use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Data fetch error: {e}")


# ---------------------------------------------------------------------------
# Tab: History
# ---------------------------------------------------------------------------

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
                from_date = st.date_input("From", value=_today - timedelta(days=90),
                                          key="sim_from_date")
                to_date = st.date_input("To", value=_today, key="sim_to_date")

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


# ---------------------------------------------------------------------------
# AI Prompt builder
# ---------------------------------------------------------------------------

def _build_ai_prompt(
    summary,
    positions: list,
    analytics_map: dict,
    sharpe: float | None,
    usd_jpy: float,
    usdjpy_series: "pd.Series | None",
    earnings_rows: list[dict],
    today: date,
) -> str:
    lines: list[str] = []

    lines.append("【ポートフォリオ基本情報】")
    if summary is not None:
        lines.append(f"キャッシュ: ¥{summary.current_cash:,.0f}")
        lines.append(f"総資産: ¥{summary.total_assets:,.0f}")
    lines.append(f"シャープレシオ: {sharpe:.2f}" if sharpe is not None else "シャープレシオ: N/A（スナップショット不足）")
    lines.append(f"USD/JPY: {usd_jpy:,.2f}")
    lines.append("")

    lines.append("【ポジション】")
    lines.append("銘柄 | 保有数 | 買値 | 現値 | 損益% | 保有日数 | β | 目標株価 | Upside")
    for p in positions:
        a = analytics_map.get(p.ticker, {})
        beta = a.get("beta")
        target = a.get("target_mean_price")
        days = (_today - p.first_buy_date).days if p.first_buy_date else None

        avg_s = f"¥{p.avg_buy_price:,.0f}" if p.market == "JP" else f"${p.avg_buy_price:,.2f}"
        cur_s = f"¥{p.current_price:,.0f}" if p.market == "JP" else f"${p.current_price:,.2f}"
        tgt_s = (f"¥{target:,.0f}" if p.market == "JP" else f"${target:,.2f}") if target else "-"
        up_s = f"{(target / p.current_price - 1) * 100:+.1f}%" if (target and p.current_price) else "-"
        beta_s = f"{beta:.2f}" if beta is not None else "-"
        days_s = f"{days}日" if days is not None else "-"
        code = p.ticker.replace(".T", "")

        lines.append(f"{code} | {p.quantity:,d}株 | {avg_s} | {cur_s} | {p.unrealized_pnl_rate:+.2f}% | {days_s} | {beta_s} | {tgt_s} | {up_s}")
    lines.append("")

    # FX breakdown for US stocks
    us_fx: list[str] = []
    for p in positions:
        if p.market != "US" or p.first_buy_date is None:
            continue
        buy_rate = _lookup_rate(usdjpy_series, p.first_buy_date)
        if buy_rate is None:
            continue
        stock_pnl_jpy = p.unrealized_pnl * buy_rate
        fx_pnl_jpy = p.unrealized_pnl * (usd_jpy - buy_rate)
        us_fx.append(
            f"{p.ticker}: 購入時レート {buy_rate:.2f}  株価損益 {stock_pnl_jpy:+,.0f}¥ / 為替損益 {fx_pnl_jpy:+,.0f}¥"
        )
    if us_fx:
        lines.append(f"【為替影響（USD/JPY現在: {usd_jpy:,.2f}）】")
        lines.extend(us_fx)
        lines.append("")

    if earnings_rows:
        lines.append("【次の決算】")
        for row in earnings_rows[:6]:
            lines.append(f"{row['Name']}: {row['Next Earnings']}（{row['Days Until']}日後）")
        lines.append("")

    news_lines: list[str] = []
    for p in positions:
        for item in (analytics_map.get(p.ticker, {}).get("news") or [])[:1]:
            title = item.get("title", "")
            if title:
                news_lines.append(f"- {p.ticker.replace('.T', '')}: {title}")
    if news_lines:
        lines.append("【注目ニュース】")
        lines.extend(news_lines[:8])
        lines.append("")

    lines.append("【質問】")
    lines.append("今日のアクションを優先度順に教えて")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tab: Analytics
# ---------------------------------------------------------------------------

with tab_analytics:
    try:
        positions_all = psvc.get_positions()
    except Exception as e:
        st.error(f"Data fetch error: {e}")
        positions_all = []

    if not positions_all:
        st.info("No positions to analyze. Add trades in the Trade tab.")
    else:
        tickers_held = [p.ticker for p in positions_all]
        name_map = {p.ticker: p.name for p in positions_all}

        with st.spinner("Loading market data..."):
            analytics_map = {t: _fetch_analytics(t) for t in tickers_held}
            usdjpy_series = _fetch_close_series("USDJPY=X")

        # ----------------------------------------------------------------
        # Portfolio Risk
        # ----------------------------------------------------------------
        st.subheader("📊 Portfolio Risk")

        sharpe = psvc.get_sharpe_ratio()
        col_sh, _pad = st.columns([1, 3])
        with col_sh:
            if sharpe is not None:
                st.metric("Sharpe Ratio (annualized)", f"{sharpe:.2f}")
            else:
                st.metric("Sharpe Ratio", "N/A", help="Requires 10+ days of snapshot history")

        if len(tickers_held) >= 2:
            st.markdown("**Return Correlation (1Y)**")
            price_frames: dict[str, pd.Series] = {}
            for t in tickers_held:
                s = _fetch_close_series(t)
                if s is not None:
                    price_frames[name_map.get(t, t)] = s.pct_change().dropna()

            if len(price_frames) >= 2:
                corr = pd.DataFrame(price_frames).dropna().corr()
                fig_corr = go.Figure(go.Heatmap(
                    z=corr.values,
                    x=corr.columns.tolist(),
                    y=corr.index.tolist(),
                    colorscale="RdBu_r",
                    zmin=-1, zmax=1,
                    text=[[f"{v:.2f}" for v in row] for row in corr.values],
                    texttemplate="%{text}",
                    hovertemplate="%{y} × %{x}: %{z:.2f}<extra></extra>",
                ))
                fig_corr.update_layout(
                    height=max(250, len(tickers_held) * 80),
                    margin=dict(l=0, r=0, t=10, b=0),
                    font=dict(family=PLOTLY_FONT, color=PLOTLY_TICK_COLOR),
                    paper_bgcolor=PLOTLY_BG, plot_bgcolor=PLOTLY_BG,
                )
                st.plotly_chart(fig_corr, use_container_width=True,
                                config={"displayModeBar": False})
        else:
            st.info("Add 2+ positions to see correlation matrix.")

        st.divider()

        # ----------------------------------------------------------------
        # Holdings & Signals — 保有日数 + β + アナリスト情報の統合テーブル
        # ----------------------------------------------------------------
        st.subheader("🔍 Holdings & Signals")
        st.caption("Days · P&L% で時間効率を確認。β・目標株価・Upside は yfinance が提供する場合のみ表示。")

        holdings_rows = []
        for p in positions_all:
            a = analytics_map.get(p.ticker, {})
            beta = a.get("beta")
            target = a.get("target_mean_price")
            days = (_today - p.first_buy_date).days if p.first_buy_date else None

            # "17d · +10.1%" 形式で時間効率を一目で把握できるよう結合
            days_pnl = (
                f"{days}d · {p.unrealized_pnl_rate:+.2f}%"
                if days is not None
                else f"{p.unrealized_pnl_rate:+.2f}%"
            )
            avg_s = f"¥{p.avg_buy_price:,.0f}" if p.market == "JP" else f"${p.avg_buy_price:,.2f}"
            cur_s = f"¥{p.current_price:,.0f}" if p.market == "JP" else f"${p.current_price:,.2f}"
            tgt_s = (f"¥{target:,.0f}" if p.market == "JP" else f"${target:,.2f}") if target else "N/A"
            up_s = f"{(target / p.current_price - 1) * 100:+.1f}%" if (target and p.current_price) else "N/A"

            holdings_rows.append({
                "Name": p.name,
                "Qty": f"{p.quantity:,d}",
                "Avg Cost": avg_s,
                "Current": cur_s,
                "Days · P&L%": days_pnl,
                "β": f"{beta:.2f}" if beta is not None else "N/A",
                "Target": tgt_s,
                "Upside": up_s,
            })

        st.dataframe(pd.DataFrame(holdings_rows), use_container_width=True, hide_index=True)

        # ----------------------------------------------------------------
        # FX Breakdown — 株価損益と為替損益の分離（米国株のみ）
        # ----------------------------------------------------------------
        us_positions_with_date = [
            p for p in positions_all
            if p.market == "US" and p.first_buy_date is not None
        ]
        if us_positions_with_date:
            st.divider()
            st.subheader("💱 FX Breakdown")
            st.caption(
                f"USD/JPY 現在 **{_usd_jpy_rate:,.2f}**  ／  "
                "購入時レートと現在レートの差から株価損益・為替損益を分離"
            )

            fx_rows = []
            for p in us_positions_with_date:
                buy_rate = _lookup_rate(usdjpy_series, p.first_buy_date)
                if buy_rate is None:
                    continue
                # 分解: 株価損益 = USD損益 × 購入時レート、為替損益 = USD損益 × レート変化分
                stock_pnl_jpy = p.unrealized_pnl * buy_rate
                fx_pnl_jpy = p.unrealized_pnl * (_usd_jpy_rate - buy_rate)
                rate_delta = _usd_jpy_rate - buy_rate
                fx_rows.append({
                    "Name": p.name,
                    "P&L (USD)": f"${p.unrealized_pnl:+,.2f}",
                    "Rate Buy→Now": f"{buy_rate:.2f} → {_usd_jpy_rate:.2f}  ({rate_delta:+.2f})",
                    "Stock P&L (¥)": f"{stock_pnl_jpy:+,.0f}¥",
                    "FX Effect (¥)": f"{fx_pnl_jpy:+,.0f}¥",
                    "Total P&L (¥)": f"{p.unrealized_pnl_jpy:+,.0f}¥",
                })

            if fx_rows:
                st.dataframe(pd.DataFrame(fx_rows), use_container_width=True, hide_index=True)

        st.divider()

        # ----------------------------------------------------------------
        # Earnings Calendar
        # ----------------------------------------------------------------
        st.subheader("📅 Earnings Calendar")

        earnings_rows: list[dict] = []
        for p in positions_all:
            ed = analytics_map.get(p.ticker, {}).get("next_earnings_date")
            if ed is not None:
                earnings_rows.append({
                    "Name": p.name,
                    "Ticker": p.ticker,
                    "Next Earnings": ed.strftime("%Y-%m-%d"),
                    "Days Until": (ed - _today).days,
                })

        if earnings_rows:
            earnings_rows.sort(key=lambda x: x["Days Until"])
            st.dataframe(pd.DataFrame(earnings_rows), use_container_width=True, hide_index=True)
        else:
            st.info("No upcoming earnings data (JP stocks may not be available via yfinance).")

        st.divider()

        # ----------------------------------------------------------------
        # News Feed
        # ----------------------------------------------------------------
        st.subheader("📰 News")

        any_news = False
        for p in positions_all:
            news_items = analytics_map.get(p.ticker, {}).get("news", [])
            if not news_items:
                continue
            any_news = True
            st.markdown(f"**{p.name}** ({p.ticker})")
            for item in news_items[:3]:
                title = item.get("title", "")
                link = item.get("link", "")
                publisher = item.get("publisher", "")
                if not title:
                    continue
                pub = f" — {publisher}" if publisher else ""
                st.markdown(f"- [{title}]({link}){pub}" if link else f"- {title}{pub}")

        if not any_news:
            st.info("No news available for current holdings.")

        st.divider()

        # ----------------------------------------------------------------
        # AI Prompt — コピーしてそのまま Claude に貼り付け可能
        # ----------------------------------------------------------------
        st.subheader("🤖 AI Prompt")
        st.caption("ページ読み込みのたびに最新データで更新されます。右上のコピーボタンで Claude に貼り付けてください。")

        prompt_text = _build_ai_prompt(
            summary=_sim_summary,
            positions=positions_all,
            analytics_map=analytics_map,
            sharpe=sharpe,
            usd_jpy=_usd_jpy_rate,
            usdjpy_series=usdjpy_series,
            earnings_rows=earnings_rows,
            today=_today,
        )
        st.code(prompt_text, language="text")

bottom_nav()
