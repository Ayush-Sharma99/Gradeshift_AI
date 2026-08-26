"""
GradeShift AI — Page 3: AI Optimizer
Engineering workstation view of the recommended control action.
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

st.set_page_config(page_title="AI Optimizer · GradeShift AI", page_icon="⬡", layout="wide")
inject_css()

# ── Global configuration ───────────────────────────────────────
GRADES = {
    'A': {'name': 'HDPE Pipe (PE100)',   'short': 'HDPE-P',  'MFI': 0.3,  'density': 0.949, 'H2_M': 0.05, 'Temp': 84.5},
    'B': {'name': 'HDPE Blow Moulding',  'short': 'HDPE-BM', 'MFI': 8.0,  'density': 0.954, 'H2_M': 0.35, 'Temp': 86.0},
    'C': {'name': 'LLDPE Film Grade',    'short': 'LLDPE-F', 'MFI': 1.0,  'density': 0.918, 'H2_M': 0.10, 'Temp': 82.0},
}
ig, tg = 'A', 'B'
prod_rate = 50.0

sidebar_brand()
sidebar_nav()
topbar(f"{GRADES[ig]['short']}", f"{GRADES[tg]['short']}", "Bathinda · Unit 03")

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom: 24px;">
<div class="gs-eyebrow">OPERATIONS</div>
<div class="gs-page-title">AI Optimizer</div>
<div class="gs-page-subtitle">Engineering decision-support for the optimal transition path.</div>
</div>
""", unsafe_allow_html=True)

# ── State panels ──────────────────────────────────────────────
col_curr, col_arr, col_tgt = st.columns([1, 0.1, 1])

def state_block(title, grade_id, is_target=False):
    g = GRADES[grade_id]
    color = COLOR['blue'] if is_target else COLOR['navy']
    border = f"1px solid {COLOR['blue']}" if is_target else f"1px solid {COLOR['border']}"
    bg = "rgba(23,105,224,0.02)" if is_target else COLOR['white']
    
    html = f"""
<div style="background: {bg}; border: {border}; border-radius: 8px; padding: 24px; height: 100%;">
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: {color}; font-weight: 600; margin-bottom: 16px;">{title}</div>
        
<div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid {COLOR['border']}; padding-bottom: 8px; margin-bottom: 8px;">
<span style="font-size: 0.85rem; color: {COLOR['text2']};">Product</span>
<span style="font-size: 0.95rem; font-weight: 600; color: {COLOR['text']};">{g['name']}</span>
</div>
        
<div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid {COLOR['border']}; padding-bottom: 8px; margin-bottom: 8px;">
<span style="font-size: 0.85rem; color: {COLOR['text2']};">MFI</span>
<span style="font-family: {FONT_TECH}; font-weight: 600; color: {color};">{g['MFI']:.2f} <span style="font-family: {FONT_PRIMARY}; font-size: 0.8rem; font-weight: 400; color: {COLOR['text2']};">g/10min</span></span>
</div>
        
<div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid {COLOR['border']}; padding-bottom: 8px; margin-bottom: 8px;">
<span style="font-size: 0.85rem; color: {COLOR['text2']};">Density</span>
<span style="font-family: {FONT_TECH}; font-weight: 500; color: {COLOR['text']};">{g['density']:.3f} <span style="font-family: {FONT_PRIMARY}; font-size: 0.8rem; font-weight: 400; color: {COLOR['text2']};">g/cm³</span></span>
</div>
        
<div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid {COLOR['border']}; padding-bottom: 8px; margin-bottom: 8px;">
<span style="font-size: 0.85rem; color: {COLOR['text2']};">H₂/C₂ Setpoint</span>
<span style="font-family: {FONT_TECH}; font-weight: 500; color: {COLOR['text']};">{g['H2_M']:.3f} <span style="font-family: {FONT_PRIMARY}; font-size: 0.8rem; font-weight: 400; color: {COLOR['text2']};">mol/mol</span></span>
</div>
        
<div style="display: flex; justify-content: space-between; align-items: baseline;">
<span style="font-size: 0.85rem; color: {COLOR['text2']};">Bed Temp</span>
<span style="font-family: {FONT_TECH}; font-weight: 500; color: {COLOR['text']};">{g['Temp']:.1f} <span style="font-family: {FONT_PRIMARY}; font-size: 0.8rem; font-weight: 400; color: {COLOR['text2']};">°C</span></span>
</div>
</div>
    """
    return html

with col_curr:
    st.markdown(state_block("Current State", ig), unsafe_allow_html=True)

with col_arr:
    st.markdown("""
<div style="height: 100%; display: flex; align-items: center; justify-content: center; color: #DCE3EA; font-size: 2rem;">
        →
</div>
    """, unsafe_allow_html=True)

with col_tgt:
    st.markdown(state_block("Target State", tg, is_target=True), unsafe_allow_html=True)

st.markdown('<hr/>', unsafe_allow_html=True)

# ── Optimization Chart ─────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_ai_data(ig, tg, pr):
    opt = TransitionOptimizer(ig, tg, pr * 1000)
    ai   = opt.optimize_bang_bang()
    return ai, opt.target_MFI, opt.spec_band

ai_traj, target_MFI, spec_band = get_ai_data(ig, tg, prod_rate)
times = [t/60 for t in ai_traj['time']]

st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-bottom: 16px;">Recommended Trajectory</div>
""", unsafe_allow_html=True)

fig = make_subplots(
    rows=2, cols=1, shared_xaxes=True,
    row_heights=[0.6, 0.4], vertical_spacing=0.08,
)

lo, hi = target_MFI*(1-spec_band), target_MFI*(1+spec_band)
fig.add_hrect(y0=lo, y1=hi, fillcolor=COLOR['spec_fill'], line_width=0, row=1, col=1)

# MFI Trajectory
fig.add_trace(go.Scatter(
    x=times, y=ai_traj['MFI_bed'], name='MFI Prediction',
    line=dict(color=COLOR['blue'], width=3)
), row=1, col=1)

fig.add_hline(y=target_MFI, line_dash="dash", line_color=COLOR['green'], line_width=1, row=1, col=1)

# H2/M Control Action
fig.add_trace(go.Scatter(
    x=times, y=ai_traj['H2_M'], name='Recommended H₂/M',
    line=dict(color=COLOR['blue'], width=2, shape='hv'),
    fill='tozeroy', fillcolor='rgba(23,105,224,0.1)'
), row=2, col=1)

# Highlight overshoot
overshoot_end = 1.0  # approximate hour where bang-bang ends
fig.add_vrect(
    x0=0, x1=overshoot_end,
    fillcolor=COLOR['amber_fill'], opacity=0.3, layer="below", line_width=0,
    row=2, col=1
)
fig.add_annotation(
    x=overshoot_end/2, y=np.max(ai_traj['H2_M']) * 0.9,
    text="Overshoot Phase", showarrow=False,
    font=dict(color=COLOR['amber'], family=FONT_PRIMARY, size=11),
    row=2, col=1
)

layout = chart_layout(height=450, show_legend=False)
fig.update_layout(**layout)
fig.update_yaxes(title_text="MFI (log scale)", type="log", gridcolor="#EDF0F4", row=1, col=1)
fig.update_yaxes(title_text="H₂/C₂ Setpoint", gridcolor="#EDF0F4", row=2, col=1)
fig.update_xaxes(title_text="Time (hours)", gridcolor="#EDF0F4", row=2, col=1)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ── Explanation ────────────────────────────────────────────────
st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-top: 16px; margin-bottom: 16px;">Why this trajectory?</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"""
<div style="border-left: 2px solid {COLOR['blue']}; padding-left: 16px;">
<div style="font-size: 0.9rem; font-weight: 600; color: {COLOR['navy']}; margin-bottom: 6px;">Accelerates off-spec purge</div>
<div style="font-size: 0.85rem; color: {COLOR['text2']}; line-height: 1.5;">The initial heavy hydrogen dosing rapidly shifts the instantaneous polymer melt index, washing out the existing bed inventory much faster than a slow ramp.</div>
</div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
<div style="border-left: 2px solid {COLOR['blue']}; padding-left: 16px;">
<div style="font-size: 0.9rem; font-weight: 600; color: {COLOR['navy']}; margin-bottom: 6px;">Maintains safety envelope</div>
<div style="font-size: 0.85rem; color: {COLOR['text2']}; line-height: 1.5;">The amplitude of the overshoot is capped by the NMPC Control Barrier Function to ensure the resulting exothermic reaction does not exceed compressor cooling limits.</div>
</div>
    """, unsafe_allow_html=True)
with col3:
    st.markdown(f"""
<div style="border-left: 2px solid {COLOR['blue']}; padding-left: 16px;">
<div style="font-size: 0.9rem; font-weight: 600; color: {COLOR['navy']}; margin-bottom: 6px;">Captures target cleanly</div>
<div style="font-size: 0.85rem; color: {COLOR['text2']}; line-height: 1.5;">The timing of the setpoint pullback is calculated perfectly by the RL agent to allow the bed momentum to glide exactly into the target spec band without oscillation.</div>
</div>
    """, unsafe_allow_html=True)
