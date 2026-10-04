"""
Page 5 — Economic Ledger (Expected Loss, Discrete VOI & Scenario Scale-Up)
Replaces legacy static financial claims with PrimePath's Phase-10 Economic Ledger:
explicit LOW / BASE / HIGH scenario parameters (`config.py`), formula-auditable
cost components, realized vs counterfactual value separation, locked replay
consequence comparison, and parameterized annual scenario scale-up (`scale_up_annual`).
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gs_theme import (
    COLOR,
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
    ExecutionMode,
    MODE_META,
    build_economic_view,
)

st.set_page_config(
    page_title="GradeShift PrimePath | Economic Ledger",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_brand()
sidebar_nav()

rt = get_cached_runtime()

st.sidebar.markdown('<div class="gs-nav-section">Scenario Parameters</div>', unsafe_allow_html=True)

selected_scenario = st.sidebar.selectbox(
    "Economic Scenario (`ECON_SCENARIOS`)",
    options=["BASE", "LOW", "HIGH"],
    index=0,
)
mass_tonnes = st.sidebar.slider(
    "Mapped Material Window Mass (tonnes)",
    min_value=10.0,
    max_value=100.0,
    value=50.0,
    step=5.0,
)
rec_mass = st.sidebar.slider(
    "Recoverable Prime-Eligible Mass (tonnes)",
    min_value=5.0,
    max_value=float(mass_tonnes),
    value=float(mass_tonnes),
    step=5.0,
)

st.sidebar.markdown('<div class="gs-nav-section">Annual Scale-Up Calculator</div>', unsafe_allow_html=True)
n_transitions_yr = st.sidebar.slider(
    "Eligible Transitions / Year (ASSUMPTION)",
    min_value=10,
    max_value=120,
    value=50,
    step=5,
)
avail_frac = st.sidebar.slider(
    "System Availability Factor",
    min_value=0.50,
    max_value=1.00,
    value=0.90,
    step=0.05,
)
adopt_frac = st.sidebar.slider(
    "Operator / QC Adoption Factor",
    min_value=0.10,
    max_value=1.00,
    value=0.50,
    step=0.05,
)

ev_view = build_economic_view(
    rt,
    scenario_name=selected_scenario,
    mass_tonnes=mass_tonnes,
    recoverable_mass_tonnes=rec_mass,
    eligible_transitions_per_year=float(n_transitions_yr),
    availability=float(avail_frac),
    adoption=float(adopt_frac),
)

sc = ev_view["scenario"]
ledger = ev_view["active_ledger"]
annual = ev_view["annual_scale_up"]
sanity = ev_view["sanity_checks"]

topbar(
    current_grade_from="A",
    current_grade_to="B",
    unit="SIM-UNIT-1 (ECONOMIC LEDGER)",
    mode_label=f"{selected_scenario} SCENARIO (ASSUMPTION)",
    partition_label="PHASE 10 · ECONOMIC LEDGER",
)

page_title(
    "Economic Ledger — Expected Loss, Discrete VOI & Scenario Accounting",
    "Auditable episode-level mass/value accounting with strict separation between realized routing value and counterfactual opportunity.",
    eyebrow="PHASE 10 · SIMULATED / ASSUMPTION ECONOMIC ENGINE",
)

mode_banner(MODE_META[ExecutionMode.ILLUSTRATIVE_DEMO.value])

# 4-Column KPI Strip
vs = ledger.get("value_split", {})
cf_opp = float(vs.get("counterfactual_opportunity_currency", 0.0))
real_val = float(vs.get("realized_value_currency", 0.0))
ann_val = float(annual.get("annual_value_currency", 0.0))

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        panel_open()
        + kpi_card(
            f"Prime-vs-Downgrade Spread ({sc.name})",
            f"₹{sc.downgrade_spread:,.0f}",
            "/ tonne",
            f"Prime: ₹{sc.prime_price:,.0f}/t · Downgrade: ₹{sc.downgrade_price:,.0f}/t",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        panel_open()
        + kpi_card(
            "Episode Opportunity Value",
            f"₹{cf_opp / 1e5:.2f}",
            "Lakh",
            f"On {rec_mass:.1f}t recoverable good material (SIMULATED)",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        panel_open()
        + kpi_card(
            "False-Prime Consequence",
            f"₹{sc.false_prime_consequence:,.0f}",
            "/ tonne",
            f"Sample: ₹{sc.sample_cost:,.0f} · Workflow: ₹{sc.workflow_cost:,.0f}",
            "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        panel_open()
        + kpi_card(
            "Scenario Annual Scale-Up",
            f"₹{ann_val / 1e7:.2f}",
            "Cr / yr",
            f"{n_transitions_yr} tx/yr × {int(avail_frac*100)}% avail × {int(adopt_frac*100)}% adopt",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )

c1, c2 = st.columns([1.2, 1.0], gap="large")

with c1:
    section_header("1. LOW / BASE / HIGH Scenario Comparison (`config.ECON_SCENARIOS`)")
    sc_df = pd.DataFrame(ev_view["scenario_comparison"])
    st.dataframe(
        sc_df.rename(
            columns={
                "scenario": "Scenario",
                "prime_price_per_t": "Prime (₹/t)",
                "downgrade_price_per_t": "Downgrade (₹/t)",
                "spread_per_t": "Spread (₹/t)",
                "false_prime_consequence_per_t": "False-Prime Penalty (₹/t)",
                "sample_cost": "Sample Cost (₹)",
                "workflow_cost": "Workflow Cost (₹)",
                "counterfactual_opportunity_currency": "Episode Opportunity (₹)",
            }
        )[
            [
                "Scenario",
                "Prime (₹/t)",
                "Downgrade (₹/t)",
                "Spread (₹/t)",
                "False-Prime Penalty (₹/t)",
                "Sample Cost (₹)",
                "Episode Opportunity (₹)",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    section_header("2. Locked Validation Replay Economics Across 4 Policies (235 Decisions)")
    lb = ev_view["locked_level_b"]
    lc = ev_view["locked_level_c"]
    lock_econ_rows = []
    for pol in ["SOP_FIXTURE", "POINT_THRESHOLD", "PRIMEPATH", "ORACLE_DIAGNOSTIC_ONLY"]:
        if pol in lc:
            lock_econ_rows.append(
                {
                    "Policy": pol,
                    "False-Prime Mass (t)": lb.get(pol, {}).get("false_prime_mass_tonnes", 0.0),
                    "False-Hold Mass (t)": lb.get(pol, {}).get("false_hold_mass_tonnes", 0.0),
                    "False-Prime Exposure (₹)": f"₹{float(lc[pol].get('false_prime_exposure_currency', 0.0)):,.0f}",
                    "False-Hold Opportunity (₹)": f"₹{float(lc[pol].get('false_hold_opportunity_currency', 0.0)):,.0f}",
                    "Avoidable Loss (₹)": f"₹{float(lc[pol].get('gross_avoidable_loss_currency', 0.0)):,.0f}",
                }
            )
    st.dataframe(pd.DataFrame(lock_econ_rows), use_container_width=True, hide_index=True)

    # Bar chart of False-Prime Exposure vs False-Hold Opportunity on Locked Test
    fig = go.Figure()
    pols = ["SOP_FIXTURE", "POINT_THRESHOLD", "PRIMEPATH"]
    fp_vals = [float(lc.get(p, {}).get("false_prime_exposure_currency", 0.0)) / 1e7 for p in pols]
    fh_vals = [float(lc.get(p, {}).get("false_hold_opportunity_currency", 0.0)) / 1e7 for p in pols]
    fig.add_trace(
        go.Bar(name="False-Prime Exposure (₹ Cr)", x=pols, y=fp_vals, marker_color=COLOR["red"])
    )
    fig.add_trace(
        go.Bar(name="False-Hold Opportunity Cost (₹ Cr)", x=pols, y=fh_vals, marker_color=COLOR["amber"])
    )
    fig.update_layout(
        barmode="group",
        **chart_layout(
            title="Locked Validation Consequence Trade-Off (₹ Crore across 5 Unseen Test Episodes)",
            height=300,
        ),
    )
    fig.update_yaxes(title_text="₹ Crore (SIMULATED / BASE)")
    st.plotly_chart(fig, use_container_width=True)

with c2:
    section_header("3. Realized vs. Counterfactual Value Split & Sanity Proofs")
    st.markdown(
        panel_open("Episode Value Split (`ValueSplit` — Never Double-Counted)")
        + data_row("Realized Route Value (Downgrade Silo)", f"₹{real_val:,.0f}")
        + data_row(
            "Counterfactual Prime Route Value",
            f"₹{float(vs.get('counterfactual_prime_value_currency', 0.0)):,.0f}",
        )
        + data_row("Counterfactual Prime-vs-Downgrade Spread", f"₹{cf_opp:,.0f}")
        + data_row("No Double Counting Check", "✅ PASS" if sanity.get("no_double_counting") else "❌ FAIL")
        + data_row("Mass Non-Negative Check", "✅ PASS" if sanity.get("mass_non_negative") else "❌ FAIL")
        + data_row(
            "Realized Separate From Counterfactual",
            "✅ PASS" if sanity.get("realized_separate_from_counterfactual") else "❌ FAIL",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )

    section_header("4. Parameterized Annual Scale-Up Formula (`scale_up_annual`)")
    st.markdown(
        panel_open("Explicit Scenario Scale-Up (ASSUMPTION — Not Measured Plant Savings)")
        + data_row("Formula", str(annual.get("formula", "")))
        + data_row("Episode Opportunity Value", f"₹{float(annual.get('validated_episode_value_currency', 0.0)):,.0f}")
        + data_row("Eligible Transitions / Year", str(annual.get("eligible_transitions_per_year")))
        + data_row("Availability × Adoption", f"{avail_frac:.2f} × {adopt_frac:.2f} = {avail_frac * adopt_frac:.2f}")
        + data_row("Annual Scenario Value", f"₹{ann_val:,.0f} (₹{ann_val / 1e7:.2f} Cr/yr)")
        + data_row("Provenance Tag", str(annual.get("provenance", "ASSUMPTION")))
        + panel_close(),
        unsafe_allow_html=True,
    )

    section_header("5. Expected-Loss Formula Components (`CostComponent`)")
    el_rows = ledger.get("expected_loss_table", {}).get("rows", [])
    comp_items = []
    for r in el_rows:
        for c_item in r.get("components", []):
            comp_items.append(
                {
                    "Action": r["action"],
                    "Component": c_item["name"],
                    "Amount (₹)": f"₹{float(c_item['amount_currency']):,.0f}",
                    "Formula": c_item["formula"],
                }
            )
    st.dataframe(pd.DataFrame(comp_items), use_container_width=True, hide_index=True, height=240)

section_header("6. How This Number Is Constructed (Formula-by-Formula Audit)")
ef = ev_view["economic_framing"]
badge_html = " · ".join(f"<code>{b}</code>" for b in ef["badges"])
st.markdown(
    f"<div style='margin-bottom:8px; font-size:0.84rem;'><strong>Mandatory Economic Labels:</strong> {badge_html}</div>",
    unsafe_allow_html=True,
)
how_rows = [
    {
        "Line Item": h["metric"],
        "Category": h["category"],
        "Formula": h["formula"],
        "Inputs": h["inputs"],
        "Amount (₹)": f"₹{float(h['value_currency']):,.0f}",
        "Evidence Class": h["evidence_class"],
        "Construction Rationale": h["explanation"],
    }
    for h in ev_view["how_constructed"]
]
st.dataframe(pd.DataFrame(how_rows), use_container_width=True, hide_index=True)

insight(
    f"<strong>Economic Honesty Rule (Not an HMEL Savings Claim):</strong> {ef['realized_vs_counterfactual_note']}"
)

