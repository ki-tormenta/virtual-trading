import streamlit as st
import plotly.graph_objects as go

from config.ui_theme import inject_styles, bottom_nav, COLOR_PROFIT, PLOTLY_FONT, PLOTLY_BG
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
st.title("🔍 売買")

if "trade_ticker" not in st.session_state:
    st.session_state.trade_ticker = None
if "trade_stock_name" not in st.session_state:
    st.session_state.trade_stock_name = None

# --- 銘柄検索 ---
col1, col2 = st.columns([4, 1])
with col1:
    code_input = st.text_input(
        "銘柄コード",
        placeholder="例: 7203（トヨタ）/ AAPL（Apple）",
        label_visibility="collapsed",
    )
with col2:
    search_btn = st.button("🔍 検索", width="stretch")

if search_btn and code_input:
    ticker = normalize_ticker(code_input)
    with st.spinner("銘柄情報を取得中..."):
        try:
            stock = PriceService().get_or_register_stock(ticker)
            st.session_state.trade_ticker = ticker
            st.session_state.trade_stock_name = stock.name
        except (StockNotFoundError, PriceNotAvailableError) as e:
            st.error(f"銘柄が見つかりません: {e}")
            st.session_state.trade_ticker = None

# --- 銘柄情報・売買フォーム ---
if st.session_state.trade_ticker:
    ticker: str = st.session_state.trade_ticker
    is_jp = ticker.endswith(".T")
    is_us = not is_jp
    currency = "円" if is_jp else "USD"

    def fmt_price(p: float) -> str:
        return f"{p:,.0f}円" if is_jp else f"${p:,.2f}"

    try:
        price_svc = PriceService()
        current_price = price_svc.get_close_price(ticker)

        st.subheader(f"{st.session_state.trade_stock_name}（{ticker}）")
        st.metric("終値", fmt_price(current_price))

        # 株価チャート（期間選択）
        _PERIODS = {"1週間": "5d", "1ヶ月": "1mo", "3ヶ月": "3mo", "1年": "1y", "3年": "3y"}
        period_label = st.radio(
            "期間",
            list(_PERIODS.keys()),
            index=3,
            horizontal=True,
            label_visibility="collapsed",
        )
        period = _PERIODS[period_label]
        df = price_svc.get_price_history(ticker, period=period)
        fig = go.Figure(
            go.Scatter(
                x=df.index,
                y=df["Close"],
                mode="lines",
                line=dict(color=COLOR_PROFIT, width=1.5),
            )
        )
        fig.update_layout(
            title=f"株価チャート（{period_label}・終値）",
            xaxis_title="日付",
            yaxis_title=f"終値（{currency}）",
            height=360,
            font=dict(family=PLOTLY_FONT),
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor=PLOTLY_BG,
            paper_bgcolor=PLOTLY_BG,
        )
        st.plotly_chart(fig, use_container_width=True)

        buy_tab, sell_tab = st.tabs(["📈 買付", "📉 売却"])

        # ── 買付タブ ──────────────────────────────────────────────────────
        with buy_tab:
            with st.form("buy_form"):
                qty = st.number_input("数量（株）", min_value=1, value=100, step=1)
                memo = st.text_area("メモ", placeholder="売買理由、将来の見通しなど")
                tags = st.text_input("タグ（カンマ区切り）", placeholder="例: グロース,長期保有")

                # 費用概算
                subtotal = current_price * qty
                if is_jp:
                    lot_q = (int(qty) // 100) * 100
                    sunit_q = int(qty) % 100
                    if sunit_q > 0 and lot_q > 0:
                        st.caption(
                            f"必要資金: {subtotal:,.0f}円  "
                            f"（通常株 {lot_q}株 + **S株 {sunit_q}株** に分割されます）"
                        )
                    elif sunit_q > 0:
                        st.caption(f"必要資金: {subtotal:,.0f}円（**S株**として処理）")
                    else:
                        st.caption(f"必要資金: {subtotal:,.0f}円")
                else:
                    fee_est = min(subtotal * 0.00495, 22.0)
                    st.caption(
                        f"必要資金: ${subtotal:,.2f}  （+ 手数料 ${fee_est:.2f}、合計 ${subtotal + fee_est:,.2f}）"
                    )

                if st.form_submit_button("買付注文を実行", width="stretch", type="primary"):
                    try:
                        txs = TradeService().buy(
                            ticker, int(qty), memo=memo or None, tags=tags or None
                        )
                        if len(txs) == 1:
                            tx = txs[0]
                            fee_str = f"  手数料: {tx.fee:,.0f}円" if tx.fee > 0 else ""
                            st.success(
                                f"買付完了 ✓  {tx.quantity:,d}株 @ {fmt_price(tx.price)}"
                                f" = {fmt_price(tx.total_amount)}{fee_str}"
                            )
                        else:
                            lot_tx, sunit_tx = txs[0], txs[1]
                            st.success(
                                f"買付完了 ✓  通常株 {lot_tx.quantity:,d}株 + "
                                f"**S株 {sunit_tx.quantity:,d}株** @ {fmt_price(lot_tx.price)}"
                            )
                        st.rerun()
                    except InsufficientFundsError as e:
                        st.error(str(e))
                    except Exception as e:
                        st.error(f"エラー: {e}")

        # ── 売却タブ ──────────────────────────────────────────────────────
        with sell_tab:
            positions = PortfolioService().get_positions()
            pos = next((p for p in positions if p.ticker == ticker), None)

            if pos is None:
                st.info("この銘柄の保有はありません。")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("保有数量", f"{pos.quantity:,d}株")
                c2.metric("平均取得単価", fmt_price(pos.avg_buy_price))
                c3.metric(
                    "含み損益",
                    fmt_price(pos.unrealized_pnl),
                    delta=f"{pos.unrealized_pnl_rate:+.2f}%",
                )

                with st.form("sell_form"):
                    qty = st.number_input(
                        "売却数量（株）",
                        min_value=1,
                        max_value=pos.quantity,
                        value=pos.quantity,
                        step=1,
                    )
                    memo = st.text_area("メモ", placeholder="売却理由、振り返りなど")
                    tags = st.text_input("タグ（カンマ区切り）", placeholder="例: 利確,損切り")

                    # 売却時の費用内訳
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
                        f"予想実現損益: {exp_pnl_jpy:+,.0f}円  "
                        f"手数料: {exp_fee_jpy:,.0f}円  "
                        f"税金: {exp_tax:,.0f}円  "
                        f"**手取り損益: {exp_net:+,.0f}円**"
                    )

                    if st.form_submit_button(
                        "売却注文を実行", width="stretch", type="primary"
                    ):
                        try:
                            tx = TradeService().sell(
                                ticker, int(qty), memo=memo or None, tags=tags or None
                            )
                            net = (tx.realized_pnl or 0) - tx.fee - tx.tax
                            st.success(
                                f"売却完了 ✓  {tx.quantity:,d}株 @ {fmt_price(tx.price)}  "
                                f"実現損益: {tx.realized_pnl:+,.0f}円  "
                                f"手数料: {tx.fee:,.0f}円  税金: {tx.tax:,.0f}円  "
                                f"**手取り: {net:+,.0f}円**"
                            )
                            st.rerun()
                        except InsufficientSharesError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"エラー: {e}")

    except (StockNotFoundError, PriceNotAvailableError) as e:
        st.error(f"株価取得エラー: {e}")

bottom_nav()
