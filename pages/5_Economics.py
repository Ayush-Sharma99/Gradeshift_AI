"""
GradeShift AI — Page 5: Economics
Business case and waterfall ROI breakdown.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import streamlit as st
import plotly.graph_objects as go

from gs_theme import (
    inject_css, topbar, sidebar_brand, sidebar_nav, page_title,
    chart_layout, COLOR, FONT_PRIMARY, FONT_TECH
)

st.set_page_config(page_title="Economics · GradeShift AI", page_icon="⬡", layout="wide")
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
<div class="gs-eyebrow">GOVERNANCE</div>
<div class="gs-page-title">Economic Impact</div>
<div class="gs-page-subtitle">Estimated annual value and implementation business case for HMEL Bathinda.</div>
</div>
""", unsafe_allow_html=True)

# ── Top Value ─────────────────────────────────────────────────
st.markdown(f"""
<div style="display: flex; align-items: baseline; gap: 16px; margin-bottom: 32px;">
<div style="font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.1em; color: {COLOR['text2']}; font-weight: 600;">Estimated Annual Value</div>
<div style="font-family: {FONT_TECH}; font-size: 3rem; font-weight: 600; color: {COLOR['navy']};"><span style="font-family: {FONT_PRIMARY}; font-size: 2rem; color: {COLOR['text2']}; margin-right: 4px;">₹</span>60–102<span style="font-family: {FONT_PRIMARY}; font-size: 1.5rem; color: {COLOR['text2']}; font-weight: 400; margin-left: 8px;">Cr</span></div>
</div>
""", unsafe_allow_html=True)

col1, col2 = st.columns([1.5, 1], gap="large")

with col1:
    st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-bottom: 16px;">Value Creation Waterfall</div>
    """, unsafe_allow_html=True)
    
    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["relative", "relative", "relative", "total"],
        x=["Off-spec<br>Reduction", "Monomer Flare<br>Reduction", "Reprocessing<br>Energy Savings", "Total Annual<br>Benefit"],
        y=[42.5, 28.3, 10.2, 81.0],
        text=["₹42.5 Cr", "₹28.3 Cr", "₹10.2 Cr", "₹81.0 Cr"],
        textposition="outside",
        connector={"line": {"color": COLOR['border']}},
        decreasing={"marker": {"color": COLOR['red']}},
        increasing={"marker": {"color": COLOR['blue']}},
        totals={"marker": {"color": COLOR['navy']}},
        textfont=dict(family=FONT_TECH, size=12)
    ))
    
    layout = chart_layout(height=450, show_legend=False)
    layout['yaxis'] = dict(title=dict(text="Value (₹ Crores)", font=dict(family=FONT_PRIMARY)), gridcolor="#EDF0F4")
    layout['xaxis'] = dict(tickfont=dict(family=FONT_PRIMARY, size=12))
    
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with col2:
    st.markdown("""
<div style="font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.1em; color: #062B52; font-weight: 600; margin-bottom: 16px;">Implementation Metrics</div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
<div style="background: {COLOR['white']}; border: 1px solid {COLOR['border']}; border-radius: 8px; padding: 24px; margin-bottom: 24px;">
<div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid {COLOR['border']}; padding-bottom: 12px; margin-bottom: 12px;">
<span style="font-size: 0.85rem; color: {COLOR['text2']}; font-weight: 600;">Software & Licensing</span>
<span style="font-family: {FONT_TECH}; font-weight: 600; color: {COLOR['text']};">₹ 2.5 Cr <span style="font-family: {FONT_PRIMARY}; font-size: 0.75rem; font-weight: 400; color: {COLOR['text2']};">/ yr</span></span>
</div>
        
<div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid {COLOR['border']}; padding-bottom: 12px; margin-bottom: 12px;">
<span style="font-size: 0.85rem; color: {COLOR['text2']}; font-weight: 600;">Infrastructure & Maintenance</span>
<span style="font-family: {FONT_TECH}; font-weight: 600; color: {COLOR['text']};">₹ 0.8 Cr <span style="font-family: {FONT_PRIMARY}; font-size: 0.75rem; font-weight: 400; color: {COLOR['text2']};">/ yr</span></span>
</div>
        
<div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid {COLOR['border']}; padding-bottom: 12px; margin-bottom: 12px;">
<span style="font-size: 0.85rem; color: {COLOR['text2']}; font-weight: 600;">Net Annual Benefit (Avg)</span>
<span style="font-family: {FONT_TECH}; font-weight: 600; color: {COLOR['green']};">₹ 77.7 Cr</span>
</div>
        
<div style="display: flex; justify-content: space-between; align-items: baseline; padding-top: 4px;">
<span style="font-size: 0.85rem; color: {COLOR['navy']}; font-weight: 600;">Estimated Payback Period</span>
<span style="font-family: {FONT_TECH}; font-size: 1.2rem; font-weight: 600; color: {COLOR['navy']};">2.1 <span style="font-family: {FONT_PRIMARY}; font-size: 0.8rem; font-weight: 400; color: {COLOR['text2']};">months</span></span>
</div>
</div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
<div style="background: rgba(32,168,115,0.05); border-left: 3px solid {COLOR['green']}; padding: 16px 20px; font-size: 0.85rem; color: {COLOR['text']}; line-height: 1.5; border-radius: 0 4px 4px 0;">
<strong style="color: {COLOR['navy']}; font-weight: 600;">Zero CAPEX Implementation</strong><br>
        GradeShift AI deploys as an edge-compute layer over the existing DCS. It requires no new physical sensors, no reactor modifications, and no downtime to install.
</div>
    """, unsafe_allow_html=True)
