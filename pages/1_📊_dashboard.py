from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

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

_FAMOUS: dict[str, str] = {
    "AAPL":   "Apple",
    "MSFT":   "Microsoft",
    "NVDA":   "NVIDIA",
    "TSLA":   "Tesla",
    "7203.T": "トヨタ",
    "9984.T": "ソフトバンクG",
    "6758.T": "ソニーG",
    "7974.T": "任天堂",
}

_TICKER_CSS = """
<style>
.ticker-wrap{overflow:hidden;background:linear-gradient(90deg,#070b14 0%,#0d1321 20%,#0d1321 80%,#070b14 100%);
border-top:1px solid rgba(0,212,170,.15);border-bottom:1px solid rgba(0,212,170,.15);
padding:9px 0;margin-bottom:28px;position:relative;}
.ticker-wrap::before{content:'';position:absolute;left:0;top:0;bottom:0;width:60px;
background:linear-gradient(90deg,#070b14,transparent);z-index:2;pointer-events:none;}
.ticker-wrap::after{content:'';position:absolute;right:0;top:0;bottom:0;width:60px;
background:linear-gradient(270deg,#070b14,transparent);z-index:2;pointer-events:none;}
.ticker-track{display:inline-flex;animation:ticker-scroll 55s linear infinite;}
.ticker-track:hover{animation-play-state:paused;}
.ticker-item{display:inline-flex;align-items:center;gap:7px;padding:0 24px;
border-right:1px solid rgba(255,255,255,.06);font-size:12px;white-space:nowrap;
font-family:'Inter','Noto Sans JP',monospace;}
.tn{color:#8892a4;font-weight:600;letter-spacing:.04em;}
.tp{color:#e8edf8;font-weight:500;}
.tu{color:#00d4aa;font-weight:600;}
.td{color:#ff4757;font-weight:600;}
@keyframes ticker-scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
</style>
"""

_CARD_CSS = """
<style>
.stock-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07);
border-radius:14px;padding:14px 14px 6px;margin-bottom:4px;
transition:border-color .2s;}
.stock-card:hover{border-color:rgba(0,212,170,.3);}
.sc-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;}
.sc-name{font-size:13px;font-weight:600;color:#f0f4ff;}
.sc-ticker{font-size:10px;color:#8892a4;margin-top:2px;}
.sc-badge{font-size:9px;font-weight:700;letter-spacing:.08em;padding:2px 6px;
border-radius:4px;background:rgba(0,212,170,.15);color:#00d4aa;}
.sc-price{font-size:18px;font-weight:700;color:#f0f4ff;line-height:1.1;}
.sc-chg-up{font-size:12px;color:#00d4aa;font-weight:600;}
.sc-chg-dn{font-size:12px;color:#ff4757;font-weight:600;}
</style>
"""


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_ticker_data(tickers: tuple[str, ...]) -> list[dict]:
    svc = PriceService()
    result = []
    for ticker in tickers:
        try:
            hist = svc.get_price_history(ticker, period="5d")
            if hist.empty:
                continue
            closes = hist["Close"].dropna()
            curr = float(closes.iloc[-1])
            chg = float((closes.iloc[-1] - closes.iloc[-2]) / closes.iloc[-2] * 100) if len(closes) >= 2 else 0.0
            is_jp = ticker.endswith(".T")
            price_str = f"¥{curr:,.0f}" if is_jp else f"${curr:.2f}"
            result.append({"ticker": ticker, "name": _FAMOUS.get(ticker, ticker.replace(".T", "")),
                           "price_str": price_str, "chg": chg})
        except Exception:
            pass
    return result


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_chart(ticker: str) -> pd.DataFrame:
    return PriceService().get_price_history(ticker, period="1y")


def _render_ticker(tickers: tuple[str, ...]) -> None:
    data = _fetch_ticker_data(tickers)
    if not data:
        return
    items = ""
    for d in data:
        cls = "tu" if d["chg"] >= 0 else "td"
        arrow = "▲" if d["chg"] >= 0 else "▼"
        items += (
            f'<span class="ticker-item">'
            f'<span class="tn">{d["name"]}</span>'
            f'<span class="tp">{d["price_str"]}</span>'
            f'<span class="{cls}">{arrow}{abs(d["chg"]):.2f}%</span>'
            f'</span>'
        )
    st.markdown(
        _TICKER_CSS + f'<div class="ticker-wrap"><div class="ticker-track">{items}{items}</div></div>',
        unsafe_allow_html=True,
    )


def _render_stock_cards(held_tickers: set[str], held_name_map: dict[str, str]) -> None:
    stocks: list[tuple[str, str, bool]] = []
    for ticker, name in held_name_map.items():
        stocks.append((ticker, name, True))
    for ticker, name in _FAMOUS.items():
        if ticker not in held_tickers:
            stocks.append((ticker, name, False))

    if not stocks:
        return

    st.markdown(_CARD_CSS, unsafe_allow_html=True)

    cols = st.columns(3)
    for i, (ticker, name, is_held) in enumerate(stocks):
        with cols[i % 3]:
            try:
                hist = _fetch_chart(ticker)
                if hist.empty:
                    continue
                closes = hist["Close"].dropna()
                curr = float(closes.iloc[-1])
                first = float(closes.iloc[0])
                chg_pct = (curr - first) / first * 100
                is_jp = ticker.endswith(".T")
                price_str = f"¥{curr:,.0f}" if is_jp else f"${curr:.2f}"
                color = COLOR_PROFIT if chg_pct >= 0 else COLOR_LOSS
                fill = "rgba(0,212,170,.07)" if chg_pct >= 0 else "rgba(255,71,87,.07)"
                chg_cls = "sc-chg-up" if chg_pct >= 0 else "sc-chg-dn"
                arrow = "▲" if chg_pct >= 0 else "▼"
                badge = '<span class="sc-badge">保有</span>' if is_held else ""

                st.markdown(
                    f'<div class="stock-card">'
                    f'<div class="sc-header">'
                    f'<div><div class="sc-name">{name}</div>'
                    f'<div class="sc-ticker">{ticker.replace(".T","")}</div></div>'
                    f'{badge}</div>'
                    f'<div class="sc-price">{price_str}</div>'
                    f'<div class="{chg_cls}">{arrow} {abs(chg_pct):.2f}%（1年）</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                y_fmt = "¥%{y:,.0f}" if is_jp else "$%{y:.2f}"
                fig = go.Figure(go.Scatter(
                    x=hist.index, y=closes,
                    mode="lines",
                    line=dict(color=color, width=1.5),
                    fill="tozeroy", fillcolor=fill,
                    hovertemplate=f"%{{x|%Y-%m-%d}}<br>{y_fmt}<extra></extra>",
                ))
                fig.update_layout(
                    height=160,
                    font=dict(family=PLOTLY_FONT),
                    margin=dict(l=0, r=0, t=0, b=0),
                    plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
                    xaxis=dict(showgrid=False, showticklabels=False, zeroline=False, showline=False),
                    yaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID, tickfont=dict(size=9),
                               showline=False, zeroline=False,
                               tickprefix="¥" if is_jp else "$"),
                    dragmode="pan",
                )
                st.plotly_chart(
                    fig, use_container_width=True,
                    config={"scrollZoom": True, "displayModeBar": False},
                    key=f"scard_{ticker}",
                )
            except Exception:
                st.caption(f"⚠️ {ticker}")


inject_styles()
require_auth()
st.title("📊 ダッシュボード")

try:
    psvc    = PortfolioService()
    summary = psvc.get_summary()
    positions = psvc.get_positions()

    held_tickers = {p.ticker for p in positions}
    held_name_map = {p.ticker: p.name for p in positions}
    all_tickers = tuple(dict.fromkeys(list(held_tickers) + list(_FAMOUS.keys())))

    # ── ティッカーバー ────────────────────────────────────────────────────────
    _render_ticker(all_tickers)

    # ── KPI カード ────────────────────────────────────────────────────────────
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

    # ── 資産推移 + ポートフォリオ構成 ─────────────────────────────────────────
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
                plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
                xaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID,
                           tickfont=dict(size=11), showline=False, zeroline=False),
                yaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID,
                           tickfont=dict(size=11), showline=False, zeroline=False,
                           tickprefix="¥", tickformat=",.0f"),
                hovermode="x unified",
                dragmode="pan",
            )
            st.plotly_chart(fig, use_container_width=True,
                            config={"scrollZoom": True, "displayModeBar": False})
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
                paper_bgcolor=PLOTLY_BG, showlegend=False,
            )
            st.plotly_chart(fig2, use_container_width=True,
                            config={"displayModeBar": False})

    # ── 銘柄チャート ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<p style='font-size:.7rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:.1em;color:#8892a4;margin-bottom:1rem'>📊 銘柄チャート"
        "<span style='font-size:.65rem;color:#3d4f63;margin-left:8px'>"
        "スクロールでズーム・ドラッグでパン</span></p>",
        unsafe_allow_html=True,
    )
    _render_stock_cards(held_tickers, held_name_map)

    # ── 市場別内訳 ────────────────────────────────────────────────────────────
    st.divider()
    kpi_row([
        kpi_card("現金残高", f"¥{summary.current_cash:,.0f}", small=True),
        kpi_card("日本株評価額（円）", f"¥{summary.jp_market_value:,.0f}", small=True),
        kpi_card("米国株評価額（円換算）", f"¥{summary.us_market_value:,.0f}", small=True),
        kpi_card("累計手数料", f"¥{summary.total_fee:,.0f}", small=True),
        kpi_card("累計税金", f"¥{summary.total_tax:,.0f}", small=True),
    ])

    # ── 銘柄ランキング ────────────────────────────────────────────────────────
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
            st.markdown(
                "".join(rank_row(p.name, p.ticker, p.unrealized_pnl_rate) for p in sorted_pos[:3]),
                unsafe_allow_html=True,
            )
        with col_bottom:
            st.markdown(
                "<p style='font-size:.7rem;font-weight:700;text-transform:uppercase;"
                "letter-spacing:.1em;color:#8892a4;margin-bottom:.6rem'>値下がり Bottom3</p>",
                unsafe_allow_html=True,
            )
            st.markdown(
                "".join(rank_row(p.name, p.ticker, p.unrealized_pnl_rate) for p in sorted_pos[-3:][::-1]),
                unsafe_allow_html=True,
            )

    # ── ベンチマーク比較 ──────────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<p style='font-size:.7rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:.1em;color:#8892a4;margin-bottom:.6rem'>ベンチマーク比較</p>",
        unsafe_allow_html=True,
    )
    bm_cols = st.columns(len(_BENCHMARKS))
    selected_bms: list[tuple[str, str]] = []
    for i, (label, ticker_bm) in enumerate(_BENCHMARKS.items()):
        with bm_cols[i]:
            if st.checkbox(label, value=False):
                selected_bms.append((label, ticker_bm))

    if snapshots and len(snapshots) >= 2 and selected_bms:
        snap_dates  = [s.date for s in snapshots]
        snap_values = [s.total_assets for s in snapshots]
        base_val    = snap_values[0]
        port_norm   = [v / base_val * 100 for v in snap_values]

        fig_bm = go.Figure()
        fig_bm.add_trace(go.Scatter(
            x=snap_dates, y=port_norm, mode="lines", name="ポートフォリオ",
            line=dict(color=COLOR_PROFIT, width=2.5),
            hovertemplate="<b>%{x}</b><br>ポートフォリオ: %{y:.1f}<extra></extra>",
        ))
        price_svc = PriceService()
        for (bm_label, bm_ticker), bm_color in zip(selected_bms, _BENCHMARK_COLORS):
            try:
                bm_df = price_svc.get_price_history(bm_ticker, period=_period_map_str)
                if bm_df.empty:
                    continue
                start = pd.Timestamp(snap_dates[0])
                bm_df = bm_df[bm_df.index >= start]
                if bm_df.empty:
                    continue
                bm_norm = bm_df["Close"] / float(bm_df["Close"].iloc[0]) * 100
                fig_bm.add_trace(go.Scatter(
                    x=bm_df.index, y=bm_norm, mode="lines", name=bm_label,
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
            plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
            xaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID, zeroline=False),
            yaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID, zeroline=False),
            legend=dict(orientation="h", y=-0.15),
            hovermode="x unified",
            dragmode="pan",
        )
        st.plotly_chart(fig_bm, use_container_width=True,
                        config={"scrollZoom": True, "displayModeBar": False})
    elif selected_bms:
        st.info("スナップショットが2日分以上揃うとベンチマーク比較グラフが表示されます。")

    # ── シミュレーション比較 ──────────────────────────────────────────────────
    st.divider()
    st.markdown(
        "<p style='font-size:.7rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:.1em;color:#8892a4;margin-bottom:.6rem'>🎮 vs シミュレーション</p>",
        unsafe_allow_html=True,
    )
    _SIM_COLORS = ["#f5a623", "#bd10e0", "#4a90e2", "#ff4757"]
    try:
        scenarios = psvc.get_simulation_scenarios()
        if not scenarios:
            st.info("シミュレーションシナリオがまだありません。🎮 シミュレーションページで作成してください。")
        else:
            sim_data: list[tuple[str, list]] = []
            for name in scenarios:
                snaps = PortfolioService(account_type="simulation", scenario_name=name).get_snapshot_history(from_date=_from)
                if len(snaps) >= 2:
                    sim_data.append((name, snaps))

            if len(snapshots) >= 2 and sim_data:
                real_base = snapshots[0].total_assets
                fig_sim = go.Figure()
                fig_sim.add_trace(go.Scatter(
                    x=[s.date for s in snapshots],
                    y=[s.total_assets / real_base * 100 for s in snapshots],
                    mode="lines", name="実口座",
                    line=dict(color=COLOR_PROFIT, width=2.5),
                    hovertemplate="<b>%{x}</b><br>実口座: %{y:.1f}<extra></extra>",
                ))
                for (name, snaps), color in zip(sim_data, _SIM_COLORS):
                    sim_base = snaps[0].total_assets
                    fig_sim.add_trace(go.Scatter(
                        x=[s.date for s in snaps],
                        y=[s.total_assets / sim_base * 100 for s in snaps],
                        mode="lines", name=name,
                        line=dict(color=color, width=2, dash="dot"),
                        hovertemplate=f"<b>%{{x}}</b><br>{name}: %{{y:.1f}}<extra></extra>",
                    ))
                fig_sim.update_layout(
                    title=dict(text="資産推移比較（開始時 = 100）", font=dict(size=13, color="#c8d0e0")),
                    height=300,
                    font=dict(family=PLOTLY_FONT, color=PLOTLY_TICK_COLOR),
                    margin=dict(l=0, r=0, t=40, b=0),
                    plot_bgcolor=PLOTLY_BG, paper_bgcolor=PLOTLY_BG,
                    xaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID, zeroline=False),
                    yaxis=dict(showgrid=True, gridcolor=PLOTLY_GRID, zeroline=False),
                    legend=dict(orientation="h", y=-0.15),
                    hovermode="x unified",
                    dragmode="pan",
                )
                st.plotly_chart(fig_sim, use_container_width=True,
                                config={"scrollZoom": True, "displayModeBar": False})

                cards = [("実口座", summary.total_assets, summary.total_pnl_rate)]
                for name in scenarios:
                    try:
                        s = PortfolioService(account_type="simulation", scenario_name=name).get_summary()
                        cards.append((name, s.total_assets, s.total_pnl_rate))
                    except Exception:
                        pass
                sim_cols = st.columns(len(cards))
                for col, (label, assets, rate) in zip(sim_cols, cards):
                    col.metric(label, f"¥{assets:,.0f}", delta=f"{rate:+.2f}%")
            else:
                st.info("シナリオのスナップショットが2日分以上揃うと比較グラフが表示されます。")
    except Exception:
        st.info("シミュレーションシナリオがまだありません。🎮 シミュレーションページで作成してください。")

except Exception as e:
    st.error(f"データ取得エラー: {e}")
    if settings.SKIP_AUTH:
        import traceback
        st.code(traceback.format_exc())

bottom_nav()
