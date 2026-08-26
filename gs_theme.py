"""
GradeShift AI — Design System & Shared Theme
All colors, typography tokens, and reusable HTML/CSS components live here.
Import this module at the top of every page.
"""

# Base64 encoded official GradeShift AI logo
GS_LOGO_B64 = "iVBORw0KGgoAAAANSUhEUgAAAgAAAAEoCAYAAAC0V1LzAAABrklEQVR4nO3c0W3CMBRF0Z/yQd6/qXSSZqC0SqkSSW5w7j4j+TgyT1xHAAAAAAAAAAAAAAD4l/X+M+ZfP56n8WPMv358T+O/nAAAgH8hAACAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCACAIAgAgCAIAIAgCBvY/56n8aXwL95HMevvPzDqXQCAABK+AHWswmC4r3gVAAAAABJRU5ErkJggg=="

# ──────────────────────────────────────────────────────────────
# DESIGN TOKENS
# ──────────────────────────────────────────────────────────────
COLOR = {
    # Brand
    "navy":    "#062B52",
    "blue":    "#1769E0",
    "cyan":    "#18BFC3",
    # Semantic
    "green":   "#20A873",
    "amber":   "#E5A11A",
    "red":     "#D64545",
    # Neutrals
    "bg":      "#F5F7FA",
    "white":   "#FFFFFF",
    "text":    "#142033",
    "text2":   "#5B687A",
    "border":  "#DCE3EA",
    "card":    "#FFFFFF",
    # Chart aliases
    "baseline":    "#8C99A8",
    "ai_traj":     "#1769E0",
    "ai_signal":   "#18BFC3",
    "spec_fill":   "rgba(32,168,115,0.06)",
    "offspec_fill":"rgba(214,69,69,0.06)",
    "amber_fill":  "rgba(229,161,26,0.10)",
}

FONT_PRIMARY = "'IBM Plex Sans', -apple-system, sans-serif"
FONT_TECH = "'IBM Plex Mono', monospace"

# ──────────────────────────────────────────────────────────────
# FULL CSS BLOCK
# ──────────────────────────────────────────────────────────────
_CSS = f"""
<style>
/* ── Google Font import ── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&display=swap');

/* ── Root reset ── */

  .stMarkdown, p, h1, h2, h3, h4, h5, h6, li, .gs-topbar, .gs-panel {{
      font-family: {FONT_PRIMARY};
  }}
  
/* ── Typography Classes ── */
.tech-val {{ font-family: {FONT_TECH}; font-weight: 500; font-size: 1.05em; }}
.tech-unit {{ font-family: {FONT_PRIMARY}; font-size: 0.85em; color: {COLOR['text2']}; margin-left: 2px; }}

/* ── Sidebar ── */

section[data-testid="stSidebar"] {{ color: rgba(255,255,255,0.85) !important; font-family: {FONT_PRIMARY}; }}

section[data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.12) !important; margin: 16px 0 !important; }}
section[data-testid="stSidebarNav"] {{ display: none !important; }} /* Hide default nav */

/* ── Streamlit chrome is left native ── */

/* Ensure the sidebar toggle is ALWAYS visible on any background */
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
/* Completely hide the header background bar so it does not block top content */
[data-testid="stHeader"] {{
    background: transparent !important;
}}


/* ── Custom Sidebar Navigation ── */
.gs-nav-section {{
    font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.1em;
    color: rgba(255,255,255,0.4); margin: 24px 0 8px 16px; font-weight: 600;
}}
.gs-nav-link {{
    display: block; padding: 8px 16px; margin: 2px 8px; border-radius: 4px;
    color: rgba(255,255,255,0.75); text-decoration: none; font-size: 0.85rem;
    transition: all 0.2s;
}}
.gs-nav-link:hover {{ background: rgba(255,255,255,0.08); color: #fff; }}
.gs-nav-link.active {{ background: rgba(23,105,224,0.15); color: {COLOR['cyan']}; font-weight: 500; border-left: 3px solid {COLOR['cyan']}; }}

/* ── Top application header bar ── */
.gs-topbar {{
    background: {COLOR['white']}; border-bottom: 1px solid {COLOR['border']};
    padding: 12px 28px; display: flex; align-items: center; gap: 32px;
    margin-bottom: 24px; position: sticky; top: 3.5rem; z-index: 100;
}}
.gs-topbar-field {{ display: flex; flex-direction: column; }}
.gs-topbar-label {{ font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.08em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 2px; }}
.gs-topbar-value {{ font-size: 0.85rem; font-weight: 600; color: {COLOR['navy']}; }}
.gs-topbar-right {{ margin-left: auto; display: flex; align-items: center; gap: 12px; }}

/* ── Status pills ── */
.gs-status {{ display: inline-flex; align-items: center; gap: 6px; padding: 4px 12px; border-radius: 4px; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; }}
.gs-status-online {{ background: rgba(32,168,115,0.1); color: {COLOR['green']}; }}
.gs-status-advisory {{ background: rgba(23,105,224,0.1); color: {COLOR['blue']}; }}
.gs-status-demo {{ background: rgba(229,161,26,0.1); color: {COLOR['amber']}; }}
.gs-status-dot {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}

/* ── Page Headers & Section Headers ── */
.gs-eyebrow {{ font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; margin-bottom: 4px; }}
.gs-page-title {{ font-size: 2.1rem; font-weight: 600; color: {COLOR['navy']}; letter-spacing: -0.02em; margin-bottom: 6px; }}
.gs-page-subtitle {{ font-size: 0.95rem; color: {COLOR['text2']}; margin-bottom: 28px; }}

.gs-section-header {{
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.1em; color: {COLOR['navy']};
    border-bottom: 1px solid {COLOR['border']};
    padding-bottom: 8px; margin-bottom: 20px; margin-top: 16px;
}}

/* ── KPIs ── */
.gs-kpi-container {{ display: flex; flex-direction: column; }}
.gs-kpi-label {{ font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 6px; }}
.gs-kpi-value {{ font-family: {FONT_TECH}; font-size: 2.2rem; font-weight: 600; color: {COLOR['navy']}; line-height: 1; }}
.gs-kpi-unit {{ font-family: {FONT_PRIMARY}; font-size: 1rem; font-weight: 400; color: {COLOR['text2']}; margin-left: 4px; }}
.gs-kpi-delta {{ font-size: 0.8rem; font-weight: 500; margin-top: 8px; }}
.delta-pos {{ color: {COLOR['green']}; }}
.delta-neg {{ color: {COLOR['red']}; }}
.delta-neu {{ color: {COLOR['text2']}; }}

/* ── Panels / Structured Rows (Less Cards) ── */
.gs-panel {{
    background: {COLOR['white']}; border: 1px solid {COLOR['border']};
    border-radius: 8px; padding: 24px; margin-bottom: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}}
.gs-panel-title {{
    font-size: 0.85rem; font-weight: 600; color: {COLOR['navy']};
    letter-spacing: 0.02em; margin-bottom: 16px;
}}
.gs-data-row {{
    display: flex; align-items: baseline; justify-content: space-between;
    padding: 10px 0; border-bottom: 1px solid {COLOR['border']};
    font-size: 0.85rem;
}}
.gs-data-row:last-child {{ border-bottom: none; padding-bottom: 0; }}
.gs-data-row-label {{ color: {COLOR['text2']}; }}
.gs-data-row-value {{ font-family: {FONT_TECH}; color: {COLOR['navy']}; font-weight: 500; }}

/* ── Insight block ── */
.gs-insight {{
    background: {COLOR['white']}; border-left: 3px solid {COLOR['blue']};
    padding: 16px 20px; font-size: 0.9rem; 
    margin: 16px 0; border-radius: 0 4px 4px 0;
    box-shadow: 0 1px 2px rgba(0,0,0,0.02); line-height: 1.5;
}}
.gs-insight strong {{ color: {COLOR['navy']}; font-weight: 600; }}

/* ── Badge ── */
.gs-badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 0.65rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
}}
.gs-badge-blue {{ background: rgba(23,105,224,0.1); color: {COLOR['blue']}; }}
.gs-badge-green {{ background: rgba(32,168,115,0.1); color: {COLOR['green']}; }}
.gs-badge-amber {{ background: rgba(229,161,26,0.1); color: {COLOR['amber']}; }}

/* ── Constraint bar ── */
.gs-constraint-row {{ display: flex; align-items: center; gap: 16px; margin: 12px 0; }}
.gs-constraint-label {{ font-size: 0.85rem;  font-weight: 500; width: 160px; flex-shrink: 0; }}
.gs-constraint-bar-wrap {{ flex: 1; height: 6px; background: {COLOR['border']}; border-radius: 3px; position: relative; }}
.gs-constraint-bar-fill {{ height: 100%; border-radius: 3px; transition: width 0.4s ease; }}
.gs-constraint-value {{ font-family: {FONT_TECH}; font-size: 0.85rem; font-weight: 600; color: {COLOR['navy']}; width: 80px; text-align: right; flex-shrink: 0; }}
.gs-constraint-limit {{ font-family: {FONT_TECH}; font-size: 0.75rem; color: {COLOR['text2']}; width: 80px; flex-shrink: 0; }}
.gs-constraint-status {{ font-size: 0.75rem; font-weight: 600; width: 60px; text-align: right; letter-spacing: 0.05em; }}

/* ── Sidebar Brand ── */
.sidebar-logo-container {{ padding: 20px 16px 32px 16px; text-align: left; }}
.sidebar-logo-img {{ max-width: 160px; height: auto; }}
.sidebar-logo-sub {{ font-size: 0.65rem; color: rgba(255,255,255,0.4); text-transform: uppercase; letter-spacing: 0.1em; margin-top: 8px; font-weight: 600; }}

/* ── Overrides ── */
hr {{ border-color: {COLOR['border']} !important; margin: 24px 0 !important; }}
.stSelectbox > div > div {{ background: rgba(255,255,255,0.05) !important; border-color: rgba(255,255,255,0.1) !important; color: #fff !important; font-size: 0.85rem !important; }}
div[data-testid="stMetricValue"] {{ font-family: {FONT_TECH} !important; color: {COLOR['navy']} !important; }}

/* ── Ultimate Sidebar Visibility Fix ── */
[data-testid="stSidebar"] * {{
    color: rgba(255, 255, 255, 0.95) !important;
}}
/* Hide the ugly default Streamlit page navigation */
[data-testid="stSidebarNav"] {{
    display: none !important;
}}

</style>
"""


def inject_css():
    """Call this once at the top of every Streamlit page."""
    import streamlit as st
    st.markdown(_CSS, unsafe_allow_html=True)


def topbar(current_grade_from: str, current_grade_to: str, unit: str = "UNIPOL™ PE — Line 03"):
    """Render the sticky top application header bar."""
    import streamlit as st
    st.markdown(f"""
<div class="gs-topbar">
<div class="gs-topbar-field">
<div class="gs-topbar-label">HMEL Polymer Complex</div>
<div class="gs-topbar-value">{unit}</div>
</div>
<div class="gs-topbar-field" style="margin-left: 24px;">
<div class="gs-topbar-label">Active Transition</div>
<div class="gs-topbar-value">{current_grade_from} → {current_grade_to}</div>
</div>
<div class="gs-topbar-right">
<span class="gs-status gs-status-online"><span class="gs-status-dot"></span>ONLINE</span>
<span class="gs-status gs-status-advisory">ADVISORY</span>
<span class="gs-status gs-status-demo">SIMULATION</span>
</div>
</div>
    """, unsafe_allow_html=True)


def sidebar_brand():
    """Render the sidebar logo and brand block."""
    import streamlit as st
    import base64
    import os
    
    logo_path = os.path.join(os.path.dirname(__file__), "gradeshift_ai.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        img_src = f"data:image/png;base64,{b64}"
    else:
        img_src = ""

    st.sidebar.markdown(f"""
<div class="sidebar-logo-container">
<img src="{img_src}" class="sidebar-logo-img" alt="GradeShift AI" style="max-width:180px;">
<div class="sidebar-logo-sub">HMEL i-QUEST 2026</div>
</div>
    """, unsafe_allow_html=True)


def sidebar_nav():
    """Render the custom sidebar navigation and system context."""
    import streamlit as st
    import os
    
    st.sidebar.markdown('<div class="gs-nav-section">Operations</div>', unsafe_allow_html=True)
    st.sidebar.page_link("app.py", label="Overview")
    st.sidebar.page_link("pages/1_Grade_Transition.py", label="Grade Transition")
    st.sidebar.page_link("pages/3_AI_Optimizer.py", label="AI Optimizer")
    
    st.sidebar.markdown('<div class="gs-nav-section">Intelligence</div>', unsafe_allow_html=True)
    st.sidebar.page_link("pages/2_Soft_Sensor.py", label="Soft Sensor")
    st.sidebar.page_link("pages/6_Digital_Twin.py", label="Digital Twin")
    
    st.sidebar.markdown('<div class="gs-nav-section">Governance</div>', unsafe_allow_html=True)
    st.sidebar.page_link("pages/4_Safety.py", label="Safety")
    st.sidebar.page_link("pages/5_Economics.py", label="Economics")
    
    st.sidebar.markdown("""
<div style="margin-top: 40px; padding: 16px; border-top: 1px solid rgba(255,255,255,0.1);">
<div style="font-size:0.65rem; color:rgba(255,255,255,0.4); text-transform:uppercase; margin-bottom:12px; letter-spacing: 0.1em; font-weight:600;">System Context</div>
<div style="display:flex; justify-content:space-between; margin-bottom:6px;">
<span style="font-size:0.75rem; color:rgba(255,255,255,0.5);">UNIT</span>
<span style="font-size:0.75rem; color:white; font-family:'IBM Plex Sans';">UNIPOL™ PE — Line 03</span>
</div>
<div style="display:flex; justify-content:space-between; margin-bottom:6px;">
<span style="font-size:0.75rem; color:rgba(255,255,255,0.5);">MODE</span>
<span style="font-size:0.75rem; color:#18BFC3; font-family:'IBM Plex Sans'; font-weight:500;">ADVISORY</span>
</div>
<div style="display:flex; justify-content:space-between; margin-bottom:6px;">
<span style="font-size:0.75rem; color:rgba(255,255,255,0.5);">STATUS</span>
<span style="font-size:0.75rem; color:#20A873; font-family:'IBM Plex Sans'; font-weight:500;">● ONLINE</span>
</div>
<div style="display:flex; justify-content:space-between; margin-bottom:6px;">
<span style="font-size:0.75rem; color:rgba(255,255,255,0.5);">SIMULATION</span>
<span style="font-size:0.75rem; color:#E5A11A; font-family:'IBM Plex Sans'; font-weight:500;">● ACTIVE</span>
</div>
</div>
    """, unsafe_allow_html=True)


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
    return '</div>'


def data_row(label: str, value: str):
    return f"""
<div class="gs-data-row">
<span class="gs-data-row-label">{label}</span>
<span class="gs-data-row-value">{value}</span>
</div>
    """


# ──────────────────────────────────────────────────────────────
# SHARED PLOTLY LAYOUT DEFAULTS
# ──────────────────────────────────────────────────────────────
def chart_layout(title: str = "", height: int = 380, show_legend: bool = True, **kwargs):
    """Return a standardised Plotly layout dict."""
    return dict(
        title=dict(text=title, font=dict(size=14, color=COLOR['navy'], family=FONT_PRIMARY, weight=600), x=0, xanchor='left', pad=dict(l=4)),
        height=height,
        font=dict(family=FONT_PRIMARY, color=COLOR['text'], size=12),
        paper_bgcolor=COLOR['white'],
        plot_bgcolor=COLOR['white'],
        showlegend=show_legend,
        legend=dict(
            orientation="h", y=-0.18, x=0,
            font=dict(size=11, color=COLOR['text2']),
            bgcolor="rgba(0,0,0,0)"
        ),
        xaxis=dict(
            gridcolor="#EDF0F4", gridwidth=1,
            linecolor=COLOR['border'], tickfont=dict(size=11, color=COLOR['text2']),
            title_font=dict(size=11, color=COLOR['text2'])
        ),
        yaxis=dict(
            gridcolor="#EDF0F4", gridwidth=1,
            linecolor=COLOR['border'], tickfont=dict(size=11, color=COLOR['text2']),
            title_font=dict(size=11, color=COLOR['text2'])
        ),
        margin=dict(l=12, r=12, t=40, b=40),
        **kwargs
    )
