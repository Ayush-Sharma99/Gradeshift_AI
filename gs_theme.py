"""
GradeShift PrimePath — Design System, Shared Theme & UI Helpers
All colors, typography tokens, reusable HTML/CSS components, and cached
RuntimeContext accessors live here. Import this module at the top of every page.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure `src/` is on sys.path for all Streamlit pages
_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Base64 encoded official GradeShift AI logo fallback
GS_LOGO_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAgAAAAEoCAYAAAC0V1LzAAABrklEQVR4nO3c0W3CMBRF0Z/yQd6/qXSS"
    "ZqC0SqkSSW5w7j4j+TgyT1xHAAAAAAAAAAAAAAD4l/X+M+ZfP56n8WPMv358T+O/nAAAgH8hAACAIAIA"
    "gCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIA"
    "gCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIA"
    "gCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIA"
    "gCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIA"
    "gCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIA"
    "gCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgCBvY/56n8aXwL95HMevvPzDqXQCAABK+AHWswmC"
    "4r3gVAAAAABJRU5ErkJggg=="
)

# ──────────────────────────────────────────────────────────────
# DESIGN TOKENS
# ──────────────────────────────────────────────────────────────
COLOR = {
    # Brand
    "navy": "#062B52",
    "blue": "#1769E0",
    "cyan": "#18BFC3",
    # Semantic
    "green": "#20A873",
    "amber": "#E5A11A",
    "red": "#D64545",
    # Neutrals
    "bg": "#F5F7FA",
    "white": "#FFFFFF",
    "text": "#142033",
    "text2": "#5B687A",
    "muted": "#5B687A",
    "border": "#DCE3EA",
    "card": "#FFFFFF",
    "panel": "#FFFFFF",
    # Chart aliases
    "baseline": "#8C99A8",
    "ai_traj": "#1769E0",
    "ai_signal": "#18BFC3",
    "spec_fill": "rgba(32,168,115,0.08)",
    "offspec_fill": "rgba(214,69,69,0.06)",
    "amber_fill": "rgba(229,161,26,0.12)",
}

FONT_PRIMARY = "'IBM Plex Sans', -apple-system, sans-serif"
FONT_TECH = "'IBM Plex Mono', monospace"

# ──────────────────────────────────────────────────────────────
# FULL CSS BLOCK
# ──────────────────────────────────────────────────────────────
_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

.stMarkdown, p, h1, h2, h3, h4, h5, h6, li, .gs-topbar, .gs-panel {{
    font-family: {FONT_PRIMARY};
}}

.tech-val {{ font-family: {FONT_TECH}; font-weight: 500; font-size: 1.05em; }}
.tech-unit {{ font-family: {FONT_PRIMARY}; font-size: 0.85em; color: {COLOR['text2']}; margin-left: 2px; }}

/* ── Sidebar ── */
section[data-testid="stSidebar"] {{ color: rgba(255,255,255,0.85) !important; font-family: {FONT_PRIMARY}; }}
section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.12) !important; margin: 16px 0 !important; }}
section[data-testid="stSidebarNav"] {{ display: none !important; }}

[data-testid="collapsedControl"], button[kind="header"] {{
    background-color: #FFFFFF !important;
    border-radius: 4px !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.1) !important;
    color: #062B52 !important;
    display: inline-flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    z-index: 999999 !important;
}}
[data-testid="collapsedControl"] svg, button[kind="header"] svg {{
    color: #062B52 !important;
    fill: #062B52 !important;
}}
[data-testid="stHeader"] {{
    background: transparent !important;
}}

/* ── Custom Sidebar Navigation ── */
.gs-nav-section {{
    font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.1em;
    color: rgba(255,255,255,0.45); margin: 20px 0 6px 16px; font-weight: 600;
}}

/* ── Top application header bar ── */
.gs-topbar {{
    background: {COLOR['white']}; border-bottom: 1px solid {COLOR['border']};
    padding: 12px 24px; display: flex; align-items: center; gap: 28px;
    margin-bottom: 18px; border-radius: 6px;
}}
.gs-topbar-field {{ display: flex; flex-direction: column; }}
.gs-topbar-label {{ font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 2px; }}
.gs-topbar-value {{ font-size: 0.85rem; font-weight: 600; color: {COLOR['navy']}; }}
.gs-topbar-right {{ margin-left: auto; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}

/* ── Status pills ── */
.gs-status {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 4px; font-size: 0.70rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }}
.gs-status-online {{ background: rgba(32,168,115,0.12); color: {COLOR['green']}; }}
.gs-status-advisory {{ background: rgba(23,105,224,0.12); color: {COLOR['blue']}; }}
.gs-status-demo {{ background: rgba(229,161,26,0.14); color: {COLOR['amber']}; }}
.gs-status-danger {{ background: rgba(214,69,69,0.14); color: {COLOR['red']}; }}
.gs-status-dot {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}

/* ── Page Headers & Section Headers ── */
.gs-eyebrow {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; margin-bottom: 4px; }}
.gs-page-title {{ font-size: 1.95rem; font-weight: 600; color: {COLOR['navy']}; letter-spacing: -0.02em; margin-bottom: 4px; }}
.gs-page-subtitle {{ font-size: 0.92rem; color: {COLOR['text2']}; margin-bottom: 20px; }}

.gs-section-header {{
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: {COLOR['navy']};
    border-bottom: 1px solid {COLOR['border']};
    padding-bottom: 8px; margin-bottom: 16px; margin-top: 14px;
}}

/* ── KPIs ── */
.gs-kpi-container {{ display: flex; flex-direction: column; }}
.gs-kpi-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 6px; }}
.gs-kpi-value {{ font-family: {FONT_TECH}; font-size: 1.85rem; font-weight: 600; color: {COLOR['navy']}; line-height: 1.1; }}
.gs-kpi-unit {{ font-family: {FONT_PRIMARY}; font-size: 0.9rem; font-weight: 400; color: {COLOR['text2']}; margin-left: 4px; }}
.gs-kpi-delta {{ font-size: 0.78rem; font-weight: 500; margin-top: 6px; }}
.delta-pos {{ color: {COLOR['green']}; }}
.delta-neg {{ color: {COLOR['red']}; }}
.delta-neu {{ color: {COLOR['text2']}; }}

/* ── Panels / Structured Rows ── */
.gs-panel {{
    background: {COLOR['white']}; border: 1px solid {COLOR['border']};
    border-radius: 8px; padding: 20px; margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}}
.gs-panel-title {{
    font-size: 0.85rem; font-weight: 600; color: {COLOR['navy']};
    letter-spacing: 0.02em; margin-bottom: 12px;
}}
.gs-data-row {{
    display: flex; align-items: baseline; justify-content: space-between;
    padding: 8px 0; border-bottom: 1px solid {COLOR['border']};
    font-size: 0.84rem;
}}
.gs-data-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
.gs-data-row-label {{ color: {COLOR['text2']}; }}
.gs-data-row-value {{ font-family: {FONT_TECH}; color: {COLOR['navy']}; font-weight: 500; }}

/* ── Insight block ── */
.gs-insight {{
    background: {COLOR['white']}; border-left: 3px solid {COLOR['blue']};
    padding: 14px 18px; font-size: 0.88rem;
    margin: 12px 0; border-radius: 0 4px 4px 0;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02); line-height: 1.5;
}}
.gs-insight strong {{ color: {COLOR['navy']}; font-weight: 600; }}

/* ── Badges ── */
.gs-badge {{
    display: inline-block; padding: 3px 9px; border-radius: 4px;
    font-size: 0.68rem; font-weight: 600; letter-spacing: 0.07em; text-transform: uppercase;
}}
.gs-badge-blue {{ background: rgba(23,105,224,0.12); color: {COLOR['blue']}; }}
.gs-badge-green {{ background: rgba(32,168,115,0.12); color: {COLOR['green']}; }}
.gs-badge-amber {{ background: rgba(229,161,26,0.15); color: {COLOR['amber']}; }}
.gs-badge-red {{ background: rgba(214,69,69,0.14); color: {COLOR['red']}; }}

/* ── Constraint bar ── */
.gs-constraint-row {{ display: flex; align-items: center; gap: 16px; margin: 10px 0; }}
.gs-constraint-label {{ font-size: 0.84rem; font-weight: 500; width: 160px; flex-shrink: 0; }}
.gs-constraint-bar-wrap {{ flex: 1; height: 6px; background: {COLOR['border']}; border-radius: 3px; position: relative; }}
.gs-constraint-bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.4s ease; }}
.gs-constraint-value {{ font-family: {FONT_TECH}; font-size: 0.84rem; font-weight: 600; color: {COLOR['navy']}; width: 80px; text-align: right; flex-shrink: 0; }}
.gs-constraint-limit {{ font-family: {FONT_TECH}; font-size: 0.75rem; color: {COLOR['text2']}; width: 80px; flex-shrink: 0; }}
.gs-constraint-status {{ font-size: 0.75rem; font-weight: 600; width: 60px; text-align: right; letter-spacing: 0.05em; }}

/* ── Sidebar Brand ── */
.sidebar-logo-container {{ padding: 16px 16px 20px 16px; text-align: left; }}
.sidebar-logo-img {{ max-width: 160px; height: auto; }}
.sidebar-logo-sub {{ font-size: 0.65rem; color: rgba(255,255,255,0.55); text-transform: uppercase; letter-spacing: 0.1em; margin-top: 6px; font-weight: 600; }}

hr {{ border-color: {COLOR['border']} !important; margin: 20px 0 !important; }}
div[data-testid="stMetricValue"] {{ font-family: {FONT_TECH} !important; color: {COLOR['navy']} !important; }}

[data-testid="stSidebar"] * {{
    color: rgba(255, 255, 255, 0.95) !important;
}}
[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] * {{
    color: #142033 !important;
}}
[data-testid="stSidebarNav"] {{
    display: none !important;
}}
</style>
"""


def get_cached_runtime():
    """Return the cached singleton RuntimeContext across all Streamlit pages."""
    import streamlit as st
    from gradeshift.ui import load_runtime_context

    @st.cache_resource(show_spinner=False)
    def _load():
        return load_runtime_context()

    return _load()


def inject_css():
    """Call this once at the top of every Streamlit page."""
    import streamlit as st

    st.markdown(_CSS, unsafe_allow_html=True)


def topbar(
    current_grade_from: str,
    current_grade_to: str,
    unit: str = "SIM-UNIT-1 (UNIPOL PE)",
    mode_label: str = "ILLUSTRATIVE DEMO",
    partition_label: str = "DEMO-A2B",
):
    """Render the sticky top application header bar with explicit provenance."""
    import streamlit as st

    mode_cls = "gs-status-demo"
    if "LOCKED" in mode_label.upper():
        mode_cls = "gs-status-online"
    elif "REPLAY" in mode_label.upper():
        mode_cls = "gs-status-advisory"

    st.markdown(
        f"""
<div class="gs-topbar">
  <div class="gs-topbar-field">
    <div class="gs-topbar-label">Reactor / Line Context</div>
    <div class="gs-topbar-value">{unit}</div>
  </div>
  <div class="gs-topbar-field">
    <div class="gs-topbar-label">Transition Direction</div>
    <div class="gs-topbar-value">Grade {current_grade_from} → Grade {current_grade_to}</div>
  </div>
  <div class="gs-topbar-field">
    <div class="gs-topbar-label">Episode / Partition</div>
    <div class="gs-topbar-value">{partition_label}</div>
  </div>
  <div class="gs-topbar-right">
    <span class="gs-status gs-status-advisory">READ-ONLY ADVISORY</span>
    <span class="gs-status {mode_cls}"><span class="gs-status-dot"></span>{mode_label}</span>
    <span class="gs-status gs-status-demo">SYNTHETIC E2/E3</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def mode_banner(mode_meta: Dict[str, str]):
    """Render a prominent evidence-separation banner at the top of a page."""
    import streamlit as st

    bkind = mode_meta.get("badge_kind", "amber")
    border_col = COLOR["amber"]
    if bkind == "green":
        border_col = COLOR["green"]
    elif bkind == "blue":
        border_col = COLOR["blue"]

    st.markdown(
        f"""
<div style="background:{COLOR['white']}; border:1px solid {COLOR['border']}; border-left:4px solid {border_col};
            border-radius:6px; padding:12px 18px; margin-bottom:18px; display:flex; align-items:center; justify-content:space-between; gap:16px;">
  <div>
    <div style="font-size:0.72rem; font-weight:700; letter-spacing:0.08em; text-transform:uppercase; color:{border_col}; margin-bottom:3px;">
      {mode_meta.get('banner_title', 'PRIMEPATH ADVISORY LAYER')}
    </div>
    <div style="font-size:0.84rem; color:{COLOR['text']}; line-height:1.45;">
      {mode_meta.get('description', '')}
    </div>
  </div>
  <div style="flex-shrink:0; text-align:right;">
    <span class="gs-badge gs-badge-{bkind}">{mode_meta.get('evidence_level', 'E2/E3')}</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def action_hero_card(
    action: str,
    action_meta: Dict[str, str],
    reason_codes: List[str],
    approval_status: str,
    approver_role: str,
    narrative: str = "",
):
    """Render the primary PrimePath Disposition Recommendation Hero Card."""
    import streamlit as st

    col = action_meta.get("color", COLOR["navy"])
    bkind = action_meta.get("badge_kind", "blue")
    reasons_html = " ".join(
        f'<span class="gs-badge gs-badge-{bkind}" style="margin-right:6px; margin-top:4px;">{rc}</span>'
        for rc in reason_codes
    )
    auth_banner = ""
    if action == "PRIME_RELEASE_CANDIDATE":
        auth_color = COLOR["amber"]
        if approval_status == "HUMAN_AUTHORIZED_IN_DEMO":
            auth_color = COLOR["green"]
        elif approval_status == "REJECTED_OR_HELD":
            auth_color = COLOR["red"]
        auth_banner = f"""
        <div style="margin-top:12px; padding:10px 14px; background:rgba(229,161,26,0.08); border-left:3px solid {auth_color}; border-radius:4px; font-size:0.82rem;">
          <strong>HUMAN / QUALITY AUTHORIZATION REQUIRED:</strong> PrimePath is strictly advisory and never certifies or releases polymer.
          Required Sign-Off Role: <span class="tech-val">{approver_role}</span> &nbsp;|&nbsp;
          Current Status: <strong>{approval_status}</strong>
        </div>
        """

    st.markdown(
        f"""
<div style="background:{COLOR['white']}; border:2px solid {col}; border-radius:8px; padding:20px 24px; margin-bottom:18px;">
  <div style="display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px;">
    <div>
      <div style="font-size:0.70rem; font-weight:700; text-transform:uppercase; letter-spacing:0.1em; color:{COLOR['text2']}; margin-bottom:4px;">
        PrimePath Disposition Recommendation (13 Hard Gates Evaluated First)
      </div>
      <div style="font-family:{FONT_TECH}; font-size:1.75rem; font-weight:700; color:{col}; letter-spacing:-0.01em;">
        {action_meta.get('display', action)}
      </div>
      <div style="font-size:0.88rem; color:{COLOR['text']}; margin-top:6px; line-height:1.45;">
        {narrative or action_meta.get('summary', '')}
      </div>
    </div>
    <div style="text-align:right;">
      <span class="gs-badge gs-badge-{bkind}" style="font-size:0.75rem; padding:5px 12px;">ACTION: {action}</span>
    </div>
  </div>
  <div style="margin-top:12px;">
    <span style="font-size:0.72rem; font-weight:600; color:{COLOR['text2']}; text-transform:uppercase; margin-right:8px;">Reason Codes:</span>
    {reasons_html}
  </div>
  {auth_banner}
</div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_brand():
    """Render the sidebar logo and brand block."""
    import streamlit as st

    logo_path = os.path.join(os.path.dirname(__file__), "gradeshift_ai.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        img_src = f"data:image/png;base64,{b64}"
    else:
        img_src = f"data:image/png;base64,{GS_LOGO_B64}"

    st.sidebar.markdown(
        f"""
<div class="sidebar-logo-container">
  <img src="{img_src}" class="sidebar-logo-img" alt="GradeShift PrimePath" style="max-width:175px;">
  <div class="sidebar-logo-sub">PRIMEPATH DECISION LAYER</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_nav():
    """Render the custom sidebar navigation and PrimePath governance context."""
    import streamlit as st

    def _safe_page_link(page: str, label: str):
        try:
            st.sidebar.page_link(page, label=label)
        except Exception:
            st.sidebar.markdown(
                f'<div style="padding:4px 16px; font-size:0.84rem; color:rgba(255,255,255,0.85);">{label}</div>',
                unsafe_allow_html=True,
            )

    st.sidebar.markdown('<div class="gs-nav-section">Decision Layer</div>', unsafe_allow_html=True)
    _safe_page_link("app.py", label="Decision Cockpit (Home)")
    _safe_page_link("pages/1_Grade_Transition.py", label="1 · Transition Replay")
    _safe_page_link("pages/3_AI_Optimizer.py", label="3 · Disposition Workbench")

    st.sidebar.markdown('<div class="gs-nav-section">Evidence & Assurance</div>', unsafe_allow_html=True)
    _safe_page_link("pages/2_Soft_Sensor.py", label="2 · Quality Evidence")
    _safe_page_link("pages/4_Safety.py", label="4 · Transition Guardian")

    st.sidebar.markdown('<div class="gs-nav-section">Value & Memory</div>', unsafe_allow_html=True)
    _safe_page_link("pages/5_Economics.py", label="5 · Economic Ledger")
    _safe_page_link("pages/6_Digital_Twin.py", label="6 · Memory & Assurance")

    st.sidebar.markdown(
        """
<div style="margin-top: 24px; padding: 14px; border-top: 1px solid rgba(255,255,255,0.12);">
  <div style="font-size:0.65rem; color:rgba(255,255,255,0.45); text-transform:uppercase; margin-bottom:10px; letter-spacing: 0.1em; font-weight:600;">PrimePath Boundary</div>
  <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
    <span style="font-size:0.73rem; color:rgba(255,255,255,0.55);">AUTHORITY</span>
    <span style="font-size:0.73rem; color:#18BFC3; font-weight:600;">ADVISORY ONLY</span>
  </div>
  <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
    <span style="font-size:0.73rem; color:rgba(255,255,255,0.55);">DCS / SETPOINTS</span>
    <span style="font-size:0.73rem; color:white;">READ-ONLY (NONE)</span>
  </div>
  <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
    <span style="font-size:0.73rem; color:rgba(255,255,255,0.55);">QC SIGN-OFF</span>
    <span style="font-size:0.73rem; color:#20A873; font-weight:600;">MANDATORY</span>
  </div>
  <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
    <span style="font-size:0.73rem; color:rgba(255,255,255,0.55);">EVIDENCE CEILING</span>
    <span style="font-size:0.73rem; color:#E5A11A; font-weight:600;">SYNTHETIC E2/E3</span>
  </div>
</div>
        """,
        unsafe_allow_html=True,
    )


def section_header(text: str):
    import streamlit as st

    st.markdown(f'<div class="gs-section-header">{text}</div>', unsafe_allow_html=True)


def page_title(title: str, subtitle: str = "", eyebrow: str = ""):
    import streamlit as st

    if eyebrow:
        st.markdown(f'<div class="gs-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="gs-page-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="gs-page-subtitle">{subtitle}</div>', unsafe_allow_html=True)


def kpi_card(label: str, value: str, unit: str = "", delta: str = "", delta_type: str = "neu"):
    """Return HTML for a structured KPI item."""
    delta_class = f"delta-{delta_type}"
    delta_html = f'<div class="gs-kpi-delta {delta_class}">{delta}</div>' if delta else ""
    return f"""
<div class="gs-kpi-container">
  <div class="gs-kpi-label">{label}</div>
  <div class="gs-kpi-value">{value}<span class="gs-kpi-unit">{unit}</span></div>
  {delta_html}
</div>
    """


def insight(text: str, kind: str = "blue"):
    """kind: blue | amber | green"""
    import streamlit as st

    st.markdown(f'<div class="gs-insight">{text}</div>', unsafe_allow_html=True)


def badge(text: str, kind: str = "blue"):
    return f'<span class="gs-badge gs-badge-{kind}">{text}</span>'


def panel_open(title: str = ""):
    """Returns opening HTML for a panel. Must be closed with panel_close()."""
    title_html = f'<div class="gs-panel-title">{title}</div>' if title else ""
    return f'<div class="gs-panel">{title_html}'


def panel_close():
    return "</div>"


def data_row(label: str, value: str):
    return f"""
<div class="gs-data-row">
  <span class="gs-data-row-label">{label}</span>
  <span class="gs-data-row-value">{value}</span>
</div>
    """


def chart_layout(title: str = "", height: int = 380, show_legend: bool = True, **kwargs):
    """Return a standardised Plotly layout dict."""
    return dict(
        title=dict(
            text=title,
            font=dict(size=14, color=COLOR["navy"], family=FONT_PRIMARY, weight=600),
            x=0,
            xanchor="left",
            pad=dict(l=4),
        ),
        height=height,
        font=dict(family=FONT_PRIMARY, color=COLOR["text"], size=12),
        paper_bgcolor=COLOR["white"],
        plot_bgcolor=COLOR["white"],
        showlegend=show_legend,
        legend=dict(
            orientation="h",
            y=-0.18,
            x=0,
            font=dict(size=11, color=COLOR["text2"]),
            bgcolor="rgba(0,0,0,0)",
        ),
        xaxis=dict(
            gridcolor="#EDF0F4",
            gridwidth=1,
            linecolor=COLOR["border"],
            tickfont=dict(size=11, color=COLOR["text2"]),
            title_font=dict(size=11, color=COLOR["text2"]),
        ),
        yaxis=dict(
            gridcolor="#EDF0F4",
            gridwidth=1,
            linecolor=COLOR["border"],
            tickfont=dict(size=11, color=COLOR["text2"]),
            title_font=dict(size=11, color=COLOR["text2"]),
        ),
        margin=dict(l=12, r=12, t=40, b=40),
        **kwargs,
    )
