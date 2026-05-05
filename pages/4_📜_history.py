from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config.ui_theme import inject_styles, bottom_nav
from core.auth import require_auth
from core.services.portfolio_service import PortfolioService
from core.services.trade_service import normalize_ticker

inject_styles()
require_auth()
st.title("📜 取引履歴")

try:
    # フィルタ
    with st.expander("🔍 フィルタ", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            type_filter = st.selectbox("種別", ["全て", "買付（BUY）", "売却（SELL）"])
            ticker_input = st.text_input("銘柄コード", placeholder="例: 7203 / AAPL")
            tag_input = st.text_input("タグ", placeholder="例: 成長株")
        with col2:
            from_date = st.date_input("開始日", value=date.today() - timedelta(days=90))
            to_date = st.date_input("終了日", value=date.today())

    trade_type: str | None = None
    if type_filter == "買付（BUY）":
        trade_type = "BUY"
    elif type_filter == "売却（SELL）":
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
                "ティッカー": r.ticker,
                "数量": f"{r.quantity:,d}株",
                "価格": (
                    f"{r.price:,.0f}{currency}" if is_jp else f"${r.price:,.2f}"
                ),
                "合計金額": (
                    f"{r.total_amount:,.0f}{currency}"
                    if is_jp
                    else f"${r.total_amount:,.2f}"
                ),
                "実現損益(円)": (
                    f"{r.realized_pnl:+,.0f}円"
                    if r.realized_pnl is not None
                    else "-"
                ),
                "手数料(円)": f"{r.fee:,.0f}円" if r.fee else "-",
                "税金(円)": f"{r.tax:,.0f}円" if r.tax else "-",
                "メモ": r.memo or "",
                "タグ": r.tags or "",
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        # メモ編集
        st.divider()
        with st.expander("✏️ メモを編集"):
            options = {
                f"{r.transaction_date.strftime('%Y-%m-%d')} "
                f"{'買付' if r.type == 'BUY' else '売却'} "
                f"{r.stock_name} {r.quantity:,}株": r
                for r in records
            }
            selected_label = st.selectbox("取引を選択", list(options.keys()))
            selected_record = options[selected_label]
            new_memo = st.text_area("メモ", value=selected_record.memo or "", height=100)
            if st.button("保存"):
                PortfolioService().update_transaction_memo(selected_record.id, new_memo or None)
                st.success("メモを保存しました")
                st.rerun()

except Exception as e:
    st.error(f"データ取得エラー: {e}")

bottom_nav()
