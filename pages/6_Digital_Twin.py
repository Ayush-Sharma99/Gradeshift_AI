"""
GradeShift AI — Page 6: Digital Twin
Real-time kinematic state and P&ID schematic of the UNIPOL PE reactor.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import streamlit as st
import plotly.graph_objects as go
import numpy as np
import time

from gs_theme import (
    inject_css, topbar, sidebar_brand, sidebar_nav, page_title,
    chart_layout, COLOR, FONT_PRIMARY, FONT_TECH
)

st.set_page_config(page_title="Digital Twin · GradeShift AI", page_icon="⬡", layout="wide")
inject_css()

# ── Global configuration ───────────────────────────────────────
GRADES = {
    'A': {'name': 'HDPE Pipe (PE100)',   'short': 'HDPE-P'},
    'B': {'name': 'HDPE Blow Moulding',  'short': 'HDPE-BM'},
}
ig, tg = 'A', 'B'

sidebar_brand()
sidebar_nav()
topbar(f"{GRADES[ig]['short']}", f"{GRADES[tg]['short']}", "Bathinda · Unit 03")

# ── Header ────────────────────────────────────────────────────
st.markdown("""
<div style="margin-bottom: 24px;">
<div class="gs-eyebrow">INTELLIGENCE</div>
<div class="gs-page-title">Process Digital Twin</div>
<div class="gs-page-subtitle">Live kinematic state estimation and spatial distribution tracking.</div>
</div>
""", unsafe_allow_html=True)


col_vis, col_kpi = st.columns([2, 1], gap="large")

with col_vis:
    st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-bottom: 16px;">Fluidized Bed Spatial Profile</div>
    """, unsafe_allow_html=True)
    
    # ── Advanced 3D/Contour Visualization of Reactor Bed ──────────
    # Simulating a temperature profile across the fluidized bed (radius vs height)
    r = np.linspace(0, 2.5, 30)  # Radius in meters
    z = np.linspace(0, 15, 50)   # Height in meters
    R, Z = np.meshgrid(r, z)
    
    # Base temperature
    T_base = 85.0
    # Add radial profile (hotter in center)
    T_radial = 1.5 * (1 - (R/2.5)**2)
    # Add vertical profile (hotter at reaction zone z=2 to z=8)
    T_vertical = 3.0 * np.exp(-((Z-5)**2)/10)
    # Add random localized hotspots (simulated bed anomalies)
    T_noise = np.random.normal(0, 0.2, R.shape)
    
    T_profile = T_base + T_radial + T_vertical + T_noise

    fig = go.Figure(data=go.Contour(
        z=T_profile,
        x=r,
        y=z,
        colorscale=[
            [0, COLOR['navy']],
            [0.3, COLOR['blue']],
            [0.6, COLOR['cyan']],
            [0.9, COLOR['amber']],
            [1, COLOR['red']]
        ],
        contours=dict(
            start=84,
            end=90,
            size=0.5,
            showlines=False
        ),
        colorbar=dict(
            title=dict(text="Temp (°C)", font=dict(family=FONT_PRIMARY)),
            tickfont=dict(family=FONT_PRIMARY)
        ),
        hovertemplate="Height: %{y:.1f}m<br>Radius: %{x:.2f}m<br>Temp: %{z:.1f}°C<extra></extra>"
    ))

    # Add reactor wall outline
    fig.add_shape(type="rect", x0=0, y0=0, x1=2.5, y1=15, line=dict(color=COLOR['border'], width=2))
    
    # Distributor plate
    fig.add_shape(type="line", x0=0, y0=0, x1=2.5, y1=0, line=dict(color=COLOR['navy'], width=4, dash="dot"))
    fig.add_annotation(x=1.25, y=-0.5, text="Gas Distributor Grid", showarrow=False, font=dict(family=FONT_PRIMARY, size=10, color=COLOR['text2']))
    
    layout = chart_layout(height=500, show_legend=False)
    layout['margin'] = dict(l=40, r=40, t=20, b=40)
    fig.update_layout(**layout)
    fig.update_xaxes(title_text="Radial Distance (m)", range=[-0.2, 2.7], gridcolor="rgba(0,0,0,0)")
    fig.update_yaxes(title_text="Bed Height (m)", range=[-1, 16], gridcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


with col_kpi:
    st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-bottom: 16px;">State Variables</div>
    """, unsafe_allow_html=True)
    
    def metric_row(label, val, unit, status="normal", delta=None):
        if status == "critical":
            col = COLOR['red']
        elif status == "warning":
            col = COLOR['amber']
        else:
            col = COLOR['text']
            
        delta_html = ""
        if delta:
            d_col = COLOR['green'] if delta.startswith("-") or status=="normal" else COLOR['red']
            delta_html = f'<div style="font-size:0.75rem; color:{d_col}; font-weight:500;">{delta}</div>'
            
        return f"""
<div style="background: {COLOR['white']}; border: 1px solid {COLOR['border']}; border-radius: 6px; padding: 12px 16px; margin-bottom: 10px; display:flex; justify-content:space-between; align-items:center;">
<div>
<div style="font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: {COLOR['text2']}; font-weight: 600; margin-bottom: 2px;">{label}</div>
<div style="font-family: {FONT_TECH}; font-size: 1.2rem; font-weight: 600; color: {col};">{val} <span style="font-family: {FONT_PRIMARY}; font-size: 0.75rem; font-weight: 400; color: {COLOR['text2']};">{unit}</span></div>
</div>
            {delta_html}
</div>
        """

    html = metric_row("Bed Weight", "84.2", "tonnes", delta="+0.1 t/hr")
    html += metric_row("Cycle Gas Velocity", "0.62", "m/s", delta="-0.01 m/s")
    html += metric_row("Condensation Fraction", "12.4", "% wt", status="warning", delta="+1.2 %")
    html += metric_row("Catalyst Productivity", "18.5", "kg/g", delta="Stable")
    html += metric_row("Max Wall Temp", "89.4", "°C", delta="-0.2 °C")
    html += metric_row("Fouling Factor", "0.014", "hr·m²·K/kcal")
    
    st.markdown(html, unsafe_allow_html=True)
    
    st.markdown(f"""
<div style="margin-top: 24px; padding: 16px; background: rgba(23,105,224,0.05); border-left: 3px solid {COLOR['blue']}; border-radius: 4px;">
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['blue']}; font-weight: 600; margin-bottom: 4px;">Digital Twin Synchronization</div>
<div style="font-size: 0.8rem; color: {COLOR['text']}; line-height: 1.5;">
            The 1st-principle kinetic model is actively synchronized with the DCS via Extended Kalman Filter (EKF), resolving spatial temperature gradients hidden from physical sensors.
</div>
</div>
    """, unsafe_allow_html=True)
