from datetime import date, timedelta

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

from config.settings import settings
from config.ui_theme import (
    inject_styles, kpi_card, kpi_row, rank_row, bottom_nav,
    COLOR_PROFIT, COLOR_LOSS, COLOR_NEUTRAL,
    COLOR_CASH, COLOR_JP, COLOR_US,
    PLOTLY_FONT, PLOTLY_BG, PLOTLY_GRID, PLOTLY_TICK_COLOR,
)
from core.auth import require_auth
from core.services.portfolio_service import PortfolioService
from core.services.price_service import PriceService

_BENCHMARKS: dict[str, str] = {
    "日経225": "^N225",
    "TOPIX": "^TOPX",
    "S&P 500": "^GSPC",
    "NASDAQ": "^IXIC",
}
_BENCHMARK_COLORS = ["#f5a623", "#7ed321", "#bd10e0", "#4a90e2"]

inject_styles()
require_auth()
st.title("📊 ダッシュボード")

try:
    psvc    = PortfolioService()
    summary = psvc.get_summary()

    # ── KPI カード（メイン4枚）────────────────────────────────────────────
    kpi_row([
        kpi_card("総資産", f"¥{summary.total_assets:,.0f}"),
        kpi_card(
            "含み損益",
            f"¥{summary.unrealized_pnl:+,.0f}",
            delta=f"{summary.unrealized_pnl / summary.initial_cash * 100:+.2f}% of initial",
            positive=summary.unrealized_pnl >= 0,
        ),
        kpi_card(
            "実現損益（累計）",
            f"¥{summary.realized_pnl:+,.0f}",
            positive=summary.realized_pnl >= 0 if summary.realized_pnl != 0 else None,
        ),
        kpi_card(
            "総合損益",
            f"¥{summary.total_pnl:+,.0f}",
            delta=f"{summary.total_pnl_rate:+.2f}%",
            positive=summary.total_pnl >= 0,
        ),
    ])

    # ── グラフ行 ──────────────────────────────────────────────────────────
    col_left, col_right = st.columns([3, 2])

    with col_left:
        _period_map: dict[str, int | None] = {
            "1ヶ月": 30, "3ヶ月": 90, "6ヶ月": 180, "1年": 365, "全期間": None,
        }
        _yf_period_map: dict[str, str] = {
            "1ヶ月": "1mo", "3ヶ月": "3mo", "6ヶ月": "6mo", "1年": "1y", "全期間": "max",
        }
        selected_period = st.radio(
            "期間", list(_period_map.keys()), horizontal=True, index=4, label_visibility="collapsed"
        )
        _days = _period_map[selected_period]
        _period_map_str = _yf_period_map[selected_period]
        _from = date.today() - timedelta(days=_days) if _days else None
        snapshots = psvc.get_snapshot_history(from_date=_from)
        if len(snapshots) >= 2:
            dates  = [s.date for s in snapshots]
            totals = [s.total_assets for s in snapshots]
            fig = go.Figure(go.Scatter(
                x=dates, y=totals,
                mode="lines",
                line=dict(color=COLOR_PROFIT, width=2.5),
                fill="tozeroy",
                fillcolor="rgba(0,212,170,0.06)",
                hovertemplate="<b>%{x}</b><br>¥%{y:,.0f}<extra></extra>",
            ))
            fig.update_layout(
                title=dict(text="資産推移", font=dict(size=13, color="#c8d0e0")),
                height=300,
                font=dict(family=PLOTLY_FONT, color=PLOTLY_TICK_COLOR),
                margin=dict(l=0, r=0, t=40, b=0),
                plot_bgcolor=PLOTLY_BG,
                paper_bgcolor=PLOTLY_BG,
                xaxis=dict(
                    showgrid=True, gridcolor=PLOTLY_GRID,
                    tickfont=dict(size=11), showline=False, zeroline=False,
                ),
                yaxis=dict(
                    showgrid=True, gridcolor=PLOTLY_GRID,
                    tickfont=dict(size=11), showline=False, zeroline=False,
                    tickprefix="¥", tickformat=",.0f",
                ),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("資産推移グラフは2日分以上のスナップショットが揃うと表示されます。")

    with col_right:
        if summary.total_assets > 0:
            labels = ["現金", "日本株", "米国株"]
            values = [summary.current_cash, summary.jp_market_value, summary.us_market_value]
            fig2 = go.Figure(go.Pie(
                labels=labels, values=values,
                hole=0.6,
                marker=dict(
                    colors=[COLOR_CASH, COLOR_JP, COLOR_US],
                    line=dict(color="#070b14", width=2),
                ),
                textinfo="label+percent",
                textfont=dict(size=12, color="#c8d0e0"),
                hovertemplate="%{label}<br>¥%{value:,.0f}<br>%{percent}<extra></extra>",
            ))
            fig2.update_layout(
                title=dict(text="ポートフォリオ構成", font=dict(size=13, color="#c8d0e0")),
                height=300,
                font=dict(family=PLOTLY_FONT, color=PLOTLY_TICK_COLOR),
                margin=dict(l=0, r=0, t=40, b=0),
                paper_bgcolor=PLOTLY_BG,
                showlegend=False,
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.divider()

    # ── 市場別内訳 + 手数料・税金（小さめカード）────────────────────────
    kpi_row([
        kpi_card("現金残高", f"¥{summary.current_cash:,.0f}", small=True),
        kpi_card("日本株評価額（円）", f"¥{summary.jp_market_value:,.0f}", small=True),
        kpi_card("米国株評価額（円換算）", f"¥{summary.us_market_value:,.0f}", small=True),
        kpi_card("累計手数料", f"¥{summary.total_fee:,.0f}", small=True),
        kpi_card("累計税金", f"¥{summary.total_tax:,.0f}", small=True),
    ])

    # ── 銘柄ランキング ────────────────────────────────────────────────────
    positions = psvc.get_positions()
    if positions:
        st.divider()
        sorted_pos = sorted(positions, key=lambda p: p.unrealized_pnl_rate, reverse=True)

        col_top, col_bottom = st.columns(2)

        with col_top:
            st.markdown(
                "<p style='font-size:.7rem;font-weight:700;text-transform:uppercase;"
                "letter-spacing:.1em;color:#8892a4;margin-bottom:.6rem'>値上がり Top3</p>",
                unsafe_allow_html=True,
            )
            rows_html = "".join(
                rank_row(p.name, p.ticker, p.unrealized_pnl_rate)
                for p in sorted_pos[:3]
            )
            st.markdown(rows_html, unsafe_allow_html=True)

        with col_bottom:
            st.markdown(
                "<p style='font-size:.7rem;font-weight:700;text-transform:uppercase;"
                "letter-spacing:.1em;color:#8892a4;margin-bottom:.6rem'>値下がり Bottom3</p>",
                unsafe_allow_html=True,
            )
            rows_html = "".join(
                rank_row(p.name, p.ticker, p.unrealized_pnl_rate)
                for p in sorted_pos[-3:][::-1]
            )
            st.markdown(rows_html, unsafe_allow_html=True)

    # ── ベンチマーク比較 ─────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<p style='font-size:.7rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:.1em;color:#8892a4;margin-bottom:.6rem'>ベンチマーク比較</p>",
        unsafe_allow_html=True,
    )

    # ON/OFF チェックボックス（横並び）
    bm_cols = st.columns(len(_BENCHMARKS))
    selected_bms: list[tuple[str, str]] = []
    for i, (label, ticker_bm) in enumerate(_BENCHMARKS.items()):
        with bm_cols[i]:
            if st.checkbox(label, value=False):
                selected_bms.append((label, ticker_bm))

    if snapshots and len(snapshots) >= 2 and selected_bms:
        # ポートフォリオを 100 に正規化
        snap_dates = [s.date for s in snapshots]
        snap_values = [s.total_assets for s in snapshots]
        base_val = snap_values[0]
        port_norm = [v / base_val * 100 for v in snap_values]

        fig_bm = go.Figure()
        fig_bm.add_trace(go.Scatter(
            x=snap_dates, y=port_norm,
            mode="lines", name="ポートフォリオ",
            line=dict(color=COLOR_PROFIT, width=2.5),
            hovertemplate="<b>%{x}</b><br>ポートフォリオ: %{y:.1f}<extra></extra>",
        ))

        price_svc = PriceService()
        for (bm_label, bm_ticker), bm_color in zip(selected_bms, _BENCHMARK_COLORS):
            try:
                bm_df = price_svc.get_price_history(bm_ticker, period=_period_map_str)
                if bm_df.empty:
                    continue
                # スナップショット開始日以降に絞る
                start = pd.Timestamp(snap_dates[0])
                bm_df = bm_df[bm_df.index >= start]
                if bm_df.empty:
                    continue
                bm_base = float(bm_df["Close"].iloc[0])
                bm_norm = bm_df["Close"] / bm_base * 100
                fig_bm.add_trace(go.Scatter(
                    x=bm_df.index, y=bm_norm,
                    mode="lines", name=bm_label,
                    line=dict(color=bm_color, width=1.5, dash="dot"),
                    hovertemplate=f"<b>%{{x}}</b><br>{bm_label}: %{{y:.1f}}<extra></extra>",
                ))
            except Exception:
                st.caption(f"⚠️ {bm_label} のデータ取得に失敗しました")

        fig_bm.update_layout(
            title=dict(text="パフォーマンス比較（開始時 = 100）", font=dict(size=13, color="#c8d0e0")),
            height=320,
            font=dict(family=PLOTLY_FONT, color=PLOTLY_TICK_COLOR),
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor=PLOTLY_BG,
            paper_bgcolor=PLOTLY_BG,
            xaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID, zeroline=False),
            yaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID, zeroline=False, ticksuffix=""),
            legend=dict(orientation="h", y=-0.15),
            hovermode="x unified",
        )
        st.plotly_chart(fig_bm, use_container_width=True)
    elif selected_bms:
        st.info("スナップショットが2日分以上揃うとベンチマーク比較グラフが表示されます。")

except Exception as e:
    st.error(f"データ取得エラー: {e}")
    if settings.SKIP_AUTH:
        import traceback
        st.code(traceback.format_exc())

bottom_nav()
