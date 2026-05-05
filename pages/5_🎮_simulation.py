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
st.caption("仮の口座でシナリオ別に投資戦略をシミュレートできます。実際の資産には影響しません。")

_MAX_SCENARIOS = 4
_SIM = "simulation"

# ── シナリオ管理 ──────────────────────────────────────────────────────────────
psvc_base = PortfolioService()
scenarios = psvc_base.get_simulation_scenarios()

col_sel, col_new = st.columns([3, 1])

with col_sel:
    if scenarios:
        selected_scenario = st.selectbox(
            "シナリオ",
            scenarios,
            key="sim_scenario_select",
        )
    else:
        selected_scenario = None
        st.info("シナリオがまだありません。右の「＋ 新規」から作成してください。")

with col_new:
    if len(scenarios) < _MAX_SCENARIOS:
        if st.button("＋ 新規", width="stretch"):
            st.session_state.sim_creating = True
    else:
        st.caption(f"上限 {_MAX_SCENARIOS} / {_MAX_SCENARIOS}")

if st.session_state.get("sim_creating"):
    with st.form("sim_new_scenario_form"):
        new_name = st.text_input(
            "シナリオ名",
            placeholder="例: 高配当戦略、グロース重視",
            max_chars=20,
        )
        c1, c2 = st.columns(2)
        submitted = c1.form_submit_button("作成", type="primary", width="stretch")
        cancelled = c2.form_submit_button("キャンセル", width="stretch")

        if submitted:
            name = new_name.strip()
            if not name:
                st.error("シナリオ名を入力してください")
            elif name in scenarios:
                st.error("同じ名前のシナリオがすでにあります")
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

# ── 選択中シナリオの操作エリア ────────────────────────────────────────────────
psvc = PortfolioService(account_type=_SIM, scenario_name=selected_scenario)

with st.expander("⚙️ シナリオ操作", expanded=False):
    # ── リネーム ──
    with st.form("sim_rename_form"):
        new_name_input = st.text_input(
            "シナリオ名を変更",
            value=selected_scenario,
            max_chars=20,
        )
        if st.form_submit_button("名前を変更", width="stretch"):
            new_name = new_name_input.strip()
            if not new_name:
                st.error("名前を入力してください")
            elif new_name == selected_scenario:
                st.info("変更がありません")
            else:
                try:
                    psvc_base.rename_simulation_scenario(selected_scenario, new_name)
                    st.success(f"「{new_name}」に変更しました")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

    st.divider()

    # ── リセット ──
    st.warning(f"「{selected_scenario}」の全取引・ポジション・スナップショットを削除して初期状態に戻します。")
    if st.button("🔄 このシナリオをリセット", type="primary"):
        st.session_state.sim_confirm_reset = selected_scenario

if st.session_state.get("sim_confirm_reset") == selected_scenario:
    st.error(f"本当に「{selected_scenario}」をリセットしますか？この操作は元に戻せません。")
    c1, c2 = st.columns(2)
    if c1.button("はい、リセットする", type="primary"):
        psvc.reset_portfolio()
        st.session_state.sim_confirm_reset = None
        st.success("リセット完了")
        st.rerun()
    if c2.button("キャンセル"):
        st.session_state.sim_confirm_reset = None
        st.rerun()

st.divider()

tab_trade, tab_positions, tab_history = st.tabs(["📈 売買", "📋 ポジション", "📜 履歴"])

# ── 売買タブ ─────────────────────────────────────────────────────────────────
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
            "銘柄コード",
            placeholder="例: 7203（トヨタ）/ AAPL",
            label_visibility="collapsed",
            key=f"sim_code_{sim_key}",
        )
    with col2:
        if st.button("🔍 検索", key=f"sim_search_{sim_key}", width="stretch"):
            if code_input:
                ticker_norm = normalize_ticker(code_input)
                with st.spinner("銘柄情報を取得中..."):
                    try:
                        stock = PriceService().get_or_register_stock(ticker_norm)
                        st.session_state[ticker_key] = ticker_norm
                        st.session_state[name_key] = stock.name
                    except (StockNotFoundError, PriceNotAvailableError) as e:
                        st.error(f"銘柄が見つかりません: {e}")
                        st.session_state[ticker_key] = None

    if st.session_state[ticker_key]:
        ticker: str = st.session_state[ticker_key]
        is_jp = ticker.endswith(".T")
        currency = "円" if is_jp else "USD"

        def fmt(p: float) -> str:
            return f"{p:,.0f}円" if is_jp else f"${p:,.2f}"

        try:
            price_svc = PriceService()
            current_price = price_svc.get_close_price(ticker)

            st.subheader(f"{st.session_state[name_key]}（{ticker}）")
            st.metric("終値", fmt(current_price))

            _PERIODS = {"1週間": "5d", "1ヶ月": "1mo", "3ヶ月": "3mo", "1年": "1y", "3年": "3y"}
            period_label = st.radio(
                "期間", list(_PERIODS.keys()), index=3, horizontal=True,
                label_visibility="collapsed", key=f"sim_period_{sim_key}",
            )
            df_chart = price_svc.get_price_history(ticker, period=_PERIODS[period_label])
            fig = go.Figure(go.Scatter(
                x=df_chart.index, y=df_chart["Close"], mode="lines",
                line=dict(color=COLOR_PROFIT, width=1.5),
            ))
            fig.update_layout(
                title=f"株価チャート（{period_label}・終値）",
                xaxis_title="日付", yaxis_title=f"終値（{currency}）",
                height=280, font=dict(family=PLOTLY_FONT),
                margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
            )
            st.plotly_chart(fig, use_container_width=True)

            buy_tab, sell_tab = st.tabs(["📈 買付", "📉 売却"])

            with buy_tab:
                with st.form(f"sim_buy_{sim_key}"):
                    qty = st.number_input("数量（株）", min_value=1, value=100, step=1)
                    memo = st.text_area("メモ", placeholder="戦略の根拠など")
                    tags = st.text_input("タグ", placeholder="例: バリュー,長期")

                    subtotal = current_price * qty
                    if is_jp:
                        st.caption(f"必要資金: {subtotal:,.0f}円")
                    else:
                        fee_est = min(subtotal * 0.00495, 22.0)
                        st.caption(f"必要資金: ${subtotal:,.2f}（+ 手数料 ${fee_est:.2f}）")

                    if st.form_submit_button("買付注文を実行", width="stretch", type="primary"):
                        try:
                            txs = TradeService(account_type=_SIM, scenario_name=selected_scenario).buy(
                                ticker, int(qty), memo=memo or None, tags=tags or None
                            )
                            st.success(f"買付完了 ✓  {txs[0].quantity:,d}株 @ {fmt(txs[0].price)}")
                            st.rerun()
                        except InsufficientFundsError as e:
                            st.error(str(e))
                        except Exception as e:
                            st.error(f"エラー: {e}")

            with sell_tab:
                positions = psvc.get_positions()
                pos = next((p for p in positions if p.ticker == ticker), None)
                if pos is None:
                    st.info("この銘柄の保有はありません。")
                else:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("保有数量", f"{pos.quantity:,d}株")
                    c2.metric("平均取得単価", fmt(pos.avg_buy_price))
                    c3.metric("含み損益", fmt(pos.unrealized_pnl),
                              delta=f"{pos.unrealized_pnl_rate:+.2f}%")

                    with st.form(f"sim_sell_{sim_key}"):
                        qty = st.number_input(
                            "売却数量（株）", min_value=1, max_value=pos.quantity,
                            value=pos.quantity, step=1,
                        )
                        memo = st.text_area("メモ", placeholder="振り返りなど")
                        exp_pnl = (current_price - pos.avg_buy_price) * int(qty)
                        exp_tax = max(0.0, exp_pnl) * _TAX_RATE
                        st.caption(f"予想実現損益: {exp_pnl:+,.0f}円  税金: {exp_tax:,.0f}円")

                        if st.form_submit_button("売却注文を実行", width="stretch", type="primary"):
                            try:
                                tx = TradeService(account_type=_SIM, scenario_name=selected_scenario).sell(
                                    ticker, int(qty), memo=memo or None
                                )
                                st.success(
                                    f"売却完了 ✓  {tx.quantity:,d}株 @ {fmt(tx.price)}  "
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
        sim_summary = psvc.get_summary()
        c1, c2, c3 = st.columns(3)
        c1.metric("現金残高", f"¥{sim_summary.current_cash:,.0f}")
        c2.metric("評価額合計", f"¥{sim_summary.market_value:,.0f}")
        c3.metric("総合損益", f"¥{sim_summary.total_pnl:+,.0f}",
                  delta=f"{sim_summary.total_pnl_rate:+.2f}%")

        positions = psvc.get_positions()
        if not positions:
            st.info("保有銘柄はありません。売買タブから購入してください。")
        else:
            view = st.radio("表示モード", ["シンプル", "詳細"], horizontal=True,
                            label_visibility="collapsed", key="sim_pos_view")
            rows_s, rows_d = [], []
            for p in positions:
                is_jp_p = p.market == "JP"
                cur = "円" if is_jp_p else "USD"
                rows_s.append({
                    "銘柄名": p.name,
                    "評価額(円)": f"{p.market_value_jpy:,.0f}円",
                    "含み損益(円)": f"{p.unrealized_pnl_jpy:+,.0f}円",
                    "損益率": f"{p.unrealized_pnl_rate:+.2f}%",
                })
                rows_d.append({
                    "銘柄名": p.name,
                    "ティッカー": p.ticker,
                    "市場": p.market,
                    "数量": f"{p.quantity:,d}株",
                    "平均取得単価": f"{p.avg_buy_price:,.0f}{cur}" if is_jp_p else f"${p.avg_buy_price:,.2f}",
                    "現在値": f"{p.current_price:,.0f}{cur}" if is_jp_p else f"${p.current_price:,.2f}",
                    "含み損益(円)": f"{p.unrealized_pnl_jpy:+,.0f}円",
                    "損益率": f"{p.unrealized_pnl_rate:+.2f}%",
                })
            st.dataframe(pd.DataFrame(rows_s if view == "シンプル" else rows_d),
                         use_container_width=True, hide_index=True)
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
                ticker_input_h = st.text_input("銘柄コード", placeholder="例: 7203 / AAPL",
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

        ticker_f = normalize_ticker(ticker_input_h) if ticker_input_h.strip() else None
        records = psvc.get_transaction_records(
            ticker=ticker_f, from_date=from_date, to_date=to_date, trade_type=trade_type,
        )

        if not records:
            st.info("該当する取引履歴がありません。")
        else:
            st.caption(f"{len(records)}件")
            rows = []
            for r in records:
                is_jp_r = r.market == "JP"
                cur = "円" if is_jp_r else "USD"
                rows.append({
                    "日付": r.transaction_date.strftime("%Y-%m-%d"),
                    "種別": "買付" if r.type == "BUY" else "売却",
                    "銘柄名": r.stock_name,
                    "数量": f"{r.quantity:,d}株",
                    "価格": f"{r.price:,.0f}{cur}" if is_jp_r else f"${r.price:,.2f}",
                    "実現損益(円)": f"{r.realized_pnl:+,.0f}円" if r.realized_pnl is not None else "-",
                    "メモ": r.memo or "",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"データ取得エラー: {e}")

bottom_nav()
