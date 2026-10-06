"""Phase 14–17 UI Presenter & Integration Tests.

Verifies that:
  1. `RuntimeContext` loads persisted Phase 5–13 artifacts without retraining.
  2. `build_demo_walkthrough` produces the exact 6-step deterministic progression
     (HOLD -> SAMPLE_NOW -> PRIME_RELEASE_CANDIDATE -> Reconciled -> Ledger -> Fault ABSTAIN).
  3. `ILLUSTRATIVE_DEMO` and `LOCKED_VALIDATION` remain strictly separated.
  4. `build_replay_view` enforces the future-truth firewall unless explicitly toggled.
  5. `build_disposition_view` enforces hard gates first (hard failure -> only ABSTAIN permitted).
  6. `build_guardian_view` triggers ABSTAIN on every sensor fault injection preset.
  7. `build_economic_view` satisfies all economic sanity checks across LOW/BASE/HIGH.
  8. `build_memory_assurance_view` retrieves 3 directional TRAIN analogs and proves
     exclusion of opposite-direction, LOCKED_TEST, and self records.
  9. Active UI files (`app.py`, `pages/1..6`) never import legacy prototype modules
     (`transition_optimizer`, `soft_sensor`, `reactor_simulator`) or mock Gaussian noise.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from gradeshift.ui import (
    ApprovalStatus,
    ExecutionMode,
    build_cockpit_view,
    build_demo_walkthrough,
    build_disposition_view,
    build_economic_view,
    build_executive_view,
    build_guardian_view,
    build_locked_validation_view,
    build_memory_assurance_view,
    build_quality_view,
    build_replay_view,
    load_runtime_context,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def rt():
    return load_runtime_context()


def test_runtime_context_loads_frozen_artifacts(rt):
    assert rt.gbm.model_version == "gbm-mfi-v1"
    assert "split-conformal-v1" in rt.versions["calibration"]
    assert len(rt.corpus) == 18
    assert rt.fingerprints.get("manifest") == "manifest:5abc0eb1ad93f56c"
    assert rt.fingerprints.get("calibrator") == "calib:3cf275c76727911a"
    assert rt.fingerprints.get("policy") == "policy:a2555a4d9431c288"
    assert rt.fingerprints.get("economics") == "econ:6cbd173e21b7b79a"


def test_demo_walkthrough_progression(rt):
    demo = build_demo_walkthrough(rt, scenario_name="BASE")
    actions = [s["action"] for s in demo["steps"]]
    assert actions == [
        "HOLD",
        "SAMPLE_NOW",
        "PRIME_RELEASE_CANDIDATE",
        "PRIME_RELEASE_CANDIDATE",
        "PRIME_RELEASE_CANDIDATE",
        "ABSTAIN",
    ]
    # Step T4 & T5 have revealed lab truth 7.95 in spec
    assert demo["steps_by_id"]["T4_TRUTH_RECONCILED"]["revealed_mfi"] == 7.95
    assert demo["steps_by_id"]["T4_TRUTH_RECONCILED"]["was_in_spec"] is True
    # Step T5 Base scenario 50t * 20,000/t = 1,000,000 INR counterfactual opportunity
    assert (
        demo["steps_by_id"]["T5_ECONOMIC_LEDGER"]["economics"][
            "counterfactual_opportunity_currency"
        ]
        == 1_000_000.0
    )


def test_cockpit_mode_separation_and_locked_abstention(rt):
    demo_view = build_cockpit_view(
        rt,
        mode=ExecutionMode.ILLUSTRATIVE_DEMO.value,
        demo_step="T3_PRIME_CANDIDATE",
    )
    assert demo_view["partition"] == "ILLUSTRATIVE_DEMO"
    assert demo_view["action"] == "PRIME_RELEASE_CANDIDATE"
    assert (
        demo_view["approval_status"]
        == ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value
    )

    locked_view = build_cockpit_view(
        rt,
        mode=ExecutionMode.LOCKED_VALIDATION.value,
        event_id="EP-BC-01",
        step_idx=10,
    )
    assert locked_view["partition"] == "LOCKED_TEST"
    assert locked_view["action"] == "ABSTAIN"
    assert "ABSTAIN_OOD" in locked_view["reason_codes"]


def test_replay_view_causal_firewall_and_policies(rt):
    rv_hidden = build_replay_view(
        rt, event_id="EP-AB-00", step_idx=10, reveal_future_truth=False
    )
    policies = [r["policy"] for r in rv_hidden["comparison_table"]]
    assert policies == [
        "SOP_FIXTURE",
        "POINT_THRESHOLD",
        "PRIMEPATH",
        "ORACLE_DIAGNOSTIC_ONLY",
    ]
    assert all(row["revealed_mfi"] is None for row in rv_hidden["timeline"])

    rv_revealed = build_replay_view(
        rt, event_id="EP-AB-00", step_idx=10, reveal_future_truth=True
    )
    assert any(row["revealed_mfi"] is not None for row in rv_revealed["timeline"])


def test_quality_view_uses_real_gbm_and_conformal(rt):
    qv = build_quality_view(rt, event_id="EP-AB-00")
    assert len(qv["trajectory"]) > 0
    first = qv["trajectory"][0]
    assert first["conformal_lower_mfi"] < first["gbm_point_mfi"] < first["conformal_upper_mfi"]
    assert qv["conformal_summary"]["chosen_method"] == "marginal_symmetric"
    assert len(qv["model_comparison"]) == 4


def test_disposition_workbench_hard_gates_first(rt):
    # All gates pass -> PRIME_RELEASE_CANDIDATE
    w_prime = build_disposition_view(
        rt, lower_mfi=7.70, upper_mfi=8.30, dwell_elapsed_min=45.0
    )
    assert w_prime["action"] == "PRIME_RELEASE_CANDIDATE"
    assert "PRIME_RELEASE_CANDIDATE" in w_prime["permitted_actions"]

    # Interval crosses spec, sample unavailable -> HOLD
    w_hold = build_disposition_view(
        rt, lower_mfi=7.50, upper_mfi=8.30, sample_available=False
    )
    assert w_hold["action"] == "HOLD"
    assert "PRIME_RELEASE_CANDIDATE" not in w_hold["permitted_actions"]

    # Interval crosses spec, sample available -> SAMPLE_NOW
    w_sample = build_disposition_view(
        rt, lower_mfi=7.50, upper_mfi=8.30, sample_available=True
    )
    assert w_sample["action"] == "SAMPLE_NOW"

    # Sensor health ABNORMAL -> ABSTAIN, only ABSTAIN permitted
    w_abstain = build_disposition_view(
        rt, lower_mfi=7.70, upper_mfi=8.30, health_state="ABNORMAL"
    )
    assert w_abstain["action"] == "ABSTAIN"
    assert w_abstain["permitted_actions"] == ["ABSTAIN"]


@pytest.mark.parametrize(
    "fault_kind",
    [
        "FROZEN_MFI",
        "MISSING_MFI",
        "STALE_MFI",
        "SPIKE_MFI",
        "TIMESTAMP_DISORDER",
    ],
)
def test_guardian_fault_presets_force_abstain(rt, fault_kind):
    gv = build_guardian_view(rt, event_id="EP-AB-00", step_idx=18, fault_kind=fault_kind)
    assert gv["resulting_action"] == "ABSTAIN"
    assert gv["health_is_blocking"] is True
    assert "ABSTAIN_SENSOR_HEALTH" in gv["reason_codes"]


def test_guardian_gap_fault_degrades_health_and_blocks_prime(rt):
    gv = build_guardian_view(rt, event_id="EP-AB-00", step_idx=18, fault_kind="GAP_H2")
    assert gv["health_overall"] == "DEGRADED"
    assert gv["resulting_action"] != "PRIME_RELEASE_CANDIDATE"
    assert "HOLD_HEALTH_DEGRADED" in gv["reason_codes"]


def test_economic_view_sanity_and_scenarios(rt):
    ev = build_economic_view(rt, scenario_name="BASE", mass_tonnes=50.0, recoverable_mass_tonnes=50.0)
    assert ev["sanity_checks"]["all_passed"] is True
    assert len(ev["scenario_comparison"]) == 3
    by_sc = {r["scenario"]: r for r in ev["scenario_comparison"]}
    assert by_sc["LOW"]["counterfactual_opportunity_currency"] < by_sc["BASE"]["counterfactual_opportunity_currency"]
    assert by_sc["BASE"]["counterfactual_opportunity_currency"] < by_sc["HIGH"]["counterfactual_opportunity_currency"]


def test_memory_assurance_directional_retrieval_and_exclusions(rt):
    mv = build_memory_assurance_view(rt, query_event_id="DEMO-A2B", k=3)
    assert len(mv["analogs"]) == 3
    excl = mv["exclusion_proof"]
    assert excl["self_excluded"] is True
    assert excl["opposite_direction_excluded"] is True
    assert excl["locked_test_excluded"] is True
    assert excl["online_learning_disabled"] is True

    # Self-exclusion when querying an existing TRAIN episode EP-AB-00
    mv_self = build_memory_assurance_view(rt, query_event_id="EP-AB-00", k=3)
    retrieved_ids = [a["event_id"] for a in mv_self["analogs"]]
    assert "EP-AB-00" not in retrieved_ids
    assert set(retrieved_ids) == {"EP-AB-01", "EP-AB-02"}


def test_executive_and_locked_validation_views(rt):
    ex = build_executive_view(rt)
    assert len(ex["illustrative_demo_summary"]["steps"]) == 6
    lv = build_locked_validation_view(rt)
    assert lv["pass_fail_criteria"]["all_passed"] is True
    assert len(lv["claim_ledger"]) >= 9


def test_active_ui_files_free_of_legacy_imports_and_mocks():
    ui_files = [REPO_ROOT / "app.py", REPO_ROOT / "gs_theme.py"] + list(
        (REPO_ROOT / "pages").glob("*.py")
    )
    forbidden = [
        "transition_optimizer",
        "soft_sensor",
        "reactor_simulator",
        "np.random.normal",
        "optimize_bang_bang",
    ]
    for path in ui_files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, f"Forbidden legacy token '{token}' found in {path.name}"


def test_human_authorization_cannot_override_hard_gate_failure(rt):
    """Phase 25 #8: Human authorization state cannot override hard-gate failure or non-prime action."""
    # Fault step T6 forces ABSTAIN even if HUMAN_AUTHORIZED_IN_DEMO is requested
    v_fault = build_cockpit_view(
        rt,
        mode=ExecutionMode.ILLUSTRATIVE_DEMO.value,
        demo_step="T6_FAULT_ABSTAIN",
        approval_status=ApprovalStatus.HUMAN_AUTHORIZED_IN_DEMO.value,
    )
    assert v_fault["action"] == "ABSTAIN"
    assert v_fault["approval_status"] == ApprovalStatus.NOT_APPLICABLE.value

    # Locked validation OOD step forces ABSTAIN even if HUMAN_AUTHORIZED_IN_DEMO is requested
    v_locked = build_cockpit_view(
        rt,
        mode=ExecutionMode.LOCKED_VALIDATION.value,
        event_id="EP-BC-01",
        step_idx=12,
        approval_status=ApprovalStatus.HUMAN_AUTHORIZED_IN_DEMO.value,
    )
    assert v_locked["action"] == "ABSTAIN"
    assert v_locked["approval_status"] == ApprovalStatus.NOT_APPLICABLE.value

    # Hold step T1 stays HOLD and NOT_APPLICABLE even if HUMAN_AUTHORIZED_IN_DEMO is requested
    v_hold = build_cockpit_view(
        rt,
        mode=ExecutionMode.ILLUSTRATIVE_DEMO.value,
        demo_step="T1_HOLD",
        approval_status=ApprovalStatus.HUMAN_AUTHORIZED_IN_DEMO.value,
    )
    assert v_hold["action"] == "HOLD"
    assert v_hold["approval_status"] == ApprovalStatus.NOT_APPLICABLE.value


def test_pre_reconciliation_views_hide_future_truth(rt):
    """Phase 25 #10: Future truth is strictly hidden in pre-reconciliation decision views."""
    demo = build_demo_walkthrough(rt)
    for pre_key in ("T1_HOLD", "T2_SAMPLE_NOW", "T3_PRIME_CANDIDATE", "T6_FAULT_ABSTAIN"):
        step = demo["steps_by_id"][pre_key]
        assert step["revealed_mfi"] is None, f"Future truth leaked in {pre_key}"
        assert step["was_in_spec"] is None, f"Future truth leaked in {pre_key}"

    # Cockpit in SYNTHETIC_REPLAY and LOCKED_VALIDATION never leaks future truth
    v_rep = build_cockpit_view(
        rt, mode=ExecutionMode.SYNTHETIC_REPLAY.value, event_id="EP-AB-00", step_idx=10
    )
    assert v_rep["revealed_mfi"] is None
    assert v_rep["was_in_spec"] is None

    # Replay view with reveal_future_truth=False masks timeline, step_trace, and future labs
    rv = build_replay_view(rt, event_id="EP-AB-00", step_idx=2, reveal_future_truth=False)
    assert rv["step_trace"]["later_truth"]["revealed_mfi"] is None
    assert rv["step_trace"]["later_truth"]["was_in_spec"] is None
    assert rv["step_trace"]["outcome"]["false_prime_tonnes"] is None
    for lw in rv["lab_windows"]:
        if not lw["known_as_of_step"]:
            assert lw["mfi"] is None


def test_five_jury_questions_and_ten_stage_lineage_chain(rt):
    """Phase 17/20/21/22: Verify jury strip, 10-stage lineage chain, economic construction, and honest locked framing."""
    v = build_cockpit_view(
        rt, mode=ExecutionMode.ILLUSTRATIVE_DEMO.value, demo_step="T3_PRIME_CANDIDATE"
    )
    assert len(v["five_jury_questions"]) == 5
    assert len(v["central_lineage_chain"]) == 10
    assert "why_action_changed" in v and len(v["why_action_changed"]) > 10
    assert (
        v["locked_honest_explanation"]["headline"]
        == "100% abstention is not commercial success. It is evidence that the current model refuses unsupported transitions."
    )

    ev = build_economic_view(rt, scenario_name="BASE")
    assert len(ev["how_constructed"]) == 5
    assert "Not an HMEL savings claim" in ev["economic_framing"]["badges"]

    mv = build_memory_assurance_view(rt, query_event_id="DEMO-A2B")
    assert (
        mv["assurance_statement"]
        == "Historical context is retrieved for auditability. It is not silently used to retrain the locked evaluation."
    )


def test_artifacts_and_fingerprints_unchanged_after_ui_operations(rt):
    """Phase 25 #12 & #13: Memory retrieval and UI presenters never mutate frozen artifacts or SHAs."""
    import hashlib

    tracked = [
        REPO_ROOT / "artifacts" / "final_validation.json",
        REPO_ROOT / "artifacts" / "manifests" / "frozen_validation_manifest.json",
        REPO_ROOT / "artifacts" / "phase5" / "gbm_mfi.joblib",
        REPO_ROOT / "artifacts" / "phase6" / "calibrator_gbm.joblib",
        REPO_ROOT / "artifacts" / "phase7" / "applicability_detector.joblib",
    ]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}

    # Exercise all presenter views
    build_cockpit_view(rt, mode=ExecutionMode.ILLUSTRATIVE_DEMO.value, demo_step="T3_PRIME_CANDIDATE")
    build_cockpit_view(rt, mode=ExecutionMode.LOCKED_VALIDATION.value, event_id="EP-BC-01")
    build_memory_assurance_view(rt, query_event_id="DEMO-A2B", k=3)
    build_economic_view(rt, scenario_name="HIGH")

    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    assert before == after


def test_cli_demo_script_succeeds():
    """Phase 25 #14: CLI demo command executes cleanly with exit code 0."""
    import subprocess
    import sys

    res = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "demo.py")],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, f"scripts/demo.py failed: {res.stderr}"
    assert "T3_PRIME_CANDIDATE" in res.stdout
    assert "100% abstention is not commercial success." in res.stdout
    assert "All 10 Phase-13 Validation Criteria Passed: True" in res.stdout


def test_no_markdown_html_indented_code_blocks():
    """Ensure no st.markdown block in app.py or pages/1..6 emits 4+ space indented HTML that CommonMark renders as a raw code block."""
    import re
    from streamlit.testing.v1 import AppTest

    indented_html_re = re.compile(r"(^|\n)[ \t]{4,}<(div|span|strong|p|ul|li|/div)", re.MULTILINE)
    pages = [
        REPO_ROOT / "app.py",
        REPO_ROOT / "pages" / "1_Grade_Transition.py",
        REPO_ROOT / "pages" / "2_Soft_Sensor.py",
        REPO_ROOT / "pages" / "3_AI_Optimizer.py",
        REPO_ROOT / "pages" / "4_Safety.py",
        REPO_ROOT / "pages" / "5_Economics.py",
        REPO_ROOT / "pages" / "6_Digital_Twin.py",
    ]
    for page_path in pages:
        at = AppTest.from_file(str(page_path), default_timeout=30).run()
        assert not at.exception, f"AppTest exception in {page_path.name}: {at.exception}"
        for md in at.markdown:
            val = md.value or ""
            assert not indented_html_re.search(val), (
                f"Indented HTML in {page_path.name} would render as a code block:\n{val}"
            )


