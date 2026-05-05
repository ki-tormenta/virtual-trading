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
st.title("🎮 シミュレーション")
st.caption("仮の口座で取引をシミュレートできます。実際の資産には影響しません。")

_SIM = "simulation"

tab_trade, tab_positions, tab_history = st.tabs(["📈 売買", "📋 ポジション", "📜 履歴"])

# ── 売買タブ ─────────────────────────────────────────────────────────────────
with tab_trade:
    if "sim_ticker" not in st.session_state:
        st.session_state.sim_ticker = None
    if "sim_stock_name" not in st.session_state:
        st.session_state.sim_stock_name = None

    col1, col2 = st.columns([4, 1])
    with col1:
        code_input = st.text_input(
            "銘柄コード",
            placeholder="例: 7203（トヨタ）/ AAPL（Apple）",
            label_visibility="collapsed",
            key="sim_code_input",
        )
    with col2:
        search_btn = st.button("🔍 検索", key="sim_search_btn", width="stretch")

    if search_btn and code_input:
        ticker = normalize_ticker(code_input)
        with st.spinner("銘柄情報を取得中..."):
            try:
                stock = PriceService().get_or_register_stock(ticker)
                st.session_state.sim_ticker = ticker
                st.session_state.sim_stock_name = stock.name
            except (StockNotFoundError, PriceNotAvailableError) as e:
                st.error(f"銘柄が見つかりません: {e}")
                st.session_state.sim_ticker = None

    if st.session_state.sim_ticker:
        ticker: str = st.session_state.sim_ticker
        is_jp = ticker.endswith(".T")
        currency = "円" if is_jp else "USD"

        def fmt_price(p: float) -> str:
            return f"{p:,.0f}円" if is_jp else f"${p:,.2f}"

        try:
            price_svc = PriceService()
            current_price = price_svc.get_close_price(ticker)

            st.subheader(f"{st.session_state.sim_stock_name}（{ticker}）")
            st.metric("終値", fmt_price(current_price))

            _PERIODS = {"1週間": "5d", "1ヶ月": "1mo", "3ヶ月": "3mo", "1年": "1y", "3年": "3y"}
            period_label = st.radio(
                "期間", list(_PERIODS.keys()), index=3, horizontal=True,
                label_visibility="collapsed", key="sim_period",
            )
            df = price_svc.get_price_history(ticker, period=_PERIODS[period_label])
            fig = go.Figure(go.Scatter(
                x=df.index, y=df["Close"], mode="lines",
                line=dict(color=COLOR_PROFIT, width=1.5),
            ))
            fig.update_layout(
                title=f"株価チャート（{period_label}・終値）",
                xaxis_title="日付", yaxis_title=f"終値（{currency}）",
                height=300, font=dict(family=PLOTLY_FONT),
                margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
            )
            st.plotly_chart(fig, use_container_width=True)

            buy_tab, sell_tab = st.tabs(["📈 買付", "📉 売却"])

            with buy_tab:
                with st.form("sim_buy_form"):
                    qty = st.number_input("数量（株）", min_value=1, value=100, step=1, key="sim_buy_qty")
                    memo = st.text_area("メモ", placeholder="シミュレーション理由など", key="sim_buy_memo")
                    tags = st.text_input("タグ", placeholder="例: 検証,グロース", key="sim_buy_tags")

                    subtotal = current_price * qty
                    if is_jp:
                        st.caption(f"必要資金: {subtotal:,.0f}円")
                    else:
                        fee_est = min(subtotal * 0.00495, 22.0)
                        st.caption(f"必要資金: ${subtotal:,.2f}（+ 手数料 ${fee_est:.2f}）")

                    if st.form_submit_button("買付注文を実行", width="stretch", type="primary"):
                        try:
                            txs = TradeService(account_type=_SIM).buy(
                                ticker, int(qty), memo=memo or None, tags=tags or None
                            )
                            tx = txs[0]
                            st.success(f"買付完了 ✓  {tx.quantity:,d}株 @ {fmt_price(tx.price)}")
                            st.rerun()
                        except InsufficientFundsError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"エラー: {e}")

            with sell_tab:
                positions = PortfolioService(account_type=_SIM).get_positions()
                pos = next((p for p in positions if p.ticker == ticker), None)

                if pos is None:
                    st.info("この銘柄の保有はありません。")
                else:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("保有数量", f"{pos.quantity:,d}株")
                    c2.metric("平均取得単価", fmt_price(pos.avg_buy_price))
                    c3.metric("含み損益", fmt_price(pos.unrealized_pnl),
                              delta=f"{pos.unrealized_pnl_rate:+.2f}%")

                    with st.form("sim_sell_form"):
                        qty = st.number_input(
                            "売却数量（株）", min_value=1, max_value=pos.quantity,
                            value=pos.quantity, step=1, key="sim_sell_qty",
                        )
                        memo = st.text_area("メモ", placeholder="振り返りなど", key="sim_sell_memo")

                        exp_pnl = (current_price - pos.avg_buy_price) * int(qty)
                        exp_tax = max(0.0, exp_pnl) * _TAX_RATE
                        st.caption(f"予想実現損益: {exp_pnl:+,.0f}円  税金: {exp_tax:,.0f}円")

                        if st.form_submit_button("売却注文を実行", width="stretch", type="primary"):
                            try:
                                tx = TradeService(account_type=_SIM).sell(
                                    ticker, int(qty), memo=memo or None
                                )
                                st.success(
                                    f"売却完了 ✓  {tx.quantity:,d}株 @ {fmt_price(tx.price)}  "
                                    f"実現損益: {tx.realized_pnl:+,.0f}円"
                                )
                                st.rerun()
                            except InsufficientSharesError as e:
                                st.error(str(e))
                            except Exception as e:
                                st.error(f"エラー: {e}")

        except (StockNotFoundError, PriceNotAvailableError) as e:
            st.error(f"株価取得エラー: {e}")

# ── ポジションタブ ────────────────────────────────────────────────────────────
with tab_positions:
    try:
        sim_psvc = PortfolioService(account_type=_SIM)
        sim_summary = sim_psvc.get_summary()

        c1, c2, c3 = st.columns(3)
        c1.metric("現金残高", f"¥{sim_summary.current_cash:,.0f}")
        c2.metric("評価額合計", f"¥{sim_summary.market_value:,.0f}")
        c3.metric("総合損益", f"¥{sim_summary.total_pnl:+,.0f}",
                  delta=f"{sim_summary.total_pnl_rate:+.2f}%")

        positions = sim_psvc.get_positions()
        if not positions:
            st.info("シミュレーション口座に保有銘柄はありません。売買タブから購入してください。")
        else:
            view = st.radio("表示モード", ["シンプル", "詳細"], horizontal=True,
                            label_visibility="collapsed", key="sim_pos_view")
            rows_simple, rows_detail = [], []
            for p in positions:
                is_jp = p.market == "JP"
                currency = "円" if is_jp else "USD"
                rows_simple.append({
                    "銘柄名": p.name,
                    "評価額(円)": f"{p.market_value_jpy:,.0f}円",
                    "含み損益(円)": f"{p.unrealized_pnl_jpy:+,.0f}円",
                    "損益率": f"{p.unrealized_pnl_rate:+.2f}%",
                })
                rows_detail.append({
                    "銘柄名": p.name,
                    "ティッカー": p.ticker,
                    "市場": p.market,
                    "数量": f"{p.quantity:,d}株",
                    "平均取得単価": f"{p.avg_buy_price:,.0f}{currency}" if is_jp else f"${p.avg_buy_price:,.2f}",
                    "現在値": f"{p.current_price:,.0f}{currency}" if is_jp else f"${p.current_price:,.2f}",
                    "含み損益(円)": f"{p.unrealized_pnl_jpy:+,.0f}円",
                    "損益率": f"{p.unrealized_pnl_rate:+.2f}%",
                })
            df = pd.DataFrame(rows_simple if view == "シンプル" else rows_detail)
            st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"データ取得エラー: {e}")

# ── 履歴タブ ──────────────────────────────────────────────────────────────────
with tab_history:
    try:
        with st.expander("🔍 フィルタ", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                type_filter = st.selectbox("種別", ["全て", "買付（BUY）", "売却（SELL）"],
                                           key="sim_type_filter")
                ticker_input = st.text_input("銘柄コード", placeholder="例: 7203 / AAPL",
                                             key="sim_ticker_filter")
            with col2:
                from_date = st.date_input("開始日", value=date.today() - timedelta(days=90),
                                          key="sim_from_date")
                to_date = st.date_input("終了日", value=date.today(), key="sim_to_date")

        trade_type = None
        if type_filter == "買付（BUY）":
            trade_type = "BUY"
        elif type_filter == "売却（SELL）":
            trade_type = "SELL"

        ticker_f = normalize_ticker(ticker_input) if ticker_input.strip() else None
        records = PortfolioService(account_type=_SIM).get_transaction_records(
            ticker=ticker_f, from_date=from_date, to_date=to_date, trade_type=trade_type,
        )

        if not records:
            st.info("該当する取引履歴がありません。")
        else:
            st.caption(f"{len(records)}件")
            rows = []
            for r in records:
                is_jp = r.market == "JP"
                currency = "円" if is_jp else "USD"
                rows.append({
                    "日付": r.transaction_date.strftime("%Y-%m-%d"),
                    "種別": "買付" if r.type == "BUY" else "売却",
                    "銘柄名": r.stock_name,
                    "数量": f"{r.quantity:,d}株",
                    "価格": f"{r.price:,.0f}{currency}" if is_jp else f"${r.price:,.2f}",
                    "実現損益(円)": f"{r.realized_pnl:+,.0f}円" if r.realized_pnl is not None else "-",
                    "メモ": r.memo or "",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"データ取得エラー: {e}")

bottom_nav()
