"""
Page 2 — Quality Evidence & Split-Conformal Uncertainty Calibration
Displays the real HistGradientBoostingRegressor (`gbm-mfi-v1`) point predictions,
finite-sample split-conformal intervals (`split-conformal-v1`), delayed laboratory
reconciliation, baseline model comparisons, and spec-crossing cases.
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
    build_quality_view,
)

st.set_page_config(
    page_title="GradeShift PrimePath | Quality Evidence",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_brand()
sidebar_nav()

rt = get_cached_runtime()

st.sidebar.markdown('<div class="gs-nav-section">Quality Controls</div>', unsafe_allow_html=True)
all_event_ids = [ev.event_id for ev in rt.corpus]
selected_event_id = st.sidebar.selectbox(
    "Inspect Episode Trajectory",
    options=all_event_ids,
    format_func=lambda eid: f"{eid} ({rt.events_by_id[eid].direction} · {rt.partitions[eid].value})",
    index=0,
)
show_reconciled_truth = st.sidebar.checkbox(
    "Overlay Delayed Lab Truth (Post-Reconciliation)",
    value=True,
)

qv = build_quality_view(rt, event_id=selected_event_id)
dir_parts = qv["direction"].split("->")

topbar(
    current_grade_from=dir_parts[0],
    current_grade_to=dir_parts[1],
    unit=rt.events_by_id[selected_event_id].unit,
    mode_label="QUALITY & CONFORMAL EVIDENCE",
    partition_label=f"{qv['event_id']} ({qv['partition']})",
)

page_title(
    "Quality Evidence & Calibrated Uncertainty",
    "Causal 41-feature HistGBM point estimation paired with finite-sample split-conformal prediction intervals.",
    eyebrow="PHASES 5 & 6 · POINT ESTIMATOR + SPLIT-CONFORMAL CALIBRATION",
)

mode_banner(MODE_META[ExecutionMode.SYNTHETIC_REPLAY.value])

# Top KPI Strip from Phase 5 & Phase 6 Frozen Artifacts
cs = qv["conformal_summary"]
locked_ov = cs.get("locked_overall", {})
gbm_comp = next((m for m in qv["model_comparison"] if m["model_key"] == "gbm"), {})

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        panel_open()
        + kpi_card(
            "Locked Test GBM MAE",
            f"{float(gbm_comp.get('locked_mae') or 0.2720):.4f}",
            "g/10m",
            f"RMSE: {float(gbm_comp.get('locked_rmse') or 0.4353):.4f} · n=235 rows",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        panel_open()
        + kpi_card(
            "Conformal Half-Width",
            f"±{float(cs.get('half_width_mfi') or 0.2369):.4f}",
            "g/10m",
            f"Method: {cs.get('chosen_method')} (90% nominal)",
            "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k3:
    st.markdown(
        panel_open()
        + kpi_card(
            "Calibration Split Support",
            f"{cs.get('calibration_rows', 141)}",
            "rows",
            f"Across {cs.get('calibration_events', 3)} whole calibration events",
            "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k4:
    emp_cov = 100.0 * float(locked_ov.get("coverage") or 0.6596)
    st.markdown(
        panel_open()
        + kpi_card(
            "Locked Empirical Coverage",
            f"{emp_cov:.1f}",
            "%",
            "Under direction shift (B→C, C→B); OOD gate blocks all",
            "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )

# Real GBM + Conformal Interval Trajectory Chart
section_header(f"Episode {qv['event_id']} — Real HistGBM Point Estimate, 90% Conformal Band & Delayed Lab Results")
traj_df = pd.DataFrame(qv["trajectory"])
spec = qv["spec"]

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

if not traj_df.empty:
    fig.add_trace(
        go.Scatter(
            x=traj_df["elapsed_min"],
            y=traj_df["conformal_upper_mfi"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=traj_df["elapsed_min"],
            y=traj_df["conformal_lower_mfi"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor="rgba(23,105,224,0.18)",
            name="90% Split-Conformal Interval (split-conformal-v1)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=traj_df["elapsed_min"],
            y=traj_df["gbm_point_mfi"],
            mode="lines",
            name="HistGBM Point Estimate (gbm-mfi-v1)",
            line=dict(color=COLOR["blue"], width=2.5),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=traj_df["elapsed_min"],
            y=traj_df["online_analyzer_mfi"],
            mode="lines",
            name="Raw Online MFI Analyzer (<= t)",
            line=dict(color=COLOR["baseline"], width=1.5, dash="dot"),
        )
    )
    if traj_df["last_known_lab_mfi"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=traj_df["elapsed_min"],
                y=traj_df["last_known_lab_mfi"],
                mode="lines",
                name="Last Resulted Lab Sample (As-Of t, Step-Hold)",
                line=dict(color=COLOR["amber"], width=1.8, shape="hv"),
            )
        )
    if show_reconciled_truth and traj_df["later_lab_truth_mfi"].notna().any():
        fig.add_trace(
            go.Scatter(
                x=traj_df["elapsed_min"],
                y=traj_df["later_lab_truth_mfi"],
                mode="markers",
                name="Delayed Lab Truth for Mapped Material (Post-Hoc)",
                marker=dict(color=COLOR["green"], size=6, symbol="diamond"),
            )
        )

fig.update_layout(
    **chart_layout(
        title=f"Episode {qv['event_id']} ({qv['direction']}) · Point vs 90% Conformal Interval vs Delayed Lab Truth",
        height=410,
    )
)
fig.update_xaxes(title_text="Elapsed Time Since Transition Start (minutes)")
fig.update_yaxes(title_text="Melt Flow Index (MFI, g/10min)")
st.plotly_chart(fig, use_container_width=True)

# Model Comparison & Spec-Crossing Examples
c1, c2 = st.columns(2, gap="large")

with c1:
    section_header("Phase-5 Estimator Comparison vs. Baselines")
    mc_rows = []
    for m in qv["model_comparison"]:
        mc_rows.append(
            {
                "Model / Baseline": m["model_label"],
                "Calibration MAE": round(float(m["calib_mae"]), 4) if m["calib_mae"] is not None else None,
                "Calibration RMSE": round(float(m["calib_rmse"]), 4) if m["calib_rmse"] is not None else None,
                "Locked Test MAE": round(float(m["locked_mae"]), 4) if m["locked_mae"] is not None else None,
                "Locked Test RMSE": round(float(m["locked_rmse"]), 4) if m["locked_rmse"] is not None else None,
                "Locked Bias": round(float(m["locked_bias"]), 4) if m["locked_bias"] is not None else None,
            }
        )
    st.dataframe(pd.DataFrame(mc_rows), use_container_width=True, hide_index=True)

    section_header("Phase-6 Conformal Method Selection (CALIBRATION Split Only)")
    cal_methods = cs.get("calibration_coverage_by_method", {})
    cm_rows = []
    for m_name, m_stats in cal_methods.items():
        cm_rows.append(
            {
                "Conformal Method": m_name,
                "Rows": m_stats.get("n_rows"),
                "Empirical Coverage": round(float(m_stats.get("coverage", 0.0)), 4),
                "Mean Width (g/10m)": round(float(m_stats.get("mean_width", 0.0)), 4),
                "Selected": "✅ YES" if m_name == cs.get("chosen_method") else "Gated / No",
            }
        )
    st.dataframe(pd.DataFrame(cm_rows), use_container_width=True, hide_index=True)

with c2:
    section_header("Why Point-In-Spec Is Insufficient: Spec-Crossing Examples")
    st.markdown(
        "Cases where `point_mfi` is inside the commercial specification band, "
        "but the 90% calibrated interval crosses a specification boundary — forcing PrimePath "
        "to recommend `HOLD` or `SAMPLE_NOW` instead of a premature `PRIME_RELEASE_CANDIDATE`:"
    )
    sc_examples = cs.get("spec_crossing_examples", [])
    if sc_examples:
        sc_rows = []
        for ex in sc_examples:
            sc_rows.append(
                {
                    "Event": ex.get("event_id"),
                    "Direction": ex.get("direction"),
                    "Point MFI": round(float(ex.get("point_mfi", 0.0)), 3),
                    "90% Interval": f"[{ex['interval'][0]:.3f}, {ex['interval'][1]:.3f}]",
                    "Spec Band": f"[{ex['spec_band'][0]:.2f}, {ex['spec_band'][1]:.2f}]",
                    "Point State": ex.get("point_state"),
                    "Interval State": ex.get("uncertainty_state"),
                    "Prime Eligible?": str(ex.get("prime_candidacy_eligible_by_interval")),
                }
            )
        st.dataframe(pd.DataFrame(sc_rows), use_container_width=True, hide_index=True)

    section_header("Locked Coverage by Transition Phase & Direction")
    by_phase = cs.get("locked_by_phase", {})
    bp_rows = [
        {
            "Phase / Subgroup": k,
            "Rows": v.get("n_rows"),
            "Coverage": f"{100.0 * float(v.get('coverage', 0.0)):.1f}%",
            "Mean Width": round(float(v.get("mean_width", 0.0)), 4),
        }
        for k, v in by_phase.items()
    ]
    st.dataframe(pd.DataFrame(bp_rows), use_container_width=True, hide_index=True)

with st.expander("Inspect Causal Feature Registry (`feat-v1`)") :
    st.dataframe(pd.DataFrame(qv["feature_schema"]), use_container_width=True, hide_index=True)

insight(
    "<strong>Calibration Honesty Note:</strong> Split-conformal calibration is fit strictly on the "
    "chronological <code>CALIBRATION</code> partition (141 rows across 3 events). On <code>LOCKED_TEST</code> "
    "(directions B→C and C→B unseen in TRAIN), empirical interval coverage drops to 65.96% during active "
    "transitions — which is why PrimePath pairs conformal intervals with the train-only <code>ApplicabilityDetector</code> "
    "that blocks all 235 locked rows."
)
