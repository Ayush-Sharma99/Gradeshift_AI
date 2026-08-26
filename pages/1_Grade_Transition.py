"""
GradeShift AI — Page 1: Grade Transition
Side-by-side comparison of Conservative Ramp vs. AI-Optimised trajectory.
The "AI Aha" moment visualisation.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import streamlit as st
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from gs_theme import (
    inject_css, topbar, sidebar_brand, sidebar_nav, page_title,
    chart_layout, COLOR, FONT_PRIMARY, FONT_TECH
)
from transition_optimizer import TransitionOptimizer

st.set_page_config(page_title="Grade Transition · GradeShift AI", page_icon="⬡", layout="wide")
inject_css()

# ── Global configuration ───────────────────────────────────────
GRADES = {
    'A': {'name': 'HDPE Pipe (PE100)',   'short': 'HDPE-P',  'MFI': 0.3,  'density': 0.949},
    'B': {'name': 'HDPE Blow Moulding',  'short': 'HDPE-BM', 'MFI': 8.0,  'density': 0.954},
    'C': {'name': 'LLDPE Film Grade',    'short': 'LLDPE-F', 'MFI': 1.0,  'density': 0.918},
}
ig, tg = 'A', 'B'
prod_rate = 50.0

sidebar_brand()
sidebar_nav()

@st.cache_data(show_spinner=False)
def run_sims(ig, tg, pr):
    opt = TransitionOptimizer(ig, tg, pr * 1000)
    base = opt.simulate_linear_ramp(ramp_time_min=240, sim_time_min=600)
    ai   = opt.optimize_bang_bang()
    return base, ai, opt.target_MFI, opt.spec_band

with st.spinner("Computing…"):
    baseline, ai_traj, target_MFI, spec_band = run_sims(ig, tg, prod_rate)

def first_on_spec(sim, tgt, band):
    lo, hi = tgt*(1-band), tgt*(1+band)
    for i, v in enumerate(sim['MFI_bed']):
        if lo <= v <= hi:
            if all(lo <= sim['MFI_bed'][j] <= hi for j in range(i, min(i+20, len(sim['MFI_bed'])))):
                return sim['time'][i]
    return sim['time'][-1]

base_t = first_on_spec(baseline, target_MFI, spec_band)
ai_t   = first_on_spec(ai_traj,  target_MFI, spec_band)
base_os = (base_t/60)*prod_rate
ai_os   = (ai_t/60)*prod_rate
saved_t = base_t - ai_t
saved_p = base_os - ai_os

topbar(f"{GRADES[ig]['short']}", f"{GRADES[tg]['short']}", "Bathinda · Unit 03")

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom: 24px;">
<div class="gs-eyebrow">GRADE TRANSITION / OPTIMIZATION</div>
<div class="gs-page-title">Grade Transition</div>
<div class="gs-page-subtitle">Compare the baseline operating trajectory with the GradeShift AI optimized trajectory.</div>
</div>
""", unsafe_allow_html=True)

# ── The "Aha" side-by-side panels ─────────────────────────────
col_b, col_ai = st.columns(2, gap="large")
times_b  = [t/60 for t in baseline['time']]
times_ai = [t/60 for t in ai_traj['time']]
lo_s = target_MFI*(1-spec_band)
hi_s = target_MFI*(1+spec_band)

def make_traj_fig(times, mfi_bed, h2m, label, color_bed, color_h2m, base_t_hrs, base_os_t, title_label):
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.7, 0.3], vertical_spacing=0.08,
    )
    
    # Target zone
    fig.add_hrect(y0=lo_s, y1=hi_s, fillcolor=COLOR['spec_fill'], line_width=0, row=1, col=1)

    # Off-spec region shading
    mask_os = [t <= base_t_hrs for t in times]
    fig.add_trace(go.Scatter(
        x=[t for t, m in zip(times, mask_os) if m],
        y=[v for v, m in zip(mfi_bed, mask_os) if m],
        name='Off-spec period',
        fill='tozeroy', fillcolor=COLOR['offspec_fill'],
        line=dict(width=0), showlegend=False, hoverinfo='skip'
    ), row=1, col=1)

    # Bed average trajectory
    fig.add_trace(go.Scatter(x=times, y=mfi_bed, name='Trajectory',
        line=dict(color=color_bed, width=3)), row=1, col=1)

    # Target line and on-spec marker
    fig.add_hline(y=target_MFI, line_dash="dash", line_color=COLOR['green'], line_width=1, row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=[base_t_hrs], y=[target_MFI], mode='markers',
        marker=dict(color=color_bed, size=10, line=dict(color='white', width=2)),
        name='Completion point', showlegend=False
    ), row=1, col=1)

    # H2M subplot
    fig.add_trace(go.Scatter(x=times, y=h2m, name='H₂/M Setpoint',
        line=dict(color=color_h2m, width=2),
        fill='tozeroy', fillcolor=f"rgba({int(color_h2m[1:3],16)},{int(color_h2m[3:5],16)},{int(color_h2m[5:7],16)},0.06)",
    ), row=2, col=1)

    layout = chart_layout("", height=420, show_legend=False)
    fig.update_yaxes(title_text="MFI (log scale)", type="log", gridcolor="#EDF0F4", row=1, col=1)
    fig.update_yaxes(title_text="H₂/M Ratio", gridcolor="#EDF0F4", row=2, col=1)
    fig.update_xaxes(title_text="Time (hours)", gridcolor="#EDF0F4", row=2, col=1)
    
    # Annotate completion point
    fig.add_annotation(
        x=base_t_hrs, y=np.log10(target_MFI) if target_MFI > 0 else target_MFI,
        text=f"{base_t_hrs:.1f}h",
        showarrow=True, arrowhead=1, ax=-40, ay=-30,
        font=dict(color=color_bed, family=FONT_TECH, size=12),
        row=1, col=1
    )

    fig.update_layout(**layout)
    return fig

with col_b:
    st.markdown(f"""
<div style="margin-bottom: 16px;">
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 4px;">Current Approach</div>
<div style="font-size: 1.15rem; font-weight: 600; color: {COLOR['navy']};">Conservative linear ramp</div>
</div>
    """, unsafe_allow_html=True)
    
    fig_b = make_traj_fig(
        times_b, baseline['MFI_bed'], baseline['H2_M'],
        "Baseline", COLOR['baseline'], "#8C99A8", base_t/60, base_os, "Baseline"
    )
    st.plotly_chart(fig_b, use_container_width=True, config={"displayModeBar": False})

with col_ai:
    st.markdown(f"""
<div style="margin-bottom: 16px;">
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['blue']}; font-weight: 600; margin-bottom: 4px;">GradeShift AI</div>
<div style="font-size: 1.15rem; font-weight: 600; color: {COLOR['blue']};">Physics-informed optimized trajectory</div>
</div>
    """, unsafe_allow_html=True)

    fig_ai = make_traj_fig(
        times_ai, ai_traj['MFI_bed'], ai_traj['H2_M'],
        "GradeShift AI", COLOR['ai_traj'], COLOR['ai_traj'], ai_t/60, ai_os, "GradeShift AI"
    )
    st.plotly_chart(fig_ai, use_container_width=True, config={"displayModeBar": False})


# ── Result block ──────────────────────────────────────────────
st.markdown('<div style="margin-top: 32px; border-top: 1px solid #DCE3EA; padding-top: 24px;"></div>', unsafe_allow_html=True)

p_saved_t = (saved_t / base_t) * 100
p_saved_os = (saved_p / base_os) * 100

st.markdown(f"""
<div style="margin-bottom: 16px;">
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['navy']}; font-weight: 600;">Result</div>
</div>
<div style="display: flex; gap: 48px;">
<div>
<div style="font-family: {FONT_TECH}; font-size: 2.2rem; font-weight: 600; color: {COLOR['navy']};">-{p_saved_t:.0f}%<span style="font-family: {FONT_PRIMARY}; font-size: 1rem; color: {COLOR['text2']}; font-weight: 400; margin-left: 8px;">transition time</span></div>
</div>
<div>
<div style="font-family: {FONT_TECH}; font-size: 2.2rem; font-weight: 600; color: {COLOR['navy']};">-{p_saved_os:.0f}%<span style="font-family: {FONT_PRIMARY}; font-size: 1rem; color: {COLOR['text2']}; font-weight: 400; margin-left: 8px;">off-spec product</span></div>
</div>
<div>
<div style="font-family: {FONT_TECH}; font-size: 2.2rem; font-weight: 600; color: {COLOR['green']};">+{saved_p:.0f} t<span style="font-family: {FONT_PRIMARY}; font-size: 1rem; color: {COLOR['text2']}; font-weight: 400; margin-left: 8px;">prime polymer recovered</span></div>
</div>
</div>
""", unsafe_allow_html=True)
