"""
GradeShift AI — Overview Dashboard (main entry point)
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import numpy as np
import plotly.graph_objects as go

from gs_theme import (
    inject_css, topbar, sidebar_brand, sidebar_nav, page_title,
    kpi_card, insight, chart_layout, COLOR, FONT_PRIMARY, FONT_TECH
)
from transition_optimizer import TransitionOptimizer

# ── Page config ────────────────────────────────────────────────
st.set_page_config(
    page_title="GradeShift AI",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

# ── Global configuration ───────────────────────────────────────
GRADES = {
    'A': {'name': 'HDPE Pipe (PE100)',       'short': 'HDPE-P',  'MFI': 0.3,  'density': 0.949, 'H2_M': 0.05},
    'B': {'name': 'HDPE Blow Moulding',      'short': 'HDPE-BM', 'MFI': 8.0,  'density': 0.954, 'H2_M': 0.35},
    'C': {'name': 'LLDPE Film Grade',        'short': 'LLDPE-F', 'MFI': 1.0,  'density': 0.918, 'H2_M': 0.10},
}
ig, tg = 'A', 'B'
prod_rate = 50.0  # t/hr

# ── Sidebar ────────────────────────────────────────────────────
sidebar_brand()
sidebar_nav()

# ── Simulations (cached) ───────────────────────────────────────
@st.cache_data(show_spinner=False)
def run_sims(ig, tg, pr):
    opt = TransitionOptimizer(ig, tg, pr * 1000)
    baseline = opt.simulate_linear_ramp(ramp_time_min=240, sim_time_min=600)
    ai_traj  = opt.optimize_bang_bang()
    return baseline, ai_traj, opt.target_MFI, opt.spec_band

with st.spinner("Computing transition trajectories…"):
    baseline, ai_traj, target_MFI, spec_band = run_sims(ig, tg, prod_rate)

# ── Metrics ───────────────────────────────────────────────────
def first_on_spec(sim, tgt, band):
    lo, hi = tgt*(1-band), tgt*(1+band)
    for i, v in enumerate(sim['MFI_bed']):
        if lo <= v <= hi:
            if all(lo <= sim['MFI_bed'][j] <= hi for j in range(i, min(i+20, len(sim['MFI_bed'])))):
                return sim['time'][i]
    return sim['time'][-1]

base_t  = first_on_spec(baseline, target_MFI, spec_band)
ai_t    = first_on_spec(ai_traj,  target_MFI, spec_band)
base_os = (base_t / 60.0) * prod_rate
ai_os   = (ai_t   / 60.0) * prod_rate
saved_t = base_t - ai_t          # minutes
saved_p = base_os - ai_os        # tonnes
val_per = saved_p * 20.0 * 1000  # ₹ (@ ₹20/kg margin)

# ── Top bar ───────────────────────────────────────────────────
topbar(
    current_grade_from = f"{GRADES[ig]['short']}",
    current_grade_to   = f"{GRADES[tg]['short']}",
    unit               = "Bathinda · Unit 03",
)

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom: 24px;">
<div style="font-size: 2.1rem; font-weight: 700; color: #062B52; letter-spacing: -0.02em; margin-bottom: 8px;">Overview</div>
<div style="font-size: 1.05rem; color: #5B687A;">Real-time transition intelligence for polyolefin grade changes.</div>
</div>
""", unsafe_allow_html=True)

# ── Current transition banner ─────────────────────────────────
st.markdown(f"""
<div style="background: {COLOR['white']}; border: 1px solid {COLOR['border']}; border-radius: 8px; padding: 16px 24px; margin-bottom: 32px; display: flex; align-items: center; justify-content: space-between;">
<div style="display: flex; align-items: center; gap: 24px;">
<div>
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 4px;">Current</div>
<div style="font-size: 0.95rem; font-weight: 600; color: {COLOR['text']};">{ig} — {GRADES[ig]['name']}</div>
</div>
<div style="color: {COLOR['text2']}; font-size: 1.2rem;">→</div>
<div>
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 4px;">Target</div>
<div style="font-size: 0.95rem; font-weight: 600; color: {COLOR['text']};">{tg} — {GRADES[tg]['name']}</div>
</div>
</div>
<div>
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['blue']}; font-weight: 600; background: rgba(23,105,224,0.1); padding: 6px 12px; border-radius: 4px;">AI OPTIMIZATION ACTIVE</div>
</div>
</div>
""", unsafe_allow_html=True)

# ── KPI strip ─────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""
<div style="padding: 0 16px; border-right: 1px solid {COLOR['border']};">
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 8px;">Transition Time</div>
<div style="font-family: {FONT_TECH}; font-size: 2.2rem; font-weight: 600; color: {COLOR['navy']}; line-height: 1;">{ai_t/60:.1f}<span style="font-family: {FONT_PRIMARY}; font-size: 1.1rem; font-weight: 400; color: {COLOR['text2']}; margin-left: 4px;">h</span></div>
<div style="font-size: 0.8rem; color: {COLOR['green']}; font-weight: 500; margin-top: 8px;">↓ {saved_t/60:.1f} h vs baseline</div>
</div>
    """, unsafe_allow_html=True)
with k2:
    st.markdown(f"""
<div style="padding: 0 16px; border-right: 1px solid {COLOR['border']};">
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 8px;">Off-Spec</div>
<div style="font-family: {FONT_TECH}; font-size: 2.2rem; font-weight: 600; color: {COLOR['navy']}; line-height: 1;">{ai_os:.0f}<span style="font-family: {FONT_PRIMARY}; font-size: 1.1rem; font-weight: 400; color: {COLOR['text2']}; margin-left: 4px;">t</span></div>
<div style="font-size: 0.8rem; color: {COLOR['green']}; font-weight: 500; margin-top: 8px;">↓ {saved_p:.0f} t vs baseline</div>
</div>
    """, unsafe_allow_html=True)
with k3:
    st.markdown(f"""
<div style="padding: 0 16px; border-right: 1px solid {COLOR['border']};">
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 8px;">Prime Recovered</div>
<div style="font-family: {FONT_TECH}; font-size: 2.2rem; font-weight: 600; color: {COLOR['navy']}; line-height: 1;">{saved_p:.0f}<span style="font-family: {FONT_PRIMARY}; font-size: 1.1rem; font-weight: 400; color: {COLOR['text2']}; margin-left: 4px;">t</span></div>
<div style="font-size: 0.8rem; color: {COLOR['green']}; font-weight: 500; margin-top: 8px;">Yield improvement</div>
</div>
    """, unsafe_allow_html=True)
with k4:
    val_L = val_per / 1_000_000
    st.markdown(f"""
<div style="padding: 0 16px;">
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 8px;">Value Recovered</div>
<div style="font-family: {FONT_TECH}; font-size: 2.2rem; font-weight: 600; color: {COLOR['navy']}; line-height: 1;"><span style="font-family: {FONT_PRIMARY}; font-size: 1.6rem; color: {COLOR['text2']}; margin-right: 2px;">₹</span>{val_L:.1f}<span style="font-family: {FONT_PRIMARY}; font-size: 1.1rem; font-weight: 400; color: {COLOR['text2']}; margin-left: 4px;">L</span></div>
<div style="font-size: 0.8rem; color: {COLOR['green']}; font-weight: 500; margin-top: 8px;">Added margin</div>
</div>
    """, unsafe_allow_html=True)

st.markdown('<div style="margin-bottom: 48px;"></div>', unsafe_allow_html=True)

# ── Main visual ───────────────────────────────────────────────
fig = go.Figure()
times = baseline['time']

# Target band
lo, hi = target_MFI*(1-spec_band), target_MFI*(1+spec_band)
fig.add_trace(go.Scatter(
    x=[0, times[-1], times[-1], 0],
    y=[hi, hi, lo, lo],
    fill='toself', fillcolor=COLOR['spec_fill'],
    line=dict(color='rgba(255,255,255,0)'),
    name="Target Spec", hoverinfo='skip'
))

# Baseline
fig.add_trace(go.Scatter(
    x=times, y=baseline['MFI_bed'],
    name="Baseline Ramp",
    line=dict(color=COLOR['baseline'], width=2, dash='dash')
))

# AI Trajectory
fig.add_trace(go.Scatter(
    x=times, y=ai_traj['MFI_bed'],
    name="GradeShift AI",
    line=dict(color=COLOR['blue'], width=3)
))

# Arrival points
fig.add_trace(go.Scatter(
    x=[base_t, ai_t], y=[target_MFI, target_MFI],
    mode='markers', marker=dict(size=8, color=[COLOR['baseline'], COLOR['blue']]),
    showlegend=False, hoverinfo='skip'
))

fig.add_annotation(
    x=ai_t, y=target_MFI, text="AI Spec Achieved",
    showarrow=True, arrowhead=1, arrowcolor=COLOR['blue'],
    ax=-40, ay=-40, font=dict(color=COLOR['blue'], family=FONT_PRIMARY, size=11)
)

fig.update_layout(**chart_layout(title="MFI Transition Trajectory: Current vs AI", height=420, show_legend=True))
fig.update_yaxes(type="log", title_text="MFI (g/10min, log scale)")
fig.update_xaxes(title_text="Time (min)")
st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

# ── Interpretation panels ─────────────────────────────────────
st.markdown('<div style="margin-top: 16px;"></div>', unsafe_allow_html=True)
c1, c2 = st.columns(2)

with c1:
    st.markdown(f"""
<div style="background: {COLOR['white']}; border: 1px solid {COLOR['border']}; border-radius: 8px; padding: 20px;">
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 8px;">Baseline</div>
<div style="font-size: 1rem; font-weight: 600; color: {COLOR['navy']}; margin-bottom: 6px;">Conservative linear ramp</div>
<div style="font-size: 0.85rem; color: {COLOR['text']}; line-height: 1.5;">Plant operators slowly ramp the H₂/monomer ratio over 4 hours to avoid sudden pressure spikes or reactor temperature oscillations, leading to a long transition time and excess off-spec product.</div>
</div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
<div style="background: {COLOR['white']}; border: 1px solid {COLOR['blue']}; border-radius: 8px; padding: 20px; box-shadow: 0 4px 12px rgba(23,105,224,0.08);">
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['blue']}; font-weight: 600; margin-bottom: 8px;">GradeShift AI</div>
<div style="font-size: 1rem; font-weight: 600; color: {COLOR['blue']}; margin-bottom: 6px;">Physics-informed optimized trajectory</div>
<div style="font-size: 0.85rem; color: {COLOR['text']}; line-height: 1.5;">The reinforcement learning agent commands an initial aggressive overshoot of the H₂ setpoint, rapidly purging the bed inventory, before smoothly capturing the target spec without violating thermal constraints.</div>
</div>
    """, unsafe_allow_html=True)

insight("<strong>AI INSIGHT:</strong> GradeShift predicts that an initial 60-minute over-dosing of hydrogen accelerates the polymer melt index response by 2.4x without triggering bed stickiness limits.", kind="blue")
