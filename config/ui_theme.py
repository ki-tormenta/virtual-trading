import streamlit as st

# ── Color palette ──────────────────────────────────────────────────────────
COLOR_PROFIT  = "#00d4aa"
COLOR_LOSS    = "#ff4757"
COLOR_NEUTRAL = "#8892a4"
COLOR_JP      = "#00d4aa"
COLOR_US      = "#4299e1"
COLOR_CASH    = "#8892a4"

PLOTLY_FONT       = "Inter, Noto Sans JP, Meiryo, sans-serif"
PLOTLY_BG         = "rgba(0,0,0,0)"
PLOTLY_GRID       = "rgba(255,255,255,0.05)"
PLOTLY_TICK_COLOR = "#8892a4"

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
  --c-bg:       #070b14;
  --c-surface:  #0d1321;
  --c-card:     rgba(255,255,255,0.04);
  --c-border:   rgba(255,255,255,0.08);
  --c-border-h: rgba(255,255,255,0.14);
  --c-profit:   #00d4aa;
  --c-loss:     #ff4757;
  --c-neutral:  #8892a4;
  --c-text:     #f0f4ff;
  --c-text2:    #8892a4;
  --c-text3:    #3d4f63;
  --r-card:     16px;
  --r-sm:       10px;
}

/* ── Font & Base ─────────────────────────────────────────────────────────── */
html, body, [class*="css"] {
  font-family: 'Inter', 'Noto Sans JP', 'Meiryo', sans-serif !important;
}
.stApp { background: var(--c-bg) !important; }
.main .block-container {
  padding-top: 2rem;
  padding-bottom: 3rem;
  max-width: 1280px;
}

/* ── Hide Streamlit chrome ───────────────────────────────────────────────── */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }

/* ── Sidebar ─────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
  background: #070b14 !important;
  border-right: 1px solid rgba(255,255,255,0.05);
}
[data-testid="stSidebarNav"] a {
  border-radius: 8px;
  color: var(--c-text2) !important;
  font-size: 0.875rem;
  font-weight: 500;
  margin: 2px 8px;
  padding: 9px 14px;
  transition: all 0.15s;
}
[data-testid="stSidebarNav"] a:hover {
  background: rgba(0,212,170,0.07) !important;
  color: var(--c-profit) !important;
}
[data-testid="stSidebarNav"] a[aria-current="page"] {
  background: rgba(0,212,170,0.1) !important;
  color: var(--c-profit) !important;
  font-weight: 600;
}

/* ── Typography ──────────────────────────────────────────────────────────── */
h1 {
  font-size: 1.45rem !important;
  font-weight: 800 !important;
  color: var(--c-text) !important;
  letter-spacing: -0.03em !important;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  padding-bottom: 1rem !important;
  margin-bottom: 1.75rem !important;
}
h2 { font-size: 0.95rem !important; font-weight: 600 !important; color: var(--c-text) !important; }
h3 { font-size: 0.85rem !important; font-weight: 600 !important; color: var(--c-text2) !important; }
p, .stMarkdown p { color: var(--c-text2); line-height: 1.6; }

/* ── KPI Cards ───────────────────────────────────────────────────────────── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1.25rem;
  margin-bottom: 2rem;
}
.kpi-card {
  background: var(--c-card);
  border: 1px solid var(--c-border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: var(--r-card);
  padding: 1.4rem 1.5rem;
  position: relative;
  overflow: hidden;
  /* ambient + key の2層シャドウ */
  box-shadow: 0 1px 2px rgba(0,0,0,0.4), 0 8px 32px rgba(0,212,170,0.06);
  transition: border-color 0.2s, box-shadow 0.2s, transform 0.2s;
}
/* 上部グロー線 */
.kpi-card::before {
  content: '';
  position: absolute;
  top: 0; left: 10%; right: 10%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,212,170,0.7), transparent);
}
/* 底面アンビエントグロー */
.kpi-card::after {
  content: '';
  position: absolute;
  bottom: 0; left: 0; right: 0;
  height: 55%;
  background: radial-gradient(ellipse at 50% 110%, rgba(0,212,170,0.07) 0%, transparent 70%);
  pointer-events: none;
}
.kpi-card:hover {
  border-color: var(--c-border-h);
  box-shadow: 0 1px 2px rgba(0,0,0,0.5), 0 12px 40px rgba(0,212,170,0.14);
  transform: translateY(-2px);
}
.kpi-label {
  font-size: 0.65rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.13em;
  color: var(--c-text2);
  margin-bottom: 0.75rem;
}
.kpi-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--c-text);
  letter-spacing: -0.03em;
  line-height: 1;
  margin-bottom: 0.5rem;
}
.kpi-value.sm { font-size: 1.45rem; }
.kpi-delta {
  font-size: 0.78rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 0.2rem;
}
.kpi-delta.pos { color: var(--c-profit); }
.kpi-delta.neg { color: var(--c-loss); }
.kpi-delta.neu { color: var(--c-neutral); }

/* ── Ranking rows ────────────────────────────────────────────────────────── */
.rank-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.65rem 1rem;
  border-radius: 10px;
  margin-bottom: 0.35rem;
  background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.05);
  transition: background 0.15s;
}
.rank-row:hover { background: rgba(255,255,255,0.05); }
.rank-name   { font-size: 0.85rem; font-weight: 500; color: #c8d0e0; }
.rank-ticker { font-size: 0.7rem; color: #8892a4; margin-left: 0.4rem; }
.rank-pct    { font-size: 0.875rem; font-weight: 700; }
.rank-pct.pos { color: var(--c-profit); }
.rank-pct.neg { color: var(--c-loss); }
.rank-pct.neu { color: var(--c-neutral); }

/* ── Buttons ─────────────────────────────────────────────────────────────── */
[data-testid="baseButton-primary"] {
  background: linear-gradient(135deg, #00d4aa, #00b894) !important;
  border: none !important;
  border-radius: var(--r-sm) !important;
  color: #070b14 !important;
  font-weight: 700 !important;
  font-size: 0.875rem !important;
  box-shadow: 0 2px 14px rgba(0,212,170,0.28) !important;
  transition: all 0.2s !important;
}
[data-testid="baseButton-primary"]:hover {
  opacity: 0.88 !important;
  box-shadow: 0 4px 22px rgba(0,212,170,0.4) !important;
  transform: translateY(-1px) !important;
}
[data-testid="baseButton-secondary"] {
  background: transparent !important;
  border: 1px solid var(--c-border) !important;
  border-radius: var(--r-sm) !important;
  color: var(--c-text2) !important;
  font-weight: 500 !important;
  transition: all 0.2s !important;
}
[data-testid="baseButton-secondary"]:hover {
  border-color: var(--c-profit) !important;
  color: var(--c-profit) !important;
}

/* ── Input Fields ────────────────────────────────────────────────────────── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
  background: rgba(255,255,255,0.04) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: var(--r-sm) !important;
  color: var(--c-text) !important;
  font-size: 0.875rem !important;
  transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus,
[data-testid="stTextArea"] textarea:focus {
  border-color: var(--c-profit) !important;
  box-shadow: 0 0 0 3px rgba(0,212,170,0.12) !important;
}
[data-testid="stTextInput"] label,
[data-testid="stNumberInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stTextArea"] label,
[data-testid="stDateInput"] label {
  color: var(--c-text2) !important;
  font-size: 0.7rem !important;
  font-weight: 700 !important;
  text-transform: uppercase !important;
  letter-spacing: 0.1em !important;
}
[data-testid="stSelectbox"] > div > div {
  background: rgba(255,255,255,0.04) !important;
  border: 1px solid var(--c-border) !important;
  border-radius: var(--r-sm) !important;
  color: var(--c-text) !important;
}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
[data-baseweb="tab-list"] {
  background: transparent !important;
  border-bottom: 1px solid rgba(255,255,255,0.06) !important;
  gap: 0 !important;
}
[data-baseweb="tab"] {
  background: transparent !important;
  color: var(--c-text2) !important;
  font-weight: 500 !important;
  font-size: 0.875rem !important;
  padding: 0.75rem 1.25rem !important;
  border-bottom: 2px solid transparent !important;
  transition: color 0.2s !important;
}
[data-baseweb="tab"]:hover { color: var(--c-text) !important; }
[aria-selected="true"][data-baseweb="tab"] {
  color: var(--c-profit) !important;
  border-bottom-color: var(--c-profit) !important;
}

/* ── Form ────────────────────────────────────────────────────────────────── */
[data-testid="stForm"] {
  background: rgba(255,255,255,0.025) !important;
  border: 1px solid rgba(255,255,255,0.07) !important;
  border-radius: var(--r-card) !important;
  padding: 1.5rem !important;
}

/* ── Misc ────────────────────────────────────────────────────────────────── */
hr {
  border: none !important;
  border-top: 1px solid rgba(255,255,255,0.06) !important;
  margin: 1.75rem 0 !important;
}
[data-testid="stAlert"] {
  border-radius: var(--r-sm) !important;
  border-left-width: 3px !important;
}
[data-testid="stDataFrame"] {
  border: 1px solid rgba(255,255,255,0.07) !important;
  border-radius: 12px !important;
  overflow: hidden;
}
[data-testid="stPlotlyChart"] {
  background: rgba(255,255,255,0.025);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: var(--r-card);
  padding: 0.25rem;
}
[data-testid="stCaptionContainer"] { color: var(--c-text3) !important; }
</style>
"""


def inject_styles() -> None:
    """全ページ共通のカスタムCSSを注入する。"""
    st.markdown(_CSS, unsafe_allow_html=True)


def kpi_card(
    label: str,
    value: str,
    delta: str | None = None,
    positive: bool | None = None,
    small: bool = False,
) -> str:
    """グラスモーフィズム KPI カードのHTMLを返す。"""
    val_cls = "kpi-value sm" if small else "kpi-value"
    delta_html = ""
    if delta is not None:
        if positive is True:
            cls, arrow = "pos", "▲"
        elif positive is False:
            cls, arrow = "neg", "▼"
        else:
            cls, arrow = "neu", "—"
        delta_html = f'<div class="kpi-delta {cls}">{arrow} {delta}</div>'
    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="{val_cls}">{value}</div>'
        f'{delta_html}'
        f'</div>'
    )


def kpi_row(cards: list[str]) -> None:
    """KPIカードを横並びグリッドでレンダリングする。"""
    st.markdown(
        f'<div class="kpi-row">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def rank_row(name: str, ticker: str, pct: float) -> str:
    """ランキング行のHTMLを返す。"""
    cls   = "pos" if pct > 0 else ("neg" if pct < 0 else "neu")
    arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "—")
    return (
        f'<div class="rank-row">'
        f'<span><span class="rank-name">{name}</span>'
        f'<span class="rank-ticker">{ticker}</span></span>'
        f'<span class="rank-pct {cls}">{arrow} {abs(pct):.2f}%</span>'
        f'</div>'
    )
