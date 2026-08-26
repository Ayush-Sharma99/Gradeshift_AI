"""
GradeShift AI — Page 4: Safety
Trustworthy display of constraints and Control Barrier Functions.
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

st.set_page_config(page_title="Safety · GradeShift AI", page_icon="⬡", layout="wide")
inject_css()

# ── Global configuration ───────────────────────────────────────
GRADES = {
    'A': {'name': 'HDPE Pipe (PE100)',   'short': 'HDPE-P',  'MFI': 0.3,  'density': 0.949, 'H2_M': 0.05, 'Temp': 84.5},
    'B': {'name': 'HDPE Blow Moulding',  'short': 'HDPE-BM', 'MFI': 8.0,  'density': 0.954, 'H2_M': 0.35, 'Temp': 86.0},
    'C': {'name': 'LLDPE Film Grade',    'short': 'LLDPE-F', 'MFI': 1.0,  'density': 0.918, 'H2_M': 0.10, 'Temp': 82.0},
}
ig, tg = 'A', 'B'

sidebar_brand()
sidebar_nav()
topbar(f"{GRADES[ig]['short']}", f"{GRADES[tg]['short']}", "Bathinda · Unit 03")

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom: 24px;">
<div class="gs-eyebrow">GOVERNANCE</div>
<div class="gs-page-title">Safety & Constraints</div>
<div class="gs-page-subtitle">Real-time monitoring of Control Barrier Functions (CBFs).</div>
</div>
""", unsafe_allow_html=True)

# ── Safety Status ─────────────────────────────────────────────
st.markdown(f"""
<div style="background: {COLOR['spec_fill']}; border: 1px solid {COLOR['green']}; border-radius: 8px; padding: 16px 24px; margin-bottom: 32px; display: flex; align-items: center; gap: 16px;">
<div style="font-size: 1.5rem;">✅</div>
<div>
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['green']}; font-weight: 600;">System Safety Status</div>
<div style="font-size: 1.2rem; font-weight: 600; color: {COLOR['navy']}; margin-top: 2px;">ALL CONSTRAINTS CLEAR</div>
</div>
</div>
""", unsafe_allow_html=True)


col1, col2 = st.columns([1, 1.2], gap="large")

with col1:
    st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-bottom: 16px;">Active Constraints</div>
    """, unsafe_allow_html=True)
    
    constraints = [
        {"name": "Bed Temperature", "val": 85.2, "limit": 90.0, "unit": "°C", "color": COLOR['blue']},
        {"name": "Reactor Pressure", "val": 24.1, "limit": 26.5, "unit": "bar", "color": COLOR['blue']},
        {"name": "Compressor Load", "val": 84, "limit": 100, "unit": "%", "color": COLOR['blue']},
        {"name": "Bed Stickiness Margin", "val": 8.2, "limit": 3.0, "unit": "°C", "color": COLOR['green'], "inverse": True},
        {"name": "Cooling Valve Open", "val": 65, "limit": 95, "unit": "%", "color": COLOR['blue']},
    ]
    
    html = ""
    for c in constraints:
        # Calculate fraction for bar
        frac = c['val'] / c['limit']
        if c.get("inverse"):
            frac = (15 - c['val']) / (15 - c['limit']) # dummy logic for visual
            frac = max(0, min(1, frac))
        
        # Color logic
        bar_color = COLOR['blue']
        status = "SAFE"
        status_color = COLOR['green']
        
        if frac > 0.9:
            bar_color = COLOR['red']
            status = "CRITICAL"
            status_color = COLOR['red']
        elif frac > 0.75:
            bar_color = COLOR['amber']
            status = "WARNING"
            status_color = COLOR['amber']
            
        if c.get("inverse") and c['val'] > c['limit'] + 2:
             bar_color = COLOR['green']
        
        html += f"""
<div class="gs-constraint-row">
<div class="gs-constraint-label">{c['name']}</div>
<div class="gs-constraint-bar-wrap">
<div class="gs-constraint-bar-fill" style="width: {frac*100}%; background: {bar_color};"></div>
</div>
<div class="gs-constraint-value">{c['val']:.1f} <span style="font-family:{FONT_PRIMARY}; font-size:0.7rem; color:{COLOR['text2']}; font-weight:400;">{c['unit']}</span></div>
<div class="gs-constraint-limit">Limit: {c['limit']:.1f}</div>
<div class="gs-constraint-status" style="color: {status_color};">{status}</div>
</div>
        """
    
    st.markdown(f"""
<div style="background: {COLOR['white']}; border: 1px solid {COLOR['border']}; border-radius: 8px; padding: 24px;">
        {html}
</div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-top: 32px; margin-bottom: 16px;">Control Barrier Functions (CBF)</div>
<div style="font-size: 0.85rem; color: #5B687A; line-height: 1.6;">
        GradeShift AI employs a formal safety layer. While the Reinforcement Learning agent proposes actions to minimise transition time, the CBF evaluates these actions against the physical constraint boundary (e.g., bed stickiness temperature). If an action is unsafe, the CBF mathematically projects it to the closest safe action before sending it to the DCS.
</div>
    """, unsafe_allow_html=True)


with col2:
    st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-bottom: 16px;">Operating Envelope</div>
    """, unsafe_allow_html=True)
    
    fig = go.Figure()

    # Define envelope
    x_env = [0.0, 0.4, 0.6, 0.4, 0.0, 0.0]
    y_env = [80, 80, 86, 92, 92, 80]
    
    # Safe region polygon
    fig.add_trace(go.Scatter(
        x=x_env, y=y_env,
        fill='toself', fillcolor='rgba(24, 191, 195, 0.05)',
        line=dict(color=COLOR['border'], width=1, dash='dash'),
        name="Safe Envelope", hoverinfo='skip'
    ))

    # Add Target Region
    fig.add_trace(go.Scatter(
        x=[0.33, 0.37, 0.37, 0.33, 0.33],
        y=[85, 85, 87, 87, 85],
        fill='toself', fillcolor='rgba(32, 168, 115, 0.1)',
        line=dict(color=COLOR['green'], width=1),
        name="Target Region"
    ))

    # Add Current State
    fig.add_trace(go.Scatter(
        x=[0.05], y=[84.5],
        mode='markers',
        marker=dict(size=12, color=COLOR['navy'], line=dict(color='white', width=2)),
        name="Current Point"
    ))
    
    # Add Trajectory
    x_traj = [0.05, 0.15, 0.25, 0.35, 0.35]
    y_traj = [84.5, 84.8, 85.2, 86.5, 86.0]
    fig.add_trace(go.Scatter(
        x=x_traj, y=y_traj,
        mode='lines+markers',
        line=dict(color=COLOR['blue'], width=2),
        marker=dict(size=6, color=COLOR['blue']),
        name="AI Trajectory"
    ))
    
    # Constraint Boundary Annotation
    fig.add_annotation(
        x=0.5, y=89, text="Constraint Boundary (Stickiness)",
        showarrow=True, arrowhead=1, ax=40, ay=-20,
        font=dict(family=FONT_PRIMARY, size=11, color=COLOR['red'])
    )

    layout = chart_layout(height=420, show_legend=True)
    layout['xaxis'] = dict(title=dict(text="H₂/C₂ Ratio", font=dict(family=FONT_PRIMARY)), gridcolor="#EDF0F4")
    layout['yaxis'] = dict(title=dict(text="Bed Temperature (°C)", font=dict(family=FONT_PRIMARY)), gridcolor="#EDF0F4")
    layout['legend'].update(x=0.02, y=0.98, bgcolor='rgba(255,255,255,0.8)')
    
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
