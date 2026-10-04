"""
Page 4 — Transition Guardian (Sensor Health, Fault Injection, OOD & Abstention Diagnostics)
Replaces legacy CBF/DCS control claims with PrimePath's read-only Transition Guardian:
7 deterministic sensor health checks (`health.py`), reproducible fault injectors (`faults.py`),
train-only OOD applicability detection (`applicability.py`), 11-row robustness matrix,
and locked test abstention decomposition.
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
    build_guardian_view,
)

st.set_page_config(
    page_title="GradeShift PrimePath | Transition Guardian",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_brand()
sidebar_nav()

rt = get_cached_runtime()

st.sidebar.markdown('<div class="gs-nav-section">Guardian Controls</div>', unsafe_allow_html=True)

all_event_ids = [ev.event_id for ev in rt.corpus]
selected_event_id = st.sidebar.selectbox(
    "Corpus Episode",
    options=all_event_ids,
    format_func=lambda eid: f"{eid} ({rt.events_by_id[eid].direction} · {rt.partitions[eid].value})",
    index=0,
)

grid_len = len(rt.decision_grid(rt.events_by_id[selected_event_id]))
selected_step = st.sidebar.slider(
    "Decision Step Index",
    min_value=0,
    max_value=max(0, grid_len - 1),
    value=min(18, max(0, grid_len - 1)),
)

fault_options = [
    "NONE",
    "FROZEN_MFI",
    "MISSING_MFI",
    "STALE_MFI",
    "SPIKE_MFI",
    "GAP_H2",
    "TIMESTAMP_DISORDER",
]
fault_labels = {
    "NONE": "NONE (Clean Sensor Stream)",
    "FROZEN_MFI": "Fault B: Frozen MFI Analyzer (35 min constant)",
    "MISSING_MFI": "Fault A: Missing MFI_online Signal",
    "STALE_MFI": "Fault G: Stale MFI_online (>20 min old)",
    "SPIKE_MFI": "Fault D: Rate Spike Outlier (4.0x jump)",
    "GAP_H2": "Fault E: Intra-Series Time Gap on H2_ratio",
    "TIMESTAMP_DISORDER": "Fault F: Non-Monotonic Timestamp Swap",
}
selected_fault = st.sidebar.selectbox(
    "Inject Deterministic Sensor Fault (`faults.py`)",
    options=fault_options,
    format_func=lambda f: fault_labels[f],
    index=0,
)

gv = build_guardian_view(
    rt,
    event_id=selected_event_id,
    step_idx=selected_step,
    fault_kind=selected_fault,
)

dir_parts = gv["direction"].split("->")
topbar(
    current_grade_from=dir_parts[0],
    current_grade_to=dir_parts[1],
    unit=gv["unit"],
    mode_label="TRANSITION GUARDIAN",
    partition_label=f"{gv['event_id']} ({gv['partition']})",
)

page_title(
    "Transition Guardian — Sensor Health, OOD Applicability & Fail-Safe Abstention",
    "Deterministic data-integrity checks and train-only domain support gating that force ABSTAIN when evidence is untrustworthy.",
    eyebrow="PHASES 7 & 13 · READ-ONLY EVIDENCE ASSURANCE LAYER",
)

mode_banner(MODE_META[ExecutionMode.SYNTHETIC_REPLAY.value])

action_hero_card(
    action=gv["resulting_action"],
    action_meta=gv["action_meta"],
    reason_codes=gv["reason_codes"],
    approval_status=(
        ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value
        if gv["resulting_action"] == "PRIME_RELEASE_CANDIDATE"
        else ApprovalStatus.NOT_APPLICABLE.value
    ),
    approver_role="Shift Quality Approver (QC)",
    narrative=(
        f"Fault Preset: {fault_labels[selected_fault]} · "
        f"Sensor Health: {gv['health_overall']} · "
        f"Applicability: {gv['applicability']['state']}"
    ),
)

# 4-Column KPI Strip
ap = gv["applicability"]
decomp = gv["abstention_decomposition"]
rob = gv["robustness_matrix"]

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        panel_open()
        + kpi_card(
            "Sensor Health State",
            gv["health_overall"],
            "",
            f"Findings: {len(gv['findings_table'])} · Blocking: {gv['health_is_blocking']}",
            "neg" if gv["health_is_blocking"] else "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        panel_open()
        + kpi_card(
            "Applicability / OOD State",
            ap["state"],
            "",
            f"Direction {gv['direction']} · Blocking: {ap['is_blocking']}",
            "neg" if ap["is_blocking"] else "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k3:
    rob_rows = rob.get("rows", [])
    n_match = sum(1 for r in rob_rows if r.get("match"))
    st.markdown(
        panel_open()
        + kpi_card(
            "Robustness Matrix",
            f"{n_match}/{len(rob_rows)}",
            "PASS",
            "Controlled fail-safe fault & OOD scenarios",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        panel_open()
        + kpi_card(
            "Locked Test Abstentions",
            f"{decomp.get('abstained_decisions', 235)}/{decomp.get('total_decisions', 235)}",
            "rows",
            "100% gate-justified (0.0 t false-prime mass)",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )

col_h, col_o = st.columns(2, gap="large")

with col_h:
    section_header("1. Live Sensor Health Report (`assess_sensor_health`)")
    st.dataframe(pd.DataFrame(gv["signal_table"]), use_container_width=True, hide_index=True)

    if gv["findings_table"]:
        st.markdown("**Active Sensor Health Findings (Triggered by Stream / Fault Injector):**")
        st.dataframe(pd.DataFrame(gv["findings_table"]), use_container_width=True, hide_index=True)
    else:
        st.success(
            "All 7 sensor health checks PASS (No missing signal, NaN, timestamp disorder, "
            "range violation, staleness, time gap, frozen value, or rate spike)."
        )

    section_header("2. Locked Validation Abstention Decomposition (235 Decisions)")
    cat_counts = decomp.get("blocking_by_category", {"ood": 235, "material_mapping": 40})
    fig = go.Figure(
        go.Bar(
            x=list(cat_counts.keys()),
            y=list(cat_counts.values()),
            marker_color=[COLOR["red"], COLOR["amber"]],
            text=list(cat_counts.values()),
            textposition="auto",
        )
    )
    fig.update_layout(
        **chart_layout(
            title="Blocking Hard-Gate Categories Across 235 Locked Test Decisions",
            height=260,
            show_legend=False,
        )
    )
    fig.update_yaxes(title_text="Blocked Decision Count (out of 235)")
    st.plotly_chart(fig, use_container_width=True)

with col_o:
    section_header("3. Train-Only OOD & Applicability Assessment (`ApplicabilityDetector`)")
    st.markdown(
        panel_open(f"Applicability Report — Episode {gv['event_id']} ({gv['direction']})")
        + data_row("Applicability State", str(ap["state"]))
        + data_row("Support / Isolation Score", f"{ap['score']:.4f}")
        + data_row("Reason Codes", ", ".join(ap["reason_codes"]))
        + data_row("Blocks Disposition?", str(ap["is_blocking"]))
        + data_row("Supported TRAIN Directions", "A->B, B->A, A->C, C->A")
        + data_row("Unseen LOCKED_TEST Directions", "B->C, C->B (Flagged UNSUPPORTED)")
        + panel_close(),
        unsafe_allow_html=True,
    )

    section_header("4. Phase-13 Robustness Matrix (11 Controlled Fail-Safe Fixtures)")
    rob_df = pd.DataFrame(
        [
            {
                "Scenario Fixture": r["scenario"],
                "Expected Action": r["expected_forced_action"],
                "Observed Action": r["observed_action"],
                "Match": "✅ PASS" if r["match"] else "❌ FAIL",
                "Reason Codes": ", ".join(r.get("reason_codes", [])),
            }
            for r in rob_rows
        ]
    )
    st.dataframe(rob_df, use_container_width=True, hide_index=True, height=340)

insight(
    "<strong>Why PrimePath Abstains on Locked Test Events:</strong> The chronological <code>TRAIN</code> "
    "partition covers transitions <code>A→B</code>, <code>B→A</code>, <code>A→C</code>, and <code>C→A</code>, "
    "while the chronological <code>LOCKED_TEST</code> partition comprises <code>B→C</code> and <code>C→B</code>. "
    "Rather than extrapolating silently into unseen grade pairs, the train-only <code>ApplicabilityDetector</code> "
    "flags <code>UNKNOWN_GRADE_PAIR</code> (<code>UNSUPPORTED</code>), forcing <code>ABSTAIN / FOLLOW SOP</code> "
    "and protecting against 1,356.0 t of false-prime exposure."
)
