"""
Page 3 — Disposition Workbench (Hard Gates First, Expected Loss & VOI Downstream)
Interactive workbench over `gradeshift.disposition.evaluate_disposition` and
`gradeshift.economics.evaluate_economics`. Demonstrates how 13 hard policy gates,
5 candidacy gates, sample eligibility, and permitted-action expected loss
determine HOLD, SAMPLE_NOW, PRIME_RELEASE_CANDIDATE, or ABSTAIN.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gs_theme import (
    COLOR,
    action_hero_card,
    chart_layout,
    data_row,
    get_cached_runtime,
    inject_css,
    insight,
    kpi_card,
    mode_banner,
    page_title,
    panel_close,
    panel_open,
    section_header,
    sidebar_brand,
    sidebar_nav,
    topbar,
)
from gradeshift.ui import (
    ApprovalStatus,
    ExecutionMode,
    MODE_META,
    build_disposition_view,
)

st.set_page_config(
    page_title="GradeShift PrimePath | Disposition Workbench",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_brand()
sidebar_nav()

rt = get_cached_runtime()

st.sidebar.markdown('<div class="gs-nav-section">Workbench Presets</div>', unsafe_allow_html=True)

preset = st.sidebar.selectbox(
    "Scenario Preset",
    options=[
        "PRIME_CANDIDATE (Interval In-Spec + 13 Gates Pass)",
        "HOLD (Interval Crosses Spec, Sample Unavailable)",
        "SAMPLE_NOW (Interval Crosses Spec + Sample Available)",
        "ABSTAIN (Sensor Health ABNORMAL)",
        "ABSTAIN (Out-of-Domain / Unsupported Direction)",
        "ABSTAIN (Ambiguous Material Route)",
        "FOLLOW_SOP (Expired Recommendation > 30m)",
        "CUSTOM (Manual Sliders Below)",
    ],
    index=0,
)

selected_scenario = st.sidebar.selectbox(
    "Economic Scenario",
    options=["BASE", "LOW", "HIGH"],
    index=0,
)

# Default values driven by preset
grade_to = "B"
lower_mfi, upper_mfi = 7.70, 8.30
dwell_elapsed = 45.0
sample_avail = True
mapping_qual = "WELL_SUPPORTED"
res_unc = 10.0
health_st = "NORMAL"
appl_st = "NORMAL"
mass_t = 50.0
rec_age = 5.0

if preset.startswith("HOLD"):
    lower_mfi, upper_mfi = 7.50, 8.30
    sample_avail = False
elif preset.startswith("SAMPLE_NOW"):
    lower_mfi, upper_mfi = 7.50, 8.30
    sample_avail = True
elif "Sensor Health" in preset:
    health_st = "ABNORMAL"
elif "Out-of-Domain" in preset:
    appl_st = "UNSUPPORTED"
elif "Ambiguous" in preset:
    mapping_qual = "AMBIGUOUS"
elif "Expired" in preset:
    rec_age = 45.0

st.sidebar.markdown('<div class="gs-nav-section">Evidence Knobs</div>', unsafe_allow_html=True)
lower_mfi = st.sidebar.slider("90% Interval Lower Bound (g/10m)", 7.00, 8.35, float(lower_mfi), 0.05)
upper_mfi = st.sidebar.slider("90% Interval Upper Bound (g/10m)", max(lower_mfi + 0.05, 7.10), 8.80, float(max(upper_mfi, lower_mfi + 0.05)), 0.05)
dwell_elapsed = st.sidebar.slider("Continuous Dwell Elapsed (min)", 0.0, 90.0, float(dwell_elapsed), 5.0)
sample_avail = st.sidebar.checkbox("Confirmatory Lab Sample Available", value=bool(sample_avail))
mapping_qual = st.sidebar.selectbox(
    "Material Mapping Quality",
    options=["WELL_SUPPORTED", "PARTIALLY_SUPPORTED", "AMBIGUOUS", "UNAVAILABLE"],
    index=["WELL_SUPPORTED", "PARTIALLY_SUPPORTED", "AMBIGUOUS", "UNAVAILABLE"].index(mapping_qual),
)
health_st = st.sidebar.selectbox(
    "Sensor Health State",
    options=["NORMAL", "DEGRADED", "ABNORMAL", "UNAVAILABLE"],
    index=["NORMAL", "DEGRADED", "ABNORMAL", "UNAVAILABLE"].index(health_st),
)
appl_st = st.sidebar.selectbox(
    "Applicability / OOD State",
    options=["NORMAL", "OOD", "UNSUPPORTED", "UNAVAILABLE"],
    index=["NORMAL", "OOD", "UNSUPPORTED", "UNAVAILABLE"].index(appl_st),
)
rec_age = st.sidebar.slider("Recommendation Age (min vs 30m expiry)", 0.0, 60.0, float(rec_age), 5.0)

dv = build_disposition_view(
    rt,
    scenario_name=selected_scenario,
    grade_to=grade_to,
    lower_mfi=lower_mfi,
    upper_mfi=upper_mfi,
    dwell_elapsed_min=dwell_elapsed,
    sample_available=sample_avail,
    mapping_quality=mapping_qual,
    residence_uncertainty_min=res_unc,
    health_state=health_st,
    applicability_state=appl_st,
    mass_tonnes=mass_t,
    recommendation_age_min=rec_age,
)

topbar(
    current_grade_from="A",
    current_grade_to=grade_to,
    unit="SIM-UNIT-1 (WORKBENCH)",
    mode_label="DISPOSITION WORKBENCH",
    partition_label="INTERACTIVE POLICY AUDIT",
)

page_title(
    "Disposition Workbench — Hard Gates, Expected Loss & Discrete VOI",
    "Pure deterministic decision engine: 13 hard policy gates evaluated FIRST; economics ranks permitted actions only.",
    eyebrow="PHASES 9 & 10 · COMMERCIAL DISPOSITION ENGINE",
)

mode_banner(MODE_META[ExecutionMode.ILLUSTRATIVE_DEMO.value])

action_hero_card(
    action=dv["action"],
    action_meta=dv["action_meta"],
    reason_codes=dv["reason_codes"],
    approval_status=(
        ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value
        if dv["action"] == "PRIME_RELEASE_CANDIDATE"
        else ApprovalStatus.NOT_APPLICABLE.value
    ),
    approver_role=dv["approver_role"],
    narrative=dv["note"],
)

# 4-Column Summary KPIs
pred = dv["prediction"]
spec = dv["spec"]
ledger = dv["economics_ledger"]
hard_pass = sum(1 for g in dv["hard_gates"] if g["passed"])
cand_pass = sum(1 for g in dv["candidacy_gates"] if g["passed"])

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        panel_open()
        + kpi_card(
            "Hard Policy Gates",
            f"{hard_pass}/{len(dv['hard_gates'])}",
            "PASS",
            "Any failure forces ABSTAIN / FOLLOW SOP",
            "pos" if hard_pass == len(dv["hard_gates"]) else "neg",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        panel_open()
        + kpi_card(
            "Prime Candidacy Gates",
            f"{cand_pass}/{len(dv['candidacy_gates'])}",
            "PASS",
            "Steers non-hard failures to HOLD / SAMPLE NOW",
            "pos" if cand_pass == len(dv["candidacy_gates"]) else "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        panel_open()
        + kpi_card(
            "Permitted Actions",
            str(len(dv["permitted_actions"])),
            "actions",
            ", ".join(dv["permitted_actions"]),
            "pos" if "PRIME_RELEASE_CANDIDATE" in dv["permitted_actions"] else "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k4:
    voi_val = float(ledger.get("voi", {}).get("voi_currency", 0.0))
    st.markdown(
        panel_open()
        + kpi_card(
            "Discrete Sample VOI",
            f"₹{voi_val:,.0f}",
            "",
            f"Economic Preferred: {dv['economic_preferred_action']}",
            "pos" if voi_val > 0 else "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )

col_g, col_e = st.columns([1.25, 1.0], gap="large")

with col_g:
    section_header("1. Thirteen Hard Policy Gates (Severity.BLOCK — Evaluated First)")
    hg_df = pd.DataFrame(
        [
            {
                "Gate ID": g["gate_id"],
                "Passed": "✅ PASS" if g["passed"] else "🛑 BLOCK",
                "Reason Code": g["reason_code"],
                "Detail": g.get("detail", ""),
            }
            for g in dv["hard_gates"]
        ]
    )
    st.dataframe(hg_df, use_container_width=True, hide_index=True)

    section_header("2. Five Prime Candidacy Gates (Severity.CANDIDACY)")
    cg_df = pd.DataFrame(
        [
            {
                "Gate ID": g["gate_id"],
                "Passed": "✅ PASS" if g["passed"] else "⚠️ STEER",
                "Reason Code": g["reason_code"],
                "Detail": g.get("detail", ""),
            }
            for g in dv["candidacy_gates"]
        ]
    )
    st.dataframe(cg_df, use_container_width=True, hide_index=True)

with col_e:
    section_header("3. Interval vs. Target Grade Specification")
    fig = go.Figure()
    fig.add_vrect(
        x0=spec["mfi_low"],
        x1=spec["mfi_high"],
        fillcolor=COLOR["spec_fill"],
        line_width=1.5,
        line_color=COLOR["green"],
        annotation_text=f"Grade {spec['grade_id']} Spec [{spec['mfi_low']:.2f}, {spec['mfi_high']:.2f}]",
    )
    fig.add_trace(
        go.Scatter(
            x=[pred["lower_mfi"], pred["point_mfi"], pred["upper_mfi"]],
            y=["90% Calibrated Interval", "90% Calibrated Interval", "90% Calibrated Interval"],
            mode="lines+markers",
            line=dict(color=dv["action_meta"]["color"], width=6),
            marker=dict(size=[12, 16, 12], color=dv["action_meta"]["color"]),
            name=f"[{pred['lower_mfi']:.2f}, {pred['upper_mfi']:.2f}]",
        )
    )
    fig.update_layout(
        **chart_layout(
            title="Calibrated 90% Interval Position Relative to Commercial Specification",
            height=220,
            show_legend=False,
        )
    )
    fig.update_xaxes(title_text="Melt Flow Index (g/10min)", range=[6.9, 8.9])
    st.plotly_chart(fig, use_container_width=True)

    section_header("4. Expected Loss Over Permitted Actions Only")
    el_rows = ledger.get("expected_loss_table", {}).get("rows", [])
    el_table = []
    for r in el_rows:
        el_table.append(
            {
                "Permitted Action": r["action"],
                "Expected Loss (₹)": f"₹{float(r['expected_loss_currency']):,.0f}",
                "False-Prime Exp (₹)": f"₹{float(r['false_prime_exposure_currency']):,.0f}",
                "False-Hold Exp (₹)": f"₹{float(r['false_hold_exposure_currency']):,.0f}",
                "Risk Proxy p(bad)": round(float(r.get("risk", {}).get("p_bad_PROXY", 0.0)), 3),
            }
        )
    st.dataframe(pd.DataFrame(el_table), use_container_width=True, hide_index=True)

    se = dv["sample_eligibility"]
    st.markdown(
        panel_open("5. Confirmatory Sample Operational Eligibility & VOI")
        + data_row("Sample Operationally Eligible?", str(se.get("eligible")))
        + data_row("Sample Result Latency", f"{se.get('expected_result_latency_min')} min")
        + data_row("Decision Horizon", f"{se.get('decision_horizon_min')} min")
        + data_row("Interval Width / Spec Width", f"{float(se.get('current_decision_uncertainty', 0.0)):.2f}x")
        + data_row("Discrete VOI (₹)", f"₹{voi_val:,.0f}")
        + panel_close(),
        unsafe_allow_html=True,
    )

insight(
    "<strong>Non-Negotiable Invariant:</strong> Economics <em>never</em> decide permission. "
    "If any hard gate fails, the only permitted action in the Phase-10 Expected Loss table is "
    "<code>ABSTAIN</code> — no economic calculation can resurrect a blocked action."
)
