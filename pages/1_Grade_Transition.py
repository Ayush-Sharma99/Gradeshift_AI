"""
Page 1 — Transition Replay & Counterfactual Policy Comparison
Replays transition episodes under the structural as-of causal firewall across
SOP_FIXTURE, POINT_THRESHOLD, PRIMEPATH, and ORACLE_DIAGNOSTIC_ONLY.
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
    build_replay_view,
)

st.set_page_config(
    page_title="GradeShift PrimePath | Transition Replay",
    page_icon="⏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_brand()
sidebar_nav()

rt = get_cached_runtime()

st.sidebar.markdown('<div class="gs-nav-section">Replay Controls</div>', unsafe_allow_html=True)

all_event_ids = [ev.event_id for ev in rt.corpus]
selected_event_id = st.sidebar.selectbox(
    "Select Corpus Episode",
    options=all_event_ids,
    format_func=lambda eid: f"{eid} ({rt.events_by_id[eid].direction} · {rt.partitions[eid].value})",
    index=0,
)

selected_scenario = st.sidebar.selectbox(
    "Economic Scenario",
    options=["BASE", "LOW", "HIGH"],
    index=0,
)

grid_len = len(rt.decision_grid(rt.events_by_id[selected_event_id]))
selected_step = st.sidebar.slider(
    "Inspect Step Index (10-min intervals)",
    min_value=0,
    max_value=max(0, grid_len - 1),
    value=min(18, max(0, grid_len - 1)),
)

reveal_truth = st.sidebar.checkbox(
    "Reveal Post-Decision Lab Truth (Diagnostic)",
    value=False,
)

rv = build_replay_view(
    rt,
    event_id=selected_event_id,
    scenario_name=selected_scenario,
    step_idx=selected_step,
    reveal_future_truth=reveal_truth,
)

dir_parts = rv["direction"].split("->")
topbar(
    current_grade_from=dir_parts[0],
    current_grade_to=dir_parts[1],
    unit=rv["unit"],
    mode_label="SYNTHETIC REPLAY",
    partition_label=f"{rv['event_id']} ({rv['partition']})",
)

page_title(
    "Transition Replay & Counterfactual Policy Comparison",
    "Causal as-of timeline replay comparing SOP Fixed-Dwell, Point Threshold, PrimePath, and Diagnostic Oracle.",
    eyebrow="PHASE 12 · STRUCTURAL FUTURE-TRUTH FIREWALL",
)

mode_banner(MODE_META[ExecutionMode.SYNTHETIC_REPLAY.value])

# 4-Column KPI Summary for Selected Episode
comp_by_pol = {r["policy"]: r for r in rv["comparison_table"]}
pp_row = comp_by_pol.get("PRIMEPATH", {})
sop_row = comp_by_pol.get("SOP_FIXTURE", {})
pt_row = comp_by_pol.get("POINT_THRESHOLD", {})

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        panel_open()
        + kpi_card(
            "PrimePath False-Prime Mass",
            f"{float(pp_row.get('false_prime_mass_tonnes', 0.0)):.1f}",
            "t",
            f"SOP: {float(sop_row.get('false_prime_mass_tonnes', 0.0)):.1f}t · Point: {float(pt_row.get('false_prime_mass_tonnes', 0.0)):.1f}t",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        panel_open()
        + kpi_card(
            "PrimePath Samples Requested",
            str(pp_row.get("n_samples", 0)),
            "samples",
            f"Decision steps: {rv['n_steps']}",
            "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k3:
    abst_rate = 100.0 * float(pp_row.get("abstention_rate") or 0.0)
    st.markdown(
        panel_open()
        + kpi_card(
            "PrimePath Abstention Rate",
            f"{abst_rate:.1f}",
            "%",
            f"Partition: {rv['partition']} ({rv['direction']})",
            "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k4:
    regret = float(pp_row.get("expected_regret_vs_oracle_currency") or 0.0)
    st.markdown(
        panel_open()
        + kpi_card(
            f"Regret vs Oracle ({selected_scenario})",
            f"₹{regret / 1e5:.2f}",
            "Lakh",
            "Diagnostic bound only (SIMULATED)",
            "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )

# Timeline Chart with Conformal Band & Step Cursor
section_header(f"Episode {rv['event_id']} Replay Trajectory & Conformal Interval Band")
tl_df = pd.DataFrame(rv["timeline"])
spec = rv["spec"]

fig = go.Figure()
fig.add_hrect(
    y0=spec["mfi_low"],
    y1=spec["mfi_high"],
    fillcolor=COLOR["spec_fill"],
    line_width=1,
    line_dash="dot",
    line_color=COLOR["green"],
    annotation_text=f"Target Grade {spec['grade_id']} Spec [{spec['mfi_low']:.2f}, {spec['mfi_high']:.2f}]",
)

if not tl_df.empty:
    fig.add_trace(
        go.Scatter(
            x=tl_df["elapsed_min"],
            y=tl_df["upper_mfi"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=tl_df["elapsed_min"],
            y=tl_df["lower_mfi"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(23,105,224,0.16)",
            name="90% Split-Conformal Interval",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=tl_df["elapsed_min"],
            y=tl_df["point_mfi"],
            mode="lines+markers",
            name="HistGBM Point Estimate (As-Of t)",
            line=dict(color=COLOR["blue"], width=2.5),
            marker=dict(size=5),
        )
    )
    if reveal_truth and "revealed_mfi" in tl_df.columns and tl_df["revealed_mfi"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=tl_df["elapsed_min"],
                y=tl_df["revealed_mfi"],
                mode="lines+markers",
                name="Revealed Future Lab Truth (Post-Firewall)",
                line=dict(color=COLOR["green"], width=2, dash="dash"),
                marker=dict(size=6, symbol="diamond"),
            )
        )

    cur_row = tl_df.iloc[rv["step_idx"]]
    fig.add_vline(
        x=float(cur_row["elapsed_min"]),
        line_width=2,
        line_dash="dash",
        line_color=COLOR["amber"],
        annotation_text=f"Step {rv['step_idx']} ({cur_row['PRIMEPATH']})",
    )

fig.update_layout(
    **chart_layout(
        title=f"Episode {rv['event_id']} ({rv['direction']}) · Causal As-Of Predictions vs Target Spec",
        height=400,
    )
)
fig.update_xaxes(title_text="Elapsed Time Since Transition Start (minutes)")
fig.update_yaxes(title_text="Melt Flow Index (MFI, g/10min)")
st.plotly_chart(fig, use_container_width=True)

# Policy Comparison Table & Step Evidence Trace
c_left, c_right = st.columns([1.25, 1.0], gap="large")

with c_left:
    section_header(f"Episode {rv['event_id']} Four-Policy Counterfactual Comparison")
    comp_rows = []
    for r in rv["comparison_table"]:
        comp_rows.append(
            {
                "Policy": r["policy"],
                "Candidate Time (min)": r["candidate_time_min"],
                "Samples": r["n_samples"],
                "False-Prime Mass (t)": round(float(r["false_prime_mass_tonnes"]), 2),
                "False-Hold Mass (t)": round(float(r["false_hold_mass_tonnes"]), 2),
                "Abstention Rate": f"{100.0 * float(r['abstention_rate'] or 0.0):.1f}%",
                "Avoidable Loss (₹)": f"₹{float(r['gross_avoidable_loss_currency']):,.0f}",
                "Regret vs Oracle (₹)": f"₹{float(r['expected_regret_vs_oracle_currency'] or 0.0):,.0f}",
            }
        )
    st.dataframe(pd.DataFrame(comp_rows), use_container_width=True, hide_index=True)
    st.caption(f"Note: {rv['oracle_label']} — Raw component metrics only; no composite 'winner score'.")

    section_header("Step-by-Step Policy Action Matrix")
    st.dataframe(
        tl_df[
            [
                "step",
                "elapsed_min",
                "point_mfi",
                "lower_mfi",
                "upper_mfi",
                "SOP_FIXTURE",
                "POINT_THRESHOLD",
                "PRIMEPATH",
                "ORACLE_DIAGNOSTIC_ONLY",
            ]
        ],
        use_container_width=True,
        hide_index=True,
        height=280,
    )

with c_right:
    section_header(f"Step {rv['step_idx']} Full Causal Evidence Trace")
    tr = rv["step_trace"]
    ctx_d = tr.get("as_of_context", {})
    dec_d = tr.get("decision", {})
    out_d = tr.get("outcome", {})
    truth_d = tr.get("later_truth", {})

    st.markdown(
        panel_open(f"Evidence Chain @ Step {rv['step_idx']} ({ctx_d.get('decision_time', '')})")
        + data_row("Elapsed Minutes", f"{ctx_d.get('elapsed_min', 0.0):.1f} min")
        + data_row("Point Estimate", f"{ctx_d.get('point_estimate', 0.0):.4f} g/10min")
        + data_row("Calibrated 90% Interval", str(ctx_d.get("interval")))
        + data_row("Target Spec Band", str(ctx_d.get("spec_band")))
        + data_row("Sensor Health", str(ctx_d.get("health_state")))
        + data_row("Applicability / OOD State", str(ctx_d.get("applicability_state")))
        + data_row("PrimePath Recommended Action", str(dec_d.get("action")))
        + data_row("Reason Codes", ", ".join(dec_d.get("reason_codes", [])))
        + data_row("Permitted Actions", ", ".join(dec_d.get("permitted_actions", [])))
        + data_row(
            "Later Revealed Truth (Firewall)",
            f"MFI={truth_d.get('revealed_mfi'):.3f} (in_spec={truth_d.get('was_in_spec')})"
            if reveal_truth and truth_d.get("revealed_mfi") is not None
            else "HIDDEN (Enable checkbox in sidebar to inspect post-decision truth)",
        )
        + data_row("Affected Window Mass", f"{out_d.get('affected_mass_tonnes', 0.0):.2f} t")
        + panel_close(),
        unsafe_allow_html=True,
    )

    section_header("Laboratory Grab-Sample Blind Windows (Collection → Result)")
    st.dataframe(pd.DataFrame(rv["lab_windows"]), use_container_width=True, hide_index=True)

insight(
    "<strong>Structural Causal Firewall (`as_of_event`):</strong> At every decision timestamp <em>t</em>, "
    "future sensor observations, unresulted laboratory grab samples (<code>result_at &gt; t</code>), and "
    "future silo routing intervals are physically stripped from the event before feature engineering "
    "and policy evaluation."
)
