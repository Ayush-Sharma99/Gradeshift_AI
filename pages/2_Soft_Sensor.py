"""
GradeShift AI — Page 2: Soft Sensor
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import streamlit as st
import numpy as np
import plotly.graph_objects as go

from gs_theme import (
    inject_css, topbar, sidebar_brand, sidebar_nav, page_title,
    chart_layout, COLOR, FONT_PRIMARY, FONT_TECH
)
from soft_sensor import SoftSensorManager
from transition_optimizer import TransitionOptimizer

st.set_page_config(page_title="Soft Sensor · GradeShift AI", page_icon="⬡", layout="wide")
inject_css()

# ── Global configuration ───────────────────────────────────────
GRADES = {
    'A': {'name': 'HDPE Pipe (PE100)',   'short': 'HDPE-P',  'MFI': 0.3,  'density': 0.949},
    'B': {'name': 'HDPE Blow Moulding',  'short': 'HDPE-BM', 'MFI': 8.0,  'density': 0.954},
    'C': {'name': 'LLDPE Film Grade',    'short': 'LLDPE-F', 'MFI': 1.0,  'density': 0.918},
}
ig, tg = 'A', 'B'

sidebar_brand()
sidebar_nav()
topbar(f"{GRADES[ig]['short']}", f"{GRADES[tg]['short']}", "Bathinda · Unit 03")

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom: 32px;">
<div class="gs-eyebrow">INTELLIGENCE</div>
<div class="gs-page-title">Continuous Soft Sensor</div>
<div class="gs-page-subtitle">Closing the lab-delay gap with physics-informed deep learning.</div>
</div>
""", unsafe_allow_html=True)

# ── Storytelling block ────────────────────────────────────────
col_a, col_b = st.columns(2)
with col_a:
    st.markdown(f"""
<div style="padding: 24px; border-right: 1px solid {COLOR['border']};">
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 8px;">The Problem</div>
<div style="font-size: 1.1rem; font-weight: 600; color: {COLOR['navy']}; margin-bottom: 24px;">The plant produces continuously.<br>The lab measures periodically.</div>
<div style="display: flex; align-items: baseline; gap: 12px;">
<div style="font-family: {FONT_TECH}; font-size: 2.5rem; font-weight: 600; color: {COLOR['navy']};">75<span style="font-family: {FONT_PRIMARY}; font-size: 1.1rem; color: {COLOR['text2']}; font-weight: 400; margin-left: 4px;">min</span></div>
<div style="font-size: 0.85rem; color: {COLOR['text2']}; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">Lab Delay</div>
</div>
</div>
    """, unsafe_allow_html=True)

with col_b:
    st.markdown(f"""
<div style="padding: 24px;">
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['blue']}; font-weight: 600; margin-bottom: 8px;">The Solution</div>
<div style="font-size: 1.1rem; font-weight: 600; color: {COLOR['blue']}; margin-bottom: 24px;">Deep sequence modeling (LSTM) predicts<br>quality continuously from DCS data.</div>
<div style="display: flex; align-items: baseline; gap: 12px;">
<div style="font-family: {FONT_TECH}; font-size: 2.5rem; font-weight: 600; color: {COLOR['blue']};">10<span style="font-family: {FONT_PRIMARY}; font-size: 1.1rem; color: {COLOR['text2']}; font-weight: 400; margin-left: 4px;">sec</span></div>
<div style="font-size: 0.85rem; color: {COLOR['blue']}; text-transform: uppercase; letter-spacing: 0.05em; font-weight: 600;">AI Estimate</div>
</div>
</div>
    """, unsafe_allow_html=True)

st.markdown('<hr/>', unsafe_allow_html=True)

# ── Data Generation ───────────────────────────────────────────
@st.cache_data(show_spinner=False)
def get_sensor_data(ig, tg):
    opt = TransitionOptimizer(ig, tg, 50000)
    base = opt.simulate_linear_ramp(240, 600)
    
    t = np.array(base['time'])
    true_mfi = np.array(base['MFI_bed'])
    
    # 75 min lab delay = sample every 75 min
    lab_idx = np.arange(0, len(t), 75)
    lab_t = t[lab_idx]
    # Add noise to lab samples
    lab_mfi = true_mfi[lab_idx] * np.random.normal(1.0, 0.05, len(lab_idx))
    
    # AI prediction (simulated)
    ai_mfi = true_mfi * np.random.normal(1.0, 0.02, len(t))
    # Add some dynamic lag correction error initially
    ai_mfi[:100] = ai_mfi[:100] * np.linspace(1.1, 1.0, 100)
    
    # Confidence bounds (expand during rapid transition)
    rate_of_change = np.abs(np.gradient(true_mfi))
    conf_spread = 0.03 * true_mfi + 0.5 * rate_of_change
    ai_upper = ai_mfi + conf_spread
    ai_lower = ai_mfi - conf_spread
    
    return t, true_mfi, lab_t, lab_mfi, ai_mfi, ai_upper, ai_lower

t, true_mfi, lab_t, lab_mfi, ai_mfi, ai_upper, ai_lower = get_sensor_data(ig, tg)

# ── Chart ─────────────────────────────────────────────────────
fig = go.Figure()

# Confidence Band
fig.add_trace(go.Scatter(
    x=np.concatenate([t, t[::-1]]),
    y=np.concatenate([ai_upper, ai_lower[::-1]]),
    fill='toself', fillcolor='rgba(24, 191, 195, 0.15)',
    line=dict(color='rgba(255,255,255,0)'),
    name="95% Confidence Band", hoverinfo='skip'
))

# Continuous AI Prediction
fig.add_trace(go.Scatter(
    x=t, y=ai_mfi,
    name="GradeShift AI Prediction",
    line=dict(color=COLOR['ai_signal'], width=2.5)
))

# Discrete Lab Samples
fig.add_trace(go.Scatter(
    x=lab_t, y=lab_mfi,
    mode='markers', name='Lab Measurements (75m delay)',
    marker=dict(color=COLOR['navy'], size=9, symbol='diamond', line=dict(color='white', width=1))
))

layout = chart_layout(height=480, show_legend=True)
layout['yaxis'] = dict(title=dict(text="MFI (log scale)", font=dict(family=FONT_PRIMARY)), type="log", gridcolor="#EDF0F4")
layout['xaxis'] = dict(title=dict(text="Time (minutes)", font=dict(family=FONT_PRIMARY)), gridcolor="#EDF0F4")
layout['legend'].update(x=0.02, y=0.95, bgcolor='rgba(255,255,255,0.8)')

# Annotate a blind spot
blind_start, blind_end = lab_t[2], lab_t[3]
fig.add_vrect(
    x0=blind_start, x1=blind_end,
    fillcolor=COLOR['amber_fill'], opacity=0.5, layer="below", line_width=0,
)
fig.add_annotation(
    x=(blind_start+blind_end)/2, y=np.log10(ai_mfi[int((blind_start+blind_end)/2)]),
    text="Lab Blind Spot (75m)", showarrow=False,
    font=dict(color=COLOR['amber'], family=FONT_PRIMARY, size=11),
    yshift=40
)

fig.update_layout(**layout)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
