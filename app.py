"""
GradeShift PrimePath — Decision Cockpit (Main Entry Point)
An uncertainty-aware, human-authorized commercial-disposition decision layer
for polyolefin grade transitions.

Strictly read-only and advisory. Never writes setpoints, never actuates plant
equipment, and never certifies or releases polymer without human QC sign-off.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from gs_theme import (
    COLOR,
     action_hero_card,
    badge,
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
    DEMO_STEP_KEYS,
    ExecutionMode,
    build_cockpit_view,
    build_executive_view,
    build_locked_validation_view,
)

st.set_page_config(
    page_title="GradeShift PrimePath | Decision Cockpit",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_brand()
sidebar_nav()

rt = get_cached_runtime()

# ──────────────────────────────────────────────────────────────
# SIDEBAR CONTROLS (Mode, Scenario, Step / Episode, Faults)
# ──────────────────────────────────────────────────────────────
st.sidebar.markdown('<div class="gs-nav-section">Cockpit Controls</div>', unsafe_allow_html=True)

mode_options = [
    ExecutionMode.ILLUSTRATIVE_DEMO.value,
    ExecutionMode.SYNTHETIC_REPLAY.value,
    ExecutionMode.LOCKED_VALIDATION.value,
]
mode_labels = {
    ExecutionMode.ILLUSTRATIVE_DEMO.value: "Illustrative Demo (DEMO-A2B)",
    ExecutionMode.SYNTHETIC_REPLAY.value: "Synthetic Corpus Replay (18 Events)",
    ExecutionMode.LOCKED_VALIDATION.value: "Locked Validation (5 Test Events)",
}
selected_mode = st.sidebar.selectbox(
    "Operating / Evidence Mode",
    options=mode_options,
    format_func=lambda m: mode_labels[m],
    index=0,
)

selected_scenario = st.sidebar.selectbox(
    "Economic Scenario (ASSUMPTION)",
    options=["BASE", "LOW", "HIGH"],
    index=0,
)

demo_step_labels = {
    "T1_HOLD": "T1 (360m): Interval Crosses Spec → HOLD",
    "T2_SAMPLE_NOW": "T2 (380m): Boundary + Sample Avail → SAMPLE NOW",
    "T3_PRIME_CANDIDATE": "T3 (400m): Full Interval In-Spec → PRIME CANDIDATE",
    "T4_TRUTH_RECONCILED": "T4 (445m): Lab Truth Revealed (7.95) → Reconciled",
    "T5_ECONOMIC_LEDGER": "T5 (445m): Episode Economic Ledger",
    "T6_FAULT_ABSTAIN": "T6 (Fault): Frozen MFI Analyzer → ABSTAIN",
}

if "demo_step" not in st.session_state:
    st.session_state["demo_step"] = "T3_PRIME_CANDIDATE"
if "approval_status" not in st.session_state:
    st.session_state["approval_status"] = ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value

selected_event_id = "EP-AB-00"
selected_step_idx = 18
sample_available = True
fault_kind = "NONE"

if selected_mode == ExecutionMode.ILLUSTRATIVE_DEMO.value:
    chosen_demo_step = st.sidebar.selectbox(
        "Demo Walkthrough Step",
        options=DEMO_STEP_KEYS,
        format_func=lambda k: demo_step_labels[k],
        index=DEMO_STEP_KEYS.index(st.session_state["demo_step"]),
    )
    st.session_state["demo_step"] = chosen_demo_step
else:
    if selected_mode == ExecutionMode.LOCKED_VALIDATION.value:
        avail_events = [
            ev.event_id
            for ev in rt.corpus
            if rt.partitions[ev.event_id].value == "LOCKED_TEST"
        ]
    else:
        avail_events = [ev.event_id for ev in rt.corpus]

    selected_event_id = st.sidebar.selectbox(
        "Transition Episode",
        options=avail_events,
        format_func=lambda eid: f"{eid} ({rt.events_by_id[eid].direction} · {rt.partitions[eid].value})",
        index=0,
    )
    grid_len = len(rt.decision_grid(rt.events_by_id[selected_event_id]))
    selected_step_idx = st.sidebar.slider(
        "Decision Step Index (10-min grid)",
        min_value=0,
        max_value=max(0, grid_len - 1),
        value=min(18, max(0, grid_len - 1)),
    )
    sample_available = st.sidebar.checkbox("Lab Grab Sample Available", value=True)
    if selected_mode == ExecutionMode.SYNTHETIC_REPLAY.value:
        fault_kind = st.sidebar.selectbox(
            "Sensor Fault Injection (Guardian)",
            options=[
                "NONE",
                "FROZEN_MFI",
                "MISSING_MFI",
                "STALE_MFI",
                "SPIKE_MFI",
                "GAP_H2",
                "TIMESTAMP_DISORDER",
            ],
            index=0,
        )

# Build Cockpit View from Presenter Layer
view = build_cockpit_view(
    rt,
    mode=selected_mode,
    scenario_name=selected_scenario,
    demo_step=st.session_state["demo_step"],
    event_id=selected_event_id,
    step_idx=selected_step_idx,
    sample_available=sample_available,
    fault_kind=fault_kind,
    approval_status=st.session_state["approval_status"],
)

dir_parts = view["direction"].split("->")
g_from = dir_parts[0] if len(dir_parts) == 2 else "A"
g_to = dir_parts[1] if len(dir_parts) == 2 else "B"

topbar(
    current_grade_from=g_from,
    current_grade_to=g_to,
    unit=view["unit"],
    mode_label=view["mode_meta"]["label"],
    partition_label=f"{view['event_id']} ({view['partition']})",
)

page_title(
    "PrimePath Decision Cockpit",
    "An uncertainty-aware, human-authorized commercial-disposition decision layer for polyolefin grade transitions. — Know when it is a prime-release candidate. Prove why. Learn every transition.",
    eyebrow="GRADESHIFT PRIMEPATH · COMPETITION-READY PRODUCT INTERFACE",
)

mode_banner(view["mode_meta"])

# ──────────────────────────────────────────────────────────────
# 30-SECOND JUDGE STRIP: 5 QUESTIONS ANSWERED AT A GLANCE
# ──────────────────────────────────────────────────────────────
q_cols = st.columns(5, gap="small")
for idx, q_item in enumerate(view.get("five_jury_questions", [])):
    with q_cols[idx]:
        st.markdown(
            f'<div style="background:{COLOR["card"]}; border:1px solid {COLOR["border"]}; border-top:3px solid {COLOR["blue"]}; border-radius:6px; padding:10px 12px; min-height:118px; margin-bottom:10px;">'
            f'<div style="font-size:0.66rem; font-weight:700; letter-spacing:0.06em; color:{COLOR["blue"]}; text-transform:uppercase; margin-bottom:4px;">{q_item["question"]}</div>'
            f'<div style="font-size:0.76rem; line-height:1.38; color:{COLOR["text"]};">{q_item["answer"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

tab_cockpit, tab_exec, tab_locked = st.tabs(
    [
        "🎛️ Operator Decision Cockpit (Deep Technical View)",
        "📊 Executive Value View (30-Second Judge View)",
        "🔒 Locked Validation & Claim Ledger",
    ]
)

# ══════════════════════════════════════════════════════════════
# TAB 1: OPERATOR DECISION COCKPIT
# ══════════════════════════════════════════════════════════════
with tab_cockpit:
    if selected_mode == ExecutionMode.ILLUSTRATIVE_DEMO.value:
        section_header("Canonical 6-Step Walkthrough Stepper (DEMO-A2B · 3–5 Minute Jury Demo)")
        bcols = st.columns(6)
        short_labels = [
            ("T1_HOLD", "T1 · HOLD"),
            ("T2_SAMPLE_NOW", "T2 · SAMPLE NOW"),
            ("T3_PRIME_CANDIDATE", "T3 · PRIME CANDIDATE"),
            ("T4_TRUTH_RECONCILED", "T4 · LAB TRUTH"),
            ("T5_ECONOMIC_LEDGER", "T5 · ECON LEDGER"),
            ("T6_FAULT_ABSTAIN", "T6 · FAULT ABSTAIN"),
        ]
        for idx, (s_key, s_lbl) in enumerate(short_labels):
            if bcols[idx].button(
                s_lbl,
                key=f"btn_{s_key}",
                use_container_width=True,
                type="primary" if st.session_state["demo_step"] == s_key else "secondary",
            ):
                st.session_state["demo_step"] = s_key
                st.rerun()

    # Primary Recommendation Hero Card
    action_hero_card(
        action=view["action"],
        action_meta=view["action_meta"],
        reason_codes=view["reason_codes"],
        approval_status=view["approval_status"],
        approver_role=view["approver_role"],
        narrative=view["narrative"],
    )

    # 10-Stage Decision Lineage Chain Strip
    chain_items = view.get("central_lineage_chain", [])
    if chain_items:
        chain_html_parts = []
        for c_idx, stage in enumerate(chain_items):
            arrow = " → " if c_idx < len(chain_items) - 1 else ""
            chain_html_parts.append(
                f"<span style='display:inline-block; background:#F8FAFC; border:1px solid {COLOR['border']}; "
                f"border-radius:4px; padding:4px 8px; margin:2px; font-size:0.73rem;'>"
                f"<strong style='color:{COLOR['navy']};'>{stage['stage']}:</strong> "
                f"<span style='color:{COLOR['text']}; font-family:monospace;'>{stage['value']}</span></span>"
                f"<span style='color:{COLOR['text2']}; font-weight:700;'>{arrow}</span>"
            )
        st.markdown(
            f"<div style='background:{COLOR['card']}; border:1px solid {COLOR['border']}; border-radius:6px; padding:8px 12px; margin-bottom:14px;'>"
            f"<div style='font-size:0.68rem; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:{COLOR['text2']}; margin-bottom:4px;'>"
            f"End-to-End Auditable Decision Lineage Chain (Live State at t+{view['elapsed_min']:.0f}m)</div>"
            + "".join(chain_html_parts)
            + "</div>",
            unsafe_allow_html=True,
        )

    # 4-Column KPI Strip
    pred = view["prediction"]
    spec = view["spec_band"]
    mw = view["material_window"]
    econ = view["economics"]

    k1, k2, k3, k4 = st.columns(4)
    interval_inside = (
        pred["lower_mfi"] >= spec["mfi_low"] and pred["upper_mfi"] <= spec["mfi_high"]
    )
    with k1:
        st.markdown(
            panel_open()
            + kpi_card(
                "90% Conformal Interval",
                f"[{pred['lower_mfi']:.2f}, {pred['upper_mfi']:.2f}]",
                "g/10m",
                f"Point: {pred['point_mfi']:.2f} vs Spec [{spec['mfi_low']:.2f}, {spec['mfi_high']:.2f}]",
                "pos" if interval_inside else "neg",
            )
            + panel_close(),
            unsafe_allow_html=True,
        )
    with k2:
        hg_ok = view["hard_gates_passed"] == view["hard_gates_total"]
        st.markdown(
            panel_open()
            + kpi_card(
                "Hard Policy Gates",
                f"{view['hard_gates_passed']}/{view['hard_gates_total']}",
                "PASS",
                f"Candidacy Gates: {view['candidacy_gates_passed']}/{view['candidacy_gates_total']} PASS",
                "pos" if hg_ok else "neg",
            )
            + panel_close(),
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            panel_open()
            + kpi_card(
                "Mapped Material Window",
                f"{mw['mapped_mass_tonnes']:.1f}",
                "tonnes",
                f"Mean Age: {mw['mean_age_min']:.1f}m · {mw['mapping_quality']}",
                "pos" if mw["mapping_quality"] == "WELL_SUPPORTED" else "neu",
            )
            + panel_close(),
            unsafe_allow_html=True,
        )
    with k4:
        cf_opp = float(econ.get("counterfactual_opportunity_currency", 0.0))
        el_chosen = float(econ.get("expected_loss_chosen_currency", 0.0))
        st.markdown(
            panel_open()
            + kpi_card(
                f"Counterfactual Spread ({selected_scenario})",
                f"₹{cf_opp / 1e5:.2f}",
                "Lakh",
                f"Expected Loss (Chosen): ₹{el_chosen:,.0f} (SIMULATED)",
                "pos" if cf_opp > 0 else "neu",
            )
            + panel_close(),
            unsafe_allow_html=True,
        )

    # Main Split: Trajectory + Conformal Interval vs Governance & Material Lineage
    col_chart, col_gov = st.columns([1.45, 1.0], gap="large")

    with col_chart:
        section_header("As-Of Quality Trajectory & Split-Conformal Interval vs Spec")
        fig = go.Figure()

        # Target Spec Band Shading
        fig.add_hrect(
            y0=spec["mfi_low"],
            y1=spec["mfi_high"],
            fillcolor=COLOR["spec_fill"],
            line_width=1,
            line_dash="dot",
            line_color=COLOR["green"],
            annotation_text=f"Grade {spec['grade_id']} Spec [{spec['mfi_low']:.2f}, {spec['mfi_high']:.2f}]",
            annotation_position="top left",
        )

        # Online MFI series up to decision time t
        t_cur = float(view["elapsed_min"])
        series_upto = [pt for pt in view["mfi_series"] if pt["t_min"] <= t_cur]
        if series_upto:
            fig.add_trace(
                go.Scatter(
                    x=[p["t_min"] for p in series_upto],
                    y=[p["value"] for p in series_upto],
                    mode="lines",
                    name="Online MFI Analyzer (<= t)",
                    line=dict(color=COLOR["baseline"], width=2),
                )
            )

        # Completed lab results known as-of t
        labs_upto = [lp for lp in view["lab_points"] if lp["result_min"] <= t_cur]
        if labs_upto:
            fig.add_trace(
                go.Scatter(
                    x=[lp["result_min"] for lp in labs_upto],
                    y=[lp["mfi"] for lp in labs_upto],
                    mode="markers",
                    name="Resulted Lab MFI (<= t)",
                    marker=dict(color=COLOR["navy"], size=8, symbol="diamond"),
                )
            )

        # Calibrated 90% Interval Error Bar at decision time t
        fig.add_trace(
            go.Scatter(
                x=[t_cur],
                y=[pred["point_mfi"]],
                error_y=dict(
                    type="data",
                    symmetric=False,
                    array=[pred["upper_mfi"] - pred["point_mfi"]],
                    arrayminus=[pred["point_mfi"] - pred["lower_mfi"]],
                    color=view["action_meta"]["color"],
                    thickness=3,
                    width=10,
                ),
                mode="markers",
                name=f"90% Conformal Interval [{pred['lower_mfi']:.2f}, {pred['upper_mfi']:.2f}]",
                marker=dict(color=view["action_meta"]["color"], size=12, symbol="circle"),
            )
        )

        # If lab truth is revealed (e.g., Step T4/T5), plot reconciled truth marker
        if view.get("revealed_mfi") is not None and (
            selected_mode != ExecutionMode.ILLUSTRATIVE_DEMO.value
            or st.session_state["demo_step"] in ("T4_TRUTH_RECONCILED", "T5_ECONOMIC_LEDGER")
        ):
            fig.add_trace(
                go.Scatter(
                    x=[t_cur + 45.0],
                    y=[float(view["revealed_mfi"])],
                    mode="markers",
                    name=f"Later Revealed Lab Truth ({float(view['revealed_mfi']):.2f} g/10m)",
                    marker=dict(color=COLOR["green"], size=13, symbol="star"),
                )
            )

        fig.update_layout(
            **chart_layout(
                title=f"Event {view['event_id']} · Decision Time t = {t_cur:.0f} min (Causal As-Of Slice)",
                height=390,
            )
        )
        fig.update_xaxes(title_text="Elapsed Time Since Transition Start (minutes)")
        fig.update_yaxes(title_text="Melt Flow Index (MFI, g/10min)")
        st.plotly_chart(fig, use_container_width=True)

        # Causal Firewall Evidence Card
        st.markdown(
            panel_open("Causal As-Of Firewall & Step Transition Audit")
            + data_row("Decision Timestamp (UTC)", str(view["decision_time"]))
            + data_row("What PrimePath KNEW at t", str(view["what_knew"]))
            + data_row("What PrimePath Did NOT Know at t", str(view["what_did_not_know"]))
            + data_row("Why the Action Changed", str(view.get("why_action_changed", "")))
            + data_row(
                "Dwell Status (As-Of t)",
                f"{view['dwell'].get('elapsed_min', 0.0):.1f}m / {view['dwell'].get('required_min', 30.0):.1f}m "
                f"({'SATISFIED' if view['dwell'].get('satisfied') else 'INCOMPLETE'})",
            )
            + panel_close(),
            unsafe_allow_html=True,
        )

    with col_gov:
        section_header("Human / QC Authorization & Material Window")

        # Human QC Approval Card
        st.markdown(
            panel_open("Human Quality Authority Sign-Off (Advisory Boundary)")
            + data_row("Required Approver Role", str(view["approver_role"]))
            + data_row("Disposition Action", str(view["action"]))
            + data_row("Current Authorization Status", str(view["approval_status"]))
            + data_row("DCS / Valve Actuation", "NONE (Strictly Read-Only Advisory)")
            + panel_close(),
            unsafe_allow_html=True,
        )

        if view["action"] == "PRIME_RELEASE_CANDIDATE":
            ac1, ac2, ac3 = st.columns(3)
            if ac1.button("✅ Authorize (Demo QC)", use_container_width=True):
                st.session_state["approval_status"] = (
                    ApprovalStatus.HUMAN_AUTHORIZED_IN_DEMO.value
                )
                st.rerun()
            if ac2.button("⏸️ Keep Pending", use_container_width=True):
                st.session_state["approval_status"] = (
                    ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value
                )
                st.rerun()
            if ac3.button("❌ Reject / Hold", use_container_width=True):
                st.session_state["approval_status"] = (
                    ApprovalStatus.REJECTED_OR_HELD.value
                )
                st.rerun()

        # Mapped Material Identity Card
        st.markdown(
            panel_open("Downstream Material Window & Residence Mapping")
            + data_row("Mapped Polymer Mass", f"{mw['mapped_mass_tonnes']:.2f} tonnes")
            + data_row("Recoverable Mass", f"{mw['recoverable_mass_tonnes']:.2f} tonnes")
            + data_row("Mean Residence Age", f"{mw['mean_age_min']:.1f} min")
            + data_row("Residence Uncertainty", f"±{mw['residence_uncertainty_min']:.1f} min")
            + data_row("Mapping Quality", str(mw["mapping_quality"]))
            + data_row("Current Destination Route", str(mw["primary_destination"]))
            + panel_close(),
            unsafe_allow_html=True,
        )

        # Sensor Health & Applicability Summary Card
        st.markdown(
            panel_open("Sensor Health & OOD Applicability Guardian")
            + data_row("Sensor Health State", str(view["health_state"]))
            + data_row("OOD Applicability State", str(view["applicability_state"]))
            + data_row(
                "Permitted Actions (Post-Gate)",
                ", ".join(view["permitted_actions"]),
            )
            + data_row(
                "Model / Calibrator Version",
                f"{view['versions']['model']} · {view['versions']['calibration']}",
            )
            + panel_close(),
            unsafe_allow_html=True,
        )

    # Bottom Section: 13 Hard Gates + 5 Candidacy Gates & Expected Loss Table
    section_header("Complete 18-Gate Policy Audit (13 Hard BLOCK Gates + 5 Candidacy Gates)")
    g_col, e_col = st.columns([1.35, 1.0], gap="large")

    with g_col:
        gate_rows = []
        for g in view["gates"]:
            gate_rows.append(
                {
                    "Gate ID": g["gate_id"],
                    "Class": "HARD (BLOCK)" if g["severity_name"] == "BLOCK" else "CANDIDACY",
                    "Status": "PASS" if g["passed"] else "FAIL",
                    "Reason Code": g["reason_code"],
                    "Detail": g.get("detail", ""),
                }
            )
        st.dataframe(pd.DataFrame(gate_rows), use_container_width=True, hide_index=True)

    with e_col:
        el_rows = econ.get("expected_loss_table", {}).get("rows", [])
        el_df_rows = []
        for r in el_rows:
            el_df_rows.append(
                {
                    "Permitted Action": r["action"],
                    "Expected Loss (₹)": f"₹{r['expected_loss_currency']:,.0f}",
                    "False-Prime Exp (₹)": f"₹{r['false_prime_exposure_currency']:,.0f}",
                    "False-Hold Exp (₹)": f"₹{r['false_hold_exposure_currency']:,.0f}",
                }
            )
        st.markdown("**Expected Loss Over Permitted Actions Only (Phase 10)**")
        st.dataframe(pd.DataFrame(el_df_rows), use_container_width=True, hide_index=True)

        voi_info = econ.get("voi", {})
        st.markdown(
            panel_open("Discrete Value of Information (VOI) for Confirmatory Sampling")
            + data_row("VOI (₹)", f"₹{float(voi_info.get('voi_currency', 0.0)):,.0f}")
            + data_row("Sample Cost (₹)", f"₹{float(voi_info.get('sample_cost_currency', 0.0)):,.0f}")
            + data_row("VOI Recommends Sample?", str(voi_info.get("recommend_sample", False)))
            + data_row("VOI Rationale", str(voi_info.get("reason", "")))
            + panel_close(),
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════
# TAB 2: EXECUTIVE VALUE VIEW (30-SECOND JURY SUMMARY)
# ══════════════════════════════════════════════════════════════
with tab_exec:
    ex = build_executive_view(rt, scenario_name=selected_scenario)
    hon = ex["locked_honest_explanation"]
    section_header("Executive Summary — Why PrimePath Exists")
    e1, e2 = st.columns(2, gap="large")
    with e1:
        st.markdown(
            panel_open("1. The Industrial Grade-Transition Dilemma")
            + f"<p style='font-size:0.9rem; line-height:1.55; color:{COLOR['text']};'>{ex['problem_statement']}</p>"
            + f"<p style='font-size:0.9rem; line-height:1.55; color:{COLOR['text']}; margin-top:10px;'><strong>Why Point Soft Sensors Fail:</strong> {ex['why_point_fails']}</p>"
            + panel_close(),
            unsafe_allow_html=True,
        )
    with e2:
        steps_html = "".join(
            f"<div style='padding:5px 0; border-bottom:1px solid {COLOR['border']}; font-size:0.85rem;'><strong>{line}</strong></div>"
            for line in ex["how_primepath_works"]
        )
        st.markdown(
            panel_open("2. Six-Layer PrimePath Decision Lineage")
            + steps_html
            + panel_close(),
            unsafe_allow_html=True,
        )

    section_header("Illustrative Demo Walkthrough vs. Locked Validation Evidence (Strictly Separated)")
    c_demo, c_lock = st.columns(2, gap="large")

    with c_demo:
        st.markdown(
            f"**A. {ex['illustrative_demo_summary']['label']}**  \n"
            "*Demonstrates full action vocabulary on controlled A→B evidence (NOT validation evidence):*"
        )
        st.dataframe(
            pd.DataFrame(ex["illustrative_demo_summary"]["steps"]),
            use_container_width=True,
            hide_index=True,
        )
        insight(
            f"<strong>Illustrative Episode Economics ({selected_scenario} Scenario):</strong> "
            f"On a 50.0 t mapped window with ₹{int(ex['illustrative_demo_summary']['scenario_spread_per_tonne']):,}/t "
            f"prime-vs-downgrade spread, identifying a verified prime candidate represents "
            f"<strong>₹{int(ex['illustrative_demo_summary']['counterfactual_opportunity_currency']):,}</strong> "
            f"in counterfactual opportunity value (SIMULATED/ASSUMPTION — Not an HMEL savings claim)."
        )

    with c_lock:
        st.markdown(
            f"**B. {ex['locked_validation_summary']['label']}**  \n"
            "*Frozen chronological evaluation where B→C and C→B are unseen in TRAIN:*"
        )
        lb = ex["locked_validation_summary"]["level_b_decision"]
        lc = ex["locked_validation_summary"]["level_c_economic"]
        lock_rows = []
        for pol in ["SOP_FIXTURE", "POINT_THRESHOLD", "PRIMEPATH", "ORACLE_DIAGNOSTIC_ONLY"]:
            if pol in lb:
                lock_rows.append(
                    {
                        "Policy": pol,
                        "False-Prime Mass (t)": lb[pol].get("false_prime_mass_tonnes"),
                        "False-Hold Mass (t)": lb[pol].get("false_hold_mass_tonnes"),
                        "Abstention Rate": f"{100.0 * float(lb[pol].get('mean_abstention_rate', 0.0)):.1f}%",
                        "False-Prime Exposure (₹)": f"₹{float(lc.get(pol, {}).get('false_prime_exposure_currency', 0.0)):,.0f}",
                    }
                )
        st.dataframe(pd.DataFrame(lock_rows), use_container_width=True, hide_index=True)
        insight(
            f"<strong>{hon['headline']}</strong><br>{hon['why_blocked']}"
        )


# ══════════════════════════════════════════════════════════════
# TAB 3: LOCKED VALIDATION & CLAIM LEDGER
# ══════════════════════════════════════════════════════════════
with tab_locked:
    lv = build_locked_validation_view(rt)
    hon_lv = lv["locked_honest_explanation"]

    section_header("Honest Locked-Validation Interpretation & Three-Way Evidence Separation")
    h1, h2 = st.columns([1.2, 1.0], gap="large")
    with h1:
        reasons_html = "".join(
            f"<li style='margin-bottom:6px; font-size:0.84rem;'>{r}</li>"
            for r in hon_lv["reasons"]
        )
        st.markdown(
            panel_open(hon_lv["headline"])
            + f"<p style='font-size:0.84rem; color:{COLOR['text']}; margin-bottom:8px;'>{hon_lv['why_blocked']}</p>"
            + f"<ul style='margin:0; padding-left:18px; color:{COLOR['text']};'>{reasons_html}</ul>"
            + panel_close(),
            unsafe_allow_html=True,
        )
    with h2:
        ev_types = hon_lv["evidence_types"]
        st.markdown(
            panel_open("Strict Evidence Type Separation")
            + data_row("1. Observed / Frozen", ev_types["observed_frozen"])
            + data_row("2. Diagnostic Oracle", ev_types["diagnostic_oracle"])
            + data_row("3. Simulated / Illustrative", ev_types["simulated_illustrative"])
            + panel_close(),
            unsafe_allow_html=True,
        )

    section_header("Phase-13 Reproducibility Fingerprints & Pass/Fail Criteria")

    f1, f2 = st.columns([1, 1.3], gap="large")
    with f1:
        fp = lv["fingerprints"]
        st.markdown(
            panel_open("SHA-256 Reproducibility Fingerprints")
            + data_row("Manifest Fingerprint", str(fp.get("manifest", "")))
            + data_row("Calibrator Fingerprint", str(fp.get("calibrator", "")))
            + data_row("Policy Fingerprint", str(fp.get("policy", "")))
            + data_row("Economics Fingerprint", str(fp.get("economics", "")))
            + data_row("Deterministic Replay Match", str(lv["determinism_evidence"].get("identical", True)))
            + panel_close(),
            unsafe_allow_html=True,
        )
    with f2:
        pf = lv["pass_fail_criteria"]
        pf_rows = [
            {"Criterion": k, "Passed": "✅ PASS" if v else "❌ FAIL"}
            for k, v in pf.items()
        ]
        st.dataframe(pd.DataFrame(pf_rows), use_container_width=True, hide_index=True)

    section_header("Claim & Evidence Ledger (Strict E2/E3 Ceiling)")
    claims_df = pd.DataFrame(lv["claim_ledger"])
    if not claims_df.empty:
        cols_to_show = [
            c
            for c in [
                "topic",
                "evidence_level",
                "claim",
                "allowed_wording",
                "prohibited_wording",
            ]
            if c in claims_df.columns
        ]
        st.dataframe(claims_df[cols_to_show], use_container_width=True, hide_index=True)

