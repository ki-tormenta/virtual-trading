import pandas as pd
import streamlit as st

from config.ui_theme import inject_styles
from core.auth import require_auth
from core.services.portfolio_service import PortfolioService

inject_styles()
require_auth()
st.title("📋 ポジション一覧")

try:
    with st.spinner("データを取得中..."):
        positions = PortfolioService().get_positions()

    if not positions:
        st.info("保有銘柄はありません。売買ページから銘柄を購入してください。")
    else:
        col_mf, col_tf = st.columns([2, 3])
        with col_mf:
            market_filter = st.selectbox("市場フィルタ", ["全て", "日本株（JP）", "米国株（US）"])
        with col_tf:
            tag_filter = st.text_input("タグフィルタ", placeholder="例: 成長株")

        filtered = positions
        if market_filter == "日本株（JP）":
            filtered = [p for p in filtered if p.market == "JP"]
        elif market_filter == "米国株（US）":
            filtered = [p for p in filtered if p.market == "US"]

        if tag_filter.strip():
            from core.services.portfolio_service import PortfolioService as _PS
            tagged = _PS().get_tickers_with_tag(tag_filter.strip())
            filtered = [p for p in filtered if p.ticker in tagged]

        if not filtered:
            st.info("該当する保有銘柄はありません。")
        else:
            # サマリー（全て円換算）
            total_value_jpy = sum(p.market_value_jpy for p in filtered)
            total_pnl_jpy = sum(p.unrealized_pnl_jpy for p in filtered)
            c1, c2, c3 = st.columns(3)
            c1.metric("銘柄数", f"{len(filtered)}銘柄")
            c2.metric("評価額合計（円換算）", f"{total_value_jpy:,.0f}円")
            c3.metric("含み損益合計（円換算）", f"{total_pnl_jpy:+,.0f}円")

            st.divider()

            # テーブル
            rows = []
            for p in filtered:
                is_jp = p.market == "JP"
                currency = "円" if is_jp else "USD"
                rows.append({
                    "銘柄名": p.name,
                    "ティッカー": p.ticker,
                    "市場": "JP" if p.market == "JP" else "US",
                    "数量": f"{p.quantity:,d}株",
                    "平均取得単価": (
                        f"{p.avg_buy_price:,.0f}{currency}"
                        if is_jp
                        else f"${p.avg_buy_price:,.2f}"
                    ),
                    "現在値": (
                        f"{p.current_price:,.0f}{currency}"
                        if is_jp
                        else f"${p.current_price:,.2f}"
                    ),
                    "評価額": (
                        f"{p.market_value:,.0f}{currency}"
                        if is_jp
                        else f"${p.market_value:,.2f}"
                    ),
                    "含み損益": (
                        f"{p.unrealized_pnl:+,.0f}{currency}"
                        if is_jp
                        else f"${p.unrealized_pnl:+,.2f}"
                    ),
                    "損益率": f"{p.unrealized_pnl_rate:+.2f}%",
                })

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)

except Exception as e:
    st.error(f"データ取得エラー: {e}")
