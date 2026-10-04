"""
Page 6 — Transition Memory & Model Assurance
Replaces the legacy 2D contour / EKF mock with PrimePath's Phase-11 Transition Memory
(`TransitionMemoryStore`, directional 3-analog retrieval, partition/self/reverse-direction
exclusion proofs, no-online-learning guard) and Phase-13 Model Assurance & Claim Ledger.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from gs_theme import (
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
    build_memory_assurance_view,
)

st.set_page_config(
    page_title="GradeShift PrimePath | Memory & Assurance",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_css()
sidebar_brand()
sidebar_nav()

rt = get_cached_runtime()

st.sidebar.markdown('<div class="gs-nav-section">Memory Retrieval</div>', unsafe_allow_html=True)

query_options = ["DEMO-A2B"] + [ev.event_id for ev in rt.corpus]
selected_query = st.sidebar.selectbox(
    "Query Transition Context",
    options=query_options,
    format_func=lambda q: (
        "DEMO-A2B (Fresh A→B Query → 3 Analogs)"
        if q == "DEMO-A2B"
        else f"{q} ({rt.events_by_id[q].direction} · Self-Excluded)"
    ),
    index=0,
)

k_analogs = st.sidebar.slider("Max Analogs to Retrieve (k)", 1, 5, 3)
unit_pol = st.sidebar.selectbox(
    "Unit Matching Policy (`UnitPolicy`)",
    options=["PREFER_SAME_UNIT", "SAME_UNIT_ONLY", "ANY_UNIT"],
    index=0,
)

mv = build_memory_assurance_view(
    rt,
    query_event_id=selected_query,
    k=k_analogs,
    unit_policy=unit_pol,
)

q_rec = mv["query_record"]
dir_parts = q_rec["direction"].split("->")

topbar(
    current_grade_from=dir_parts[0],
    current_grade_to=dir_parts[1],
    unit=q_rec["unit"],
    mode_label="TRANSITION MEMORY & ASSURANCE",
    partition_label=f"QUERY: {selected_query} ({q_rec['direction']})",
)

page_title(
    "Transition Memory & Model Assurance",
    "Append-only reconciled episode memory, directional analog retrieval with scope-isolation proofs, and Phase-13 claim governance.",
    eyebrow="PHASES 11 & 13 · IMMUTABLE MEMORY + CLAIM LEDGER",
)

mode_banner(MODE_META[ExecutionMode.LOCKED_VALIDATION.value])

# Top KPI Strip
stats = mv["store_stats"]
excl = mv["exclusion_proof"]
pf = mv["pass_fail_criteria"]

k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(
        panel_open()
        + kpi_card(
            "Reconciled Episodes in Store",
            f"{stats.get('reconciled_episodes', 18)}/{stats.get('total_episodes', 18)}",
            "episodes",
            "Immutable append-only MemoryRecord store",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k2:
    st.markdown(
        panel_open()
        + kpi_card(
            "Retrieved TRAIN Analogs",
            str(len(mv["analogs"])),
            f"for {q_rec['direction']}",
            f"IDs: {', '.join(excl['retrieved_event_ids']) or 'None (Unseen Direction)'}",
            "pos" if mv["analogs"] else "neu",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k3:
    all_excl_ok = (
        excl["self_excluded"]
        and excl["opposite_direction_excluded"]
        and excl["locked_test_excluded"]
    )
    st.markdown(
        panel_open()
        + kpi_card(
            "Scope & Leakage Isolation",
            "VERIFIED" if all_excl_ok else "CHECK",
            "",
            "Self, opposite-direction & LOCKED_TEST excluded",
            "pos" if all_excl_ok else "neg",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )
with k4:
    st.markdown(
        panel_open()
        + kpi_card(
            "Online Learning / Auto-Retrain",
            "DISABLED",
            "",
            "Storing/reconciling never mutates model or policy",
            "pos",
        )
        + panel_close(),
        unsafe_allow_html=True,
    )

col_m, col_p = st.columns([1.3, 1.0], gap="large")

with col_m:
    section_header(f"1. Retrieved Directional Analogs (`direction={q_rec['direction']}`, `allowed_partition=TRAIN`)")
    if mv["analogs"]:
        analog_rows = []
        for a in mv["analogs"]:
            sim = a.get("similarity", {})
            pred_s = a.get("what_was_predicted", {})
            lab_t = a.get("laboratory_truth", {})
            analog_rows.append(
                {
                    "Analog Event ID": a.get("event_id"),
                    "Partition": a.get("partition"),
                    "Similarity Score": round(float(sim.get("score", 0.0)), 4),
                    "Matching Dimensions": ", ".join(sim.get("matching_dimensions", [])),
                    "Predicted MFI": round(float(pred_s.get("point_mfi", 0.0)), 3),
                    "90% Interval": f"[{pred_s.get('lower_mfi', 0.0):.2f}, {pred_s.get('upper_mfi', 0.0):.2f}]",
                    "Disposition": a.get("what_happened", {}).get("disposition_action"),
                    "Reconciled Lab MFI": round(float(lab_t.get("revealed_mfi", 0.0)), 3),
                    "Was In-Spec?": str(lab_t.get("was_in_spec")),
                }
            )
        st.dataframe(pd.DataFrame(analog_rows), use_container_width=True, hide_index=True)
    else:
        st.warning(
            f"Zero TRAIN analogs retrieved for direction `{q_rec['direction']}` because "
            f"`{q_rec['direction']}` only appears in `CALIBRATION` / `LOCKED_TEST` and is "
            "strictly isolated from `TRAIN`."
        )

    section_header("2. Complete Immutable Episode Store (`TransitionMemoryStore.all_latest()`)")
    rec_rows = []
    for r in mv["all_records"]:
        ps = r.get("prediction_snapshot", {})
        lo = r.get("lab_outcome") or {}
        rec_rows.append(
            {
                "Event ID": r["event_id"],
                "Direction": r["direction"],
                "Partition": r["partition"],
                "Status": r["reconciliation_status"],
                "Version": f"v{r['record_version']}",
                "Point MFI": round(float(ps.get("point_mfi", 0.0)), 3),
                "Action": r["disposition_action"],
                "Lab Truth MFI": round(float(lo.get("revealed_mfi", 0.0)), 3)
                if lo.get("revealed_mfi") is not None
                else None,
                "In-Spec": str(lo.get("was_in_spec")),
            }
        )
    st.dataframe(pd.DataFrame(rec_rows), use_container_width=True, hide_index=True, height=320)

with col_p:
    section_header("3. Scope-Isolation & Leakage Exclusion Proof")
    st.markdown(
        panel_open("Deterministic Retrieval Guardrails (`memory.py`)")
        + data_row("Query Event ID", str(excl["query_event_id"]))
        + data_row("Required Direction", f"{excl['query_direction']} (!= {excl['opposite_direction']})")
        + data_row("Opposite-Direction Events in Store", ", ".join(excl["opposite_direction_events_in_store"]))
        + data_row("LOCKED_TEST Events in Store", ", ".join(excl["locked_test_events_in_store"]))
        + data_row("Retrieved Analog IDs", ", ".join(excl["retrieved_event_ids"]) or "None")
        + data_row("Self-Exclusion Verified?", "✅ YES" if excl["self_excluded"] else "❌ NO")
        + data_row(
            f"Opposite Direction ({excl['opposite_direction']}) Excluded?",
            "✅ YES" if excl["opposite_direction_excluded"] else "❌ NO",
        )
        + data_row("LOCKED_TEST Partition Excluded?", "✅ YES" if excl["locked_test_excluded"] else "❌ NO")
        + data_row("Silent Online Retraining?", "FALSE (Explicitly Prohibited)")
        + panel_close(),
        unsafe_allow_html=True,
    )

    section_header("4. Artifact Versions, Evidence Ladder (`E0` – `E5`) & Reproducibility Fingerprints")
    ev_ladder = mv["evidence_ladder"]
    el_html = panel_open("PrimePath Artifact Versions & Evidence Classification Ladder")
    for k_ver, v_ver in mv["versions"].items():
        el_html += data_row(f"Version [{k_ver}]", str(v_ver))
    for k_fp, v_fp in mv["fingerprints"].items():
        el_html += data_row(f"Fingerprint [{k_fp}]", str(v_fp))
    for lvl, desc in ev_ladder.items():
        el_html += data_row(lvl, str(desc))
    el_html += panel_close()
    st.markdown(el_html, unsafe_allow_html=True)

section_header("5. Frozen Phase-13 Claim & Evidence Governance Ledger (`docs/CLAIMS.md`)")
claims_df = pd.DataFrame(mv["claim_ledger"])
if not claims_df.empty:
    st.dataframe(
        claims_df[
            [
                "topic",
                "evidence_level",
                "claim",
                "source_artifact",
                "allowed_wording",
                "prohibited_wording",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

insight(
    f"<strong>{mv['assurance_statement']}</strong> — Transition Memory gives PrimePath auditable historical "
    "context. It does <em>not</em> perform continuous online learning or silent threshold mutation — "
    "promoting reconciled episodes into a future model training cycle is an explicit, offline, "
    "human-governed engineering action."
)

