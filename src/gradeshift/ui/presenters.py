"""Pure-Python Presenter Layer for GradeShift PrimePath UI.

Exposes UI-ready view objects for:
  1. PrimePath Decision Cockpit (`build_cockpit_view`)
  2. Canonical Illustrative Demo Walkthrough (`build_demo_walkthrough`)
  3. Transition Replay (`build_replay_view`)
  4. Quality Evidence (`build_quality_view`)
  5. Disposition Workbench (`build_disposition_view`)
  6. Transition Guardian (`build_guardian_view`)
  7. Economic Ledger (`build_economic_view`)
  8. Transition Memory & Model Assurance (`build_memory_assurance_view`)
  9. Executive Value View (`build_executive_view`)
  10. Locked Validation Inspector (`build_locked_validation_view`)

Every presenter delegates calculation to `src/gradeshift/` domain modules
(`disposition.py`, `economics.py`, `replay.py`, `memory.py`, `health.py`,
`applicability.py`, `calibrator.py`, `estimator.py`, `validation.py`) and
preserves strict separation between `ILLUSTRATIVE_DEMO`, `SYNTHETIC_REPLAY`,
and `LOCKED_VALIDATION`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .. import config as C
from .. import disposition as D
from .. import economics as E
from .. import faults as F
from .. import memory as M
from .. import replay as R
from .. import validation as V
from ..applicability import ApplicabilityResult, ApplicabilityState
from ..health import HealthState, SensorHealthReport, assess_sensor_health
from ..material_service import (
    MATERIAL_SERVICE_VERSION,
    MappingQuality,
    MaterialEligibilityResult,
)
from ..partition import Partition
from ..provenance import Provenance
from ..schemas import PredictionBundle
from ..simulate import generate_episode
from .context import (
    MODE_META,
    ApprovalStatus,
    ExecutionMode,
    RuntimeContext,
    apply_fault_preset,
)

# Human-readable labels & semantic colors for the 4 frozen actions
ACTION_META: Dict[str, Dict[str, str]] = {
    D.HOLD: {
        "display": "HOLD / FOLLOW CURRENT ROUTING",
        "short": "HOLD",
        "color": "#E5A11A",
        "badge_kind": "amber",
        "summary": "Keep routing transitional polymer to current downgrade/wide-spec silo.",
    },
    D.SAMPLE_NOW: {
        "display": "SAMPLE NOW",
        "short": "SAMPLE NOW",
        "color": "#1769E0",
        "badge_kind": "blue",
        "summary": "Request confirmatory laboratory grab sample to resolve boundary uncertainty.",
    },
    D.PRIME_RELEASE_CANDIDATE: {
        "display": "PRIME-RELEASE CANDIDATE",
        "short": "PRIME CANDIDATE",
        "color": "#20A873",
        "badge_kind": "green",
        "summary": (
            "Candidate for prime commercial disposition — ADVISORY ONLY. "
            "Requires Human / Shift Quality Approver (QC) authorization."
        ),
    },
    D.ABSTAIN: {
        "display": "ABSTAIN / FOLLOW SOP",
        "short": "ABSTAIN",
        "color": "#D64545",
        "badge_kind": "red",
        "summary": "Hard gate blocked disposition. Defer to Standard Operating Procedure (SOP).",
    },
}


# ──────────────────────────────────────────────────────────────────────────
# 1. CANONICAL ILLUSTRATIVE DEMO WALKTHROUGH (Steps T1..T5 + T6 Fault Branch)
# ──────────────────────────────────────────────────────────────────────────

DEMO_STEP_KEYS = [
    "T1_HOLD",
    "T2_SAMPLE_NOW",
    "T3_PRIME_CANDIDATE",
    "T4_TRUTH_RECONCILED",
    "T5_ECONOMIC_LEDGER",
    "T6_FAULT_ABSTAIN",
]


def build_demo_walkthrough(
    rt: RuntimeContext,
    scenario_name: str = C.DEFAULT_SCENARIO,
    selected_step: str = "T3_PRIME_CANDIDATE",
    approval_status: str = ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value,
) -> Dict[str, Any]:
    """Construct the rich 6-step canonical illustrative demo (`DEMO-A2B`) using
    the real Phase-9 `evaluate_disposition` and Phase-10 `evaluate_economics`
    engines on controlled evidence, plus the frozen `replay.demo_fixture`.
    """
    sc = C.get_scenario(scenario_name)
    raw_fixture = R.demo_fixture(sc)
    base_time = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ev = generate_episode("DEMO-A2B", "A", "B", seed=4242, start_time=base_time)
    spec = C.get_grade("B")

    def _t(minutes: int) -> datetime:
        return base_time + timedelta(minutes=minutes)

    def _pred(t_min: int, lo: float, hi: float, pb: float = 0.15) -> PredictionBundle:
        return PredictionBundle(
            event_id=ev.event_id,
            decision_time=_t(t_min),
            point_mfi=round((lo + hi) / 2.0, 4),
            lower_mfi=lo,
            upper_mfi=hi,
            nominal_coverage=0.90,
            prob_bad=pb,
            model_version=rt.gbm.model_version,
            calibration_version=f"{rt.calibrator.calibration_version}:{rt.calibrator.method}",
        )

    def _mat() -> MaterialEligibilityResult:
        return MaterialEligibilityResult(
            material_window_available=True,
            mapping_quality=MappingQuality.WELL_SUPPORTED,
            route_known=True,
            mass_reconciled=True,
            residence_uncertainty_min=10.0,
            route_ambiguity=0.0,
            blocking_reason_codes=(),
            reason_codes=("MATERIAL_WELL_SUPPORTED",),
            provenance=Provenance.SIMULATED,
            service_version=MATERIAL_SERVICE_VERSION,
        )

    def _eval_step(
        step_id: str,
        title: str,
        t_min: int,
        lo: float,
        hi: float,
        dwell_elapsed: float,
        sample_avail: bool,
        narrative: str,
        what_knew: str,
        what_did_not_know: str,
        why_action_changed: str,
        fault_health: Optional[SensorHealthReport] = None,
        revealed_mfi: Optional[float] = None,
    ) -> Dict[str, Any]:
        dt = _t(t_min)
        pred = _pred(t_min, lo, hi, pb=0.22 if lo < spec.mfi_low else 0.02)
        hr = fault_health or SensorHealthReport(
            as_of=dt,
            overall_state=HealthState.NORMAL,
            required_available=True,
            signal_states={
                "MFI_online": HealthState.NORMAL,
                "H2_ratio": HealthState.NORMAL,
                "bed_temp": HealthState.NORMAL,
            },
            findings=(),
            rule_version="health-v1",
            provenance=Provenance.SIMULATED,
        )
        ap = ApplicabilityResult(
            state=ApplicabilityState.NORMAL,
            score=0.14,
            reason_codes=("IN_DOMAIN",),
            detail={"direction": "A->B", "unit": ev.unit, "in_train_support": True},
            feature_version="feat-v1",
            detector_version=rt.detector.detector_version,
            applicability_version="applicability-v1",
            provenance=Provenance.SIMULATED,
        )
        dwell = D.DwellStatus(
            required_min=spec.dwell_min,
            elapsed_min=dwell_elapsed,
            satisfied=dwell_elapsed >= spec.dwell_min,
            in_spec_now=spec.in_spec(pred.point_mfi),
            as_of=dt,
        )
        evid = D.DispositionEvidence(
            event=ev,
            decision_time=dt,
            spec=spec,
            prediction=pred,
            material_eligibility=_mat(),
            health_report=hr,
            applicability_result=ap,
            dwell_status=dwell,
            sample_available=sample_avail,
            versions=rt.versions,
        )
        disp = D.evaluate_disposition(evid)
        was_good = (
            spec.in_spec(revealed_mfi) if revealed_mfi is not None else None
        )
        econ_in = E.EconomicInputs(
            event_id=ev.event_id,
            decision_id=f"DEMO-A2B@{step_id}",
            mass_tonnes=50.0,
            recoverable_mass_tonnes=50.0,
            actual_route_value_per_tonne=float(sc.downgrade_price),
            scenario=sc,
        )
        econ = E.evaluate_economics(disp, econ_in, realized_good=was_good)
        return {
            "step_id": step_id,
            "title": title,
            "t_min": t_min,
            "decision_time": dt.isoformat(),
            "narrative": narrative,
            "what_knew": what_knew,
            "what_did_not_know": what_did_not_know,
            "why_action_changed": why_action_changed,
            "action": disp.action,
            "action_meta": ACTION_META[disp.action],
            "reason_codes": list(disp.reason_codes),
            "prediction": {
                "point_mfi": pred.point_mfi,
                "lower_mfi": pred.lower_mfi,
                "upper_mfi": pred.upper_mfi,
                "width": round(pred.upper_mfi - pred.lower_mfi, 4),
                "nominal_coverage": pred.nominal_coverage,
            },
            "spec_band": {
                "grade_id": spec.grade_id,
                "name": spec.name,
                "target_mfi": spec.target_mfi,
                "mfi_low": spec.mfi_low,
                "mfi_high": spec.mfi_high,
                "dwell_min": spec.dwell_min,
            },
            "dwell": dwell.to_dict(),
            "material_window": {
                "mapped_mass_tonnes": 50.0,
                "recoverable_mass_tonnes": 50.0,
                "mean_age_min": 42.0,
                "age_spread_min": 11.5,
                "residence_uncertainty_min": 10.0,
                "primary_destination": "SILO-DOWNGRADE-02",
                "mapping_quality": "WELL_SUPPORTED",
                "route_known": True,
                "production_window": f"t-{52}m to t-{32}m",
            },
            "gates": [g.to_dict() for g in disp.gates],
            "hard_gates_passed": sum(
                1 for g in disp.gates if g.severity == D.Severity.BLOCK and g.passed
            ),
            "hard_gates_total": sum(
                1 for g in disp.gates if g.severity == D.Severity.BLOCK
            ),
            "candidacy_gates_passed": sum(
                1 for g in disp.gates if g.severity == D.Severity.CANDIDACY and g.passed
            ),
            "candidacy_gates_total": sum(
                1 for g in disp.gates if g.severity == D.Severity.CANDIDACY
            ),
            "health_state": hr.overall_state.name,
            "health_findings": [f.to_dict() for f in hr.findings],
            "applicability_state": ap.state.name,
            "permitted_actions": list(econ.permitted_actions),
            "economics": econ.to_ledger(),
            "revealed_mfi": revealed_mfi,
            "was_in_spec": was_good,
            "disposition_result": disp,
            "economic_result": econ,
        }

    # Build the 6 canonical walkthrough steps
    s1 = _eval_step(
        step_id="T1_HOLD",
        title="Step T1 (t=360m) — Point In-Spec, Interval Crosses Spec → HOLD",
        t_min=360,
        lo=7.50,
        hi=8.30,
        dwell_elapsed=35.0,
        sample_avail=False,
        narrative=(
            "Point estimate (7.90 g/10min) lies inside Grade B spec [7.60, 8.40], "
            "but the 90% calibrated interval [7.50, 8.30] crosses the lower spec limit "
            "(7.50 < 7.60) and confirmatory sampling is not yet available."
        ),
        what_knew="Online MFI=7.88, H2/C2 stabilized, point=7.90, 90% interval=[7.50, 8.30].",
        what_did_not_know="True laboratory MFI at pelletizer (45-min lab delay still pending).",
        why_action_changed=(
            "Baseline transition state: Although the point estimate (7.90) is inside spec, "
            "the lower conformal bound (7.50) violates 7.60 and grab sampling is unavailable → HOLD."
        ),
    )
    s2 = _eval_step(
        step_id="T2_SAMPLE_NOW",
        title="Step T2 (t=380m) — Boundary Uncertainty + Positive VOI → SAMPLE NOW",
        t_min=380,
        lo=7.50,
        hi=8.30,
        dwell_elapsed=45.0,
        sample_avail=True,
        narrative=(
            "Calibrated interval [7.50, 8.30] still crosses the lower spec limit (7.60), "
            "and a confirmatory lab grab sample is operationally available with 45-min "
            "latency inside the 240-min decision horizon."
        ),
        what_knew="Interval crosses spec [7.50 < 7.60]; grab sample latency (45m) <= horizon (240m).",
        what_did_not_know="Whether the boundary packet is genuinely >= 7.60 g/10min.",
        why_action_changed=(
            "Changed from HOLD → SAMPLE NOW because confirmatory lab sampling became available "
            "within the 240-min horizon and resolves the boundary uncertainty [7.50, 8.30]."
        ),
    )
    s3 = _eval_step(
        step_id="T3_PRIME_CANDIDATE",
        title="Step T3 (t=400m) — Full Interval Inside Spec + 13 Gates Pass → PRIME CANDIDATE",
        t_min=400,
        lo=7.70,
        hi=8.30,
        dwell_elapsed=60.0,
        sample_avail=False,
        narrative=(
            "All 13 hard policy gates pass, the entire 90% calibrated interval [7.70, 8.30] "
            "lies strictly inside Grade B specification [7.60, 8.40], and 60 min dwell "
            "exceeds the 30 min requirement. Flagged as PRIME-RELEASE CANDIDATE awaiting QC sign-off."
        ),
        what_knew="90% interval [7.70, 8.30] strictly inside [7.60, 8.40]; dwell 60m >= 30m; all 13 hard gates PASS.",
        what_did_not_know="Post-hoc laboratory confirmation sample result (arrives at T4).",
        why_action_changed=(
            "Changed from SAMPLE NOW → PRIME-RELEASE CANDIDATE because the entire 90% conformal "
            "interval [7.70, 8.30] converged inside [7.60, 8.40] with 60m dwell and all hard gates passing."
        ),
    )
    s4 = _eval_step(
        step_id="T4_TRUTH_RECONCILED",
        title="Step T4 (t=445m) — Delayed Lab Truth Revealed (7.95 g/10min) → Reconciled",
        t_min=400,
        lo=7.70,
        hi=8.30,
        dwell_elapsed=60.0,
        sample_avail=False,
        narrative=(
            "45 minutes later, laboratory ASTM D1238 test returns revealed_mfi = 7.95 g/10min "
            "(strictly inside [7.60, 8.40]). The candidate window was genuinely in-spec prime polymer."
        ),
        what_knew="As-of T3 decision was locked before T4 lab result arrived (causal firewall).",
        what_did_not_know="At T3, future truth 7.95 g/10min was hidden; revealed only now at T4 for reconciliation.",
        why_action_changed=(
            "As-of T3 recommendation is preserved; delayed ASTM D1238 lab truth (7.95 g/10min) "
            "arrives at t=445m and reconciles the candidate window as genuinely in-spec."
        ),
        revealed_mfi=7.95,
    )
    s5 = _eval_step(
        step_id="T5_ECONOMIC_LEDGER",
        title="Step T5 (t=445m) — Episode Economic Ledger & Counterfactual Reconciliation",
        t_min=400,
        lo=7.70,
        hi=8.30,
        dwell_elapsed=60.0,
        sample_avail=False,
        narrative=(
            f"Under the {sc.name} scenario (spread ₹{int(sc.downgrade_spread):,}/t on 50 t window), "
            f"reconciling the confirmed good window yields ₹{int(50.0 * sc.downgrade_spread):,} "
            "in counterfactual prime-vs-downgrade opportunity value with ₹0 false-prime exposure."
        ),
        what_knew="Confirmed lab MFI = 7.95 g/10min (in-spec); mapped mass = 50.0 t.",
        what_did_not_know="N/A — Post-reconciliation audit ledger.",
        why_action_changed=(
            f"Reconciled outcome is posted to the Phase-10 Economic Ledger ({sc.name} scenario): "
            f"₹{int(50.0 * sc.downgrade_spread):,} counterfactual opportunity value separated from realized routing."
        ),
        revealed_mfi=7.95,
    )

    # Step T6: Fault injection branch (frozen online analyzer -> ABSTAIN)
    fault_ev = F.freeze_signal(ev, "MFI_online", _t(365), _t(400), value=7.92)
    fault_hr = assess_sensor_health(fault_ev, _t(400))
    s6 = _eval_step(
        step_id="T6_FAULT_ABSTAIN",
        title="Step T6 (Fault Branch) — Frozen MFI Analyzer Injected → ABSTAIN / FOLLOW SOP",
        t_min=400,
        lo=7.70,
        hi=8.30,
        dwell_elapsed=60.0,
        sample_avail=True,
        narrative=(
            "Even when the interval [7.70, 8.30] appears inside spec, injecting a frozen "
            "online analyzer fault trips the `sensor_health` hard gate (Severity.BLOCK). "
            "PrimePath immediately refuses to guess and forces ABSTAIN / FOLLOW SOP."
        ),
        what_knew="MFI_online repeated constant value 7.92 over 35 min -> FROZEN_VALUE health fault.",
        what_did_not_know="True polymer state while primary online analyzer is frozen.",
        why_action_changed=(
            "Changed from PRIME-RELEASE CANDIDATE → ABSTAIN / FOLLOW SOP because a frozen MFI "
            "analyzer fault tripped the sensor_health hard gate (Severity.BLOCK). Policy overrides interval."
        ),
        fault_health=fault_hr,
    )

    steps_by_id = {
        s["step_id"]: s for s in (s1, s2, s3, s4, s5, s6)
    }
    active = steps_by_id.get(selected_step, s3)

    # Human authorization state handling — NEVER applies if action != PRIME_RELEASE_CANDIDATE
    if active["action"] == D.PRIME_RELEASE_CANDIDATE:
        eff_approval = (
            approval_status
            if approval_status != ApprovalStatus.NOT_APPLICABLE.value
            else ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value
        )
    else:
        eff_approval = ApprovalStatus.NOT_APPLICABLE.value

    # Trajectory series from the DEMO-A2B episode for plotting
    mfi_series = [
        {
            "t_min": (o.timestamp - base_time).total_seconds() / 60.0,
            "timestamp": o.timestamp.isoformat(),
            "value": o.value,
        }
        for o in ev.series
        if o.tag == "MFI_online"
    ]
    h2_series = [
        {
            "t_min": (o.timestamp - base_time).total_seconds() / 60.0,
            "timestamp": o.timestamp.isoformat(),
            "value": o.value,
        }
        for o in ev.series
        if o.tag == "H2_ratio"
    ]
    lab_points = [
        {
            "sample_id": l.sample_id,
            "collected_min": (l.collected_at - base_time).total_seconds() / 60.0,
            "result_min": (l.result_at - base_time).total_seconds() / 60.0,
            "mfi": l.mfi,
        }
        for l in ev.labs
    ]

    return {
        "mode": ExecutionMode.ILLUSTRATIVE_DEMO.value,
        "mode_meta": MODE_META[ExecutionMode.ILLUSTRATIVE_DEMO.value],
        "event_id": ev.event_id,
        "direction": "A->B",
        "grade_from": C.GRADES["A"],
        "grade_to": C.GRADES["B"],
        "unit": ev.unit,
        "scenario": sc,
        "raw_fixture": raw_fixture,
        "steps": [s1, s2, s3, s4, s5, s6],
        "steps_by_id": steps_by_id,
        "active_step": active,
        "approval_status": eff_approval,
        "mfi_series": mfi_series,
        "h2_series": h2_series,
        "lab_points": lab_points,
        "versions": rt.versions,
        "fingerprints": rt.fingerprints,
    }


def _build_five_jury_questions(view_data: Dict[str, Any], scenario_name: str) -> List[Dict[str, str]]:
    """Construct the 5 immediate judge landing-state Q&A cards."""
    pred = view_data["prediction"]
    spec = view_data["spec_band"]
    mw = view_data["material_window"]
    return [
        {
            "question": "1. WHAT IS THE PROBLEM?",
            "answer": (
                "During polyolefin grade transitions (~50 t/h throughput), lab MFI results lag "
                "production by 45–75 min. Fixed-time SOP rules either downgrade good prime resin "
                "(false hold) or risk routing off-spec resin to prime silos (false prime)."
            ),
        },
        {
            "question": "2. WHY DOES IT MATTER?",
            "answer": (
                "Point-only soft sensors ignore prediction intervals, residence-time mixing, and "
                "out-of-domain shifts — exposing the plant to off-spec prime claims (₹40k–₹90k/t "
                "assumption) or lost prime-vs-downgrade margin (₹12k–₹25k/t assumption, E0/E2)."
            ),
        },
        {
            "question": "3. WHAT DOES PRIMEPATH DECIDE?",
            "answer": (
                f"Active Recommendation: {view_data['action_meta']['display']}. "
                "PrimePath is strictly read-only and advisory — it never writes DCS setpoints or "
                "certifies product; PRIME-RELEASE CANDIDATE always requires Human QC sign-off."
            ),
        },
        {
            "question": "4. WHAT EVIDENCE SUPPORTS THE DECISION?",
            "answer": (
                f"90% Conformal Interval [{pred['lower_mfi']:.2f}, {pred['upper_mfi']:.2f}] g/10m "
                f"vs Grade {spec['grade_id']} Spec [{spec['mfi_low']:.2f}, {spec['mfi_high']:.2f}]; "
                f"Mapped Window: {mw['mapped_mass_tonnes']:.1f} t ({mw['mapping_quality']}); "
                f"Hard Gates: {view_data['hard_gates_passed']}/{view_data['hard_gates_total']} PASS."
            ),
        },
        {
            "question": "5. WHAT HAPPENS WHEN EVIDENCE IS BAD?",
            "answer": (
                "PrimePath does not guess when evidence is insufficient. Any sensor health fault "
                "(frozen, missing, stale, spike), unsupported grade direction (OOD), or ambiguous "
                "material window trips a BLOCK hard gate and forces ABSTAIN / FOLLOW SOP."
            ),
        },
    ]


def _build_central_lineage_chain(view_data: Dict[str, Any]) -> List[Dict[str, str]]:
    """Build the 10-stage end-to-end PrimePath decision lineage chain."""
    pred = view_data["prediction"]
    spec = view_data["spec_band"]
    mw = view_data["material_window"]
    econ = view_data["economics"]
    rev = view_data.get("revealed_mfi")
    return [
        {
            "stage": "1. EVIDENCE",
            "value": f"As-of t={view_data['elapsed_min']}m",
            "detail": "Causal firewall strips future labs/tags",
        },
        {
            "stage": "2. UNCERTAINTY",
            "value": f"[{pred['lower_mfi']:.2f}, {pred['upper_mfi']:.2f}] g/10m",
            "detail": f"Point {pred['point_mfi']:.2f} vs Spec [{spec['mfi_low']:.2f}, {spec['mfi_high']:.2f}]",
        },
        {
            "stage": "3. MATERIAL ID",
            "value": f"{mw['mapped_mass_tonnes']:.1f}t ({mw['mean_age_min']:.0f}m age)",
            "detail": f"Quality: {mw['mapping_quality']}",
        },
        {
            "stage": "4. HEALTH / OOD",
            "value": f"Health: {view_data['health_state']}",
            "detail": f"Domain: {view_data['applicability_state']}",
        },
        {
            "stage": "5. POLICY GATES",
            "value": f"{view_data['hard_gates_passed']}/{view_data['hard_gates_total']} Hard PASS",
            "detail": f"{view_data['candidacy_gates_passed']}/{view_data['candidacy_gates_total']} Candidacy PASS",
        },
        {
            "stage": "6. DISPOSITION",
            "value": view_data["action"],
            "detail": ", ".join(view_data["reason_codes"][:2]),
        },
        {
            "stage": "7. HUMAN QC AUTH",
            "value": view_data["approval_status"],
            "detail": view_data["approver_role"],
        },
        {
            "stage": "8. ECONOMICS",
            "value": f"EL: ₹{float(econ.get('expected_loss_chosen_currency', 0.0)):,.0f}",
            "detail": f"Permitted: {', '.join(view_data['permitted_actions'])}",
        },
        {
            "stage": "9. RECONCILIATION",
            "value": f"Lab: {rev:.2f} g/10m" if rev is not None else "Pending (Blind Window)",
            "detail": f"In-Spec: {view_data.get('was_in_spec')}" if rev is not None else "Withheld until result_at",
        },
        {
            "stage": "10. MEMORY",
            "value": "Append-Only Store",
            "detail": "No online learning / TRAIN-isolated",
        },
    ]


# ──────────────────────────────────────────────────────────────────────────
# 2. DECISION COCKPIT VIEW (Supports Demo, Replay, and Locked Validation)
# ──────────────────────────────────────────────────────────────────────────

def build_cockpit_view(
    rt: RuntimeContext,
    mode: str = ExecutionMode.ILLUSTRATIVE_DEMO.value,
    scenario_name: str = C.DEFAULT_SCENARIO,
    demo_step: str = "T3_PRIME_CANDIDATE",
    event_id: str = "EP-AB-00",
    step_idx: int = 18,
    sample_available: bool = True,
    fault_kind: str = "NONE",
    approval_status: str = ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value,
) -> Dict[str, Any]:
    """Build the unified Decision Cockpit view model for any selected mode."""
    if mode == ExecutionMode.ILLUSTRATIVE_DEMO.value:
        demo = build_demo_walkthrough(
            rt,
            scenario_name=scenario_name,
            selected_step=demo_step,
            approval_status=approval_status,
        )
        step = demo["active_step"]
        out = {
            "mode": mode,
            "mode_meta": MODE_META[mode],
            "event_id": demo["event_id"],
            "partition": "ILLUSTRATIVE_DEMO",
            "direction": demo["direction"],
            "unit": demo["unit"],
            "decision_time": step["decision_time"],
            "elapsed_min": step["t_min"],
            "action": step["action"],
            "action_meta": step["action_meta"],
            "reason_codes": step["reason_codes"],
            "prediction": step["prediction"],
            "spec_band": step["spec_band"],
            "dwell": step["dwell"],
            "material_window": step["material_window"],
            "gates": step["gates"],
            "hard_gates_passed": step["hard_gates_passed"],
            "hard_gates_total": step["hard_gates_total"],
            "candidacy_gates_passed": step["candidacy_gates_passed"],
            "candidacy_gates_total": step["candidacy_gates_total"],
            "health_state": step["health_state"],
            "health_findings": step["health_findings"],
            "applicability_state": step["applicability_state"],
            "permitted_actions": step["permitted_actions"],
            "economics": step["economics"],
            "approval_status": demo["approval_status"],
            "approver_role": C.POLICY.required_approver,
            "narrative": step["narrative"],
            "what_knew": step["what_knew"],
            "what_did_not_know": step["what_did_not_know"],
            "why_action_changed": step["why_action_changed"],
            "revealed_mfi": step["revealed_mfi"],
            "was_in_spec": step["was_in_spec"],
            "mfi_series": demo["mfi_series"],
            "h2_series": demo["h2_series"],
            "lab_points": demo["lab_points"],
            "demo_steps": demo["steps"],
            "locked_honest_explanation": LOCKED_HONEST_EXPLANATION,
            "versions": rt.versions,
            "fingerprints": rt.fingerprints,
        }
        out["five_jury_questions"] = _build_five_jury_questions(out, scenario_name)
        out["central_lineage_chain"] = _build_central_lineage_chain(out)
        return out

    # SYNTHETIC_REPLAY or LOCKED_VALIDATION on a real corpus event
    if mode == ExecutionMode.LOCKED_VALIDATION.value:
        locked_ids = [
            ev.event_id
            for ev in rt.corpus
            if rt.partitions[ev.event_id] is Partition.LOCKED_TEST
        ]
        if event_id not in locked_ids:
            event_id = locked_ids[0]
        fault_kind = "NONE"  # Never mutate locked validation events

    ev = rt.events_by_id.get(event_id, rt.corpus[0])
    part = rt.partitions[ev.event_id].value
    grid = rt.decision_grid(ev)
    idx = max(0, min(step_idx, len(grid) - 1))
    t = grid[idx]
    ctx, disp, econ = rt.evaluate_event_at(
        ev,
        t,
        scenario_name=scenario_name,
        sample_available=sample_available,
        fault_kind=fault_kind,
    )
    spec = C.get_grade(ev.grade_to)

    if disp.action == D.PRIME_RELEASE_CANDIDATE:
        eff_approval = (
            approval_status
            if approval_status != ApprovalStatus.NOT_APPLICABLE.value
            else ApprovalStatus.PENDING_HUMAN_AUTHORIZATION.value
        )
    else:
        eff_approval = ApprovalStatus.NOT_APPLICABLE.value

    aoe = ctx.as_of_event
    mfi_series = [
        {
            "t_min": (o.timestamp - ev.started_at).total_seconds() / 60.0,
            "timestamp": o.timestamp.isoformat(),
            "value": o.value,
        }
        for o in aoe.series
        if o.tag == "MFI_online"
    ]
    h2_series = [
        {
            "t_min": (o.timestamp - ev.started_at).total_seconds() / 60.0,
            "timestamp": o.timestamp.isoformat(),
            "value": o.value,
        }
        for o in aoe.series
        if o.tag == "H2_ratio"
    ]
    lab_points = [
        {
            "sample_id": l.sample_id,
            "collected_min": (l.collected_at - ev.started_at).total_seconds() / 60.0,
            "result_min": (l.result_at - ev.started_at).total_seconds() / 60.0,
            "mfi": l.mfi,
        }
        for l in aoe.labs
    ]

    mws = ctx.material_window_summary
    me = ctx.material_eligibility
    out = {
        "mode": mode,
        "mode_meta": MODE_META[mode],
        "event_id": ev.event_id,
        "partition": part,
        "direction": ev.direction,
        "unit": ev.unit,
        "decision_time": t.isoformat(),
        "elapsed_min": round(ctx.elapsed_min, 1),
        "step_idx": idx,
        "total_steps": len(grid),
        "action": disp.action,
        "action_meta": ACTION_META[disp.action],
        "reason_codes": list(disp.reason_codes),
        "prediction": {
            "point_mfi": round(ctx.prediction.point_mfi, 4),
            "lower_mfi": round(ctx.prediction.lower_mfi, 4),
            "upper_mfi": round(ctx.prediction.upper_mfi, 4),
            "width": round(ctx.prediction.upper_mfi - ctx.prediction.lower_mfi, 4),
            "nominal_coverage": ctx.prediction.nominal_coverage,
        },
        "spec_band": {
            "grade_id": spec.grade_id,
            "name": spec.name,
            "target_mfi": spec.target_mfi,
            "mfi_low": spec.mfi_low,
            "mfi_high": spec.mfi_high,
            "dwell_min": spec.dwell_min,
        },
        "dwell": disp.dwell_status.to_dict() if disp.dwell_status else {},
        "material_window": {
            "mapped_mass_tonnes": round(float(mws.get("mapped_mass_tonnes", 0.0)), 2),
            "recoverable_mass_tonnes": round(float(mws.get("mapped_mass_tonnes", 0.0)), 2),
            "mean_age_min": round(float(mws.get("mean_age_min", 0.0)), 1),
            "age_spread_min": 12.0,
            "residence_uncertainty_min": round(
                float(getattr(me, "residence_uncertainty_min", 0.0)), 1
            ),
            "primary_destination": str(mws.get("primary_destination", "SILO-DOWNGRADE")),
            "mapping_quality": str(mws.get("mapping_quality", "UNKNOWN")),
            "route_known": bool(mws.get("route_known", False)),
            "production_window": str(mws.get("production_time_start", "")),
        },
        "gates": [g.to_dict() for g in disp.gates],
        "hard_gates_passed": sum(
            1 for g in disp.gates if g.severity == D.Severity.BLOCK and g.passed
        ),
        "hard_gates_total": sum(
            1 for g in disp.gates if g.severity == D.Severity.BLOCK
        ),
        "candidacy_gates_passed": sum(
            1 for g in disp.gates if g.severity == D.Severity.CANDIDACY and g.passed
        ),
        "candidacy_gates_total": sum(
            1 for g in disp.gates if g.severity == D.Severity.CANDIDACY
        ),
        "health_state": disp.health_state or "UNKNOWN",
        "health_findings": [f.to_dict() for f in ctx.health_report.findings],
        "applicability_state": disp.applicability_state or "UNKNOWN",
        "permitted_actions": list(econ.permitted_actions),
        "economics": econ.to_ledger(),
        "approval_status": eff_approval,
        "approver_role": disp.approver_role,
        "narrative": disp.note,
        "what_knew": (
            f"Causal as-of slice at t+{int(ctx.elapsed_min)}m: "
            f"{len(ctx.snapshot.observations)} sensor observations, "
            f"{len(ctx.snapshot.lab_results)} completed labs."
        ),
        "what_did_not_know": (
            "Future laboratory grab-sample results (result_at > t) and post-t trajectory "
            "are strictly withheld by the structural as-of causal firewall."
        ),
        "why_action_changed": (
            f"Evaluated at step {idx} (t+{int(ctx.elapsed_min)}m): "
            f"Hard gates {sum(1 for g in disp.gates if g.severity == D.Severity.BLOCK and g.passed)}/"
            f"{sum(1 for g in disp.gates if g.severity == D.Severity.BLOCK)} PASS → {disp.action} "
            f"({', '.join(disp.reason_codes)})."
        ),
        # Pre-reconciliation decision cockpit never leaks future truth
        "revealed_mfi": None,
        "was_in_spec": None,
        "mfi_series": mfi_series,
        "h2_series": h2_series,
        "lab_points": lab_points,
        "demo_steps": [],
        "locked_honest_explanation": LOCKED_HONEST_EXPLANATION,
        "versions": rt.versions,
        "fingerprints": rt.fingerprints,
    }
    out["five_jury_questions"] = _build_five_jury_questions(out, scenario_name)
    out["central_lineage_chain"] = _build_central_lineage_chain(out)
    return out


LOCKED_HONEST_EXPLANATION: Dict[str, Any] = {
    "headline": (
        "100% abstention is not commercial success. "
        "It is evidence that the current model refuses unsupported transitions."
    ),
    "why_blocked": (
        "Chronological event partitioning placed directions A→B, A→C, B→A, C→A in TRAIN (10 episodes), "
        "while LOCKED_TEST (5 episodes, 235 decision rows) comprises unseen directions B→C and C→B. "
        "The train-only ApplicabilityDetector flags all 235 locked rows as UNSUPPORTED (ood hard gate), "
        "and 40 rows additionally fail material_mapping."
    ),
    "reasons": [
        "Prevents unsupported prime candidacy on transition directions (B→C, C→B) absent from the chronological training split.",
        "Exposes the exact applicability boundary via the train-only OOD detector (235/235 locked rows blocked by ood gate; 40/235 additionally blocked by material_mapping).",
        "Creates a clear, auditable engineering path for future data collection (expanding directional training and multi-episode calibration before enabling prime candidacy on new grade pairs).",
        "Demonstrates that quality and applicability policy gates strictly dominate economic upside (0.0 t false-prime mass vs 1,356.0 t for SOP_FIXTURE and 588.0 t for POINT_THRESHOLD, at an explicit 984.0 t false-hold opportunity cost).",
    ],
    "evidence_types": {
        "observed_frozen": (
            "Observed / Frozen Validation Evidence (LOCKED_VALIDATION — 5 unseen test episodes, "
            "235 decisions, frozen SHA-256 artifacts, E2/E3 ceiling)"
        ),
        "diagnostic_oracle": (
            "Diagnostic Oracle Evidence (ORACLE_DIAGNOSTIC_ONLY — non-causal hindsight benchmark "
            "using future laboratory truth; never deployable as a live policy)"
        ),
        "simulated_illustrative": (
            "Simulated / Illustrative Evidence (ILLUSTRATIVE_DEMO — controlled in-domain A→B walkthrough "
            "demonstrating HOLD → SAMPLE NOW → PRIME-RELEASE CANDIDATE → RECONCILED → ABSTAIN)"
        ),
    },
}


# ──────────────────────────────────────────────────────────────────────────
# 3. PAGE 1 — TRANSITION REPLAY VIEW (`build_replay_view`)
# ──────────────────────────────────────────────────────────────────────────

def build_replay_view(
    rt: RuntimeContext,
    event_id: str = "EP-AB-00",
    scenario_name: str = C.DEFAULT_SCENARIO,
    step_idx: int = 18,
    reveal_future_truth: bool = False,
) -> Dict[str, Any]:
    """Replay a selected transition episode across all 4 policies under the
    structural as-of firewall and return timeline series + comparison metrics.
    """
    ev = rt.events_by_id.get(event_id, rt.corpus[0])
    ep = rt.get_replay_episode(ev.event_id, scenario_name=scenario_name)
    spec = C.get_grade(ev.grade_to)
    comp = R.build_comparison_table(ep)

    n_steps = len(ep.decision_times)
    idx = max(0, min(step_idx, n_steps - 1))
    current_dt = ep.decision_times[idx]
    raw_trace = dict(R.event_trace(ep, policy=R.PRIMEPATH, step=idx))
    if not reveal_future_truth:
        raw_trace["later_truth"] = {
            "revealed_mfi": None,
            "was_in_spec": None,
            "actual_route": None,
            "note": "Withheld by structural as-of causal firewall prior to reconciliation.",
        }
        raw_trace["outcome"] = {
            "false_prime_tonnes": None,
            "false_hold_tonnes": None,
            "true_prime_tonnes": None,
            "note": "Withheld by structural as-of causal firewall prior to reconciliation.",
        }
    trace = raw_trace

    # Timeline rows across all steps
    timeline_rows: List[Dict[str, Any]] = []
    for i, dt in enumerate(ep.decision_times):
        ctx = ep.contexts[i]
        truth = ep.truths[i]
        row: Dict[str, Any] = {
            "step": i,
            "elapsed_min": round(ctx.elapsed_min, 1),
            "decision_time": dt.isoformat(),
            "point_mfi": round(ctx.prediction.point_mfi, 4) if ctx.prediction else None,
            "lower_mfi": round(ctx.prediction.lower_mfi, 4) if ctx.prediction else None,
            "upper_mfi": round(ctx.prediction.upper_mfi, 4) if ctx.prediction else None,
            "mapped_mass_tonnes": round(
                float(ctx.material_window_summary.get("mapped_mass_tonnes", 0.0)), 2
            ),
            "health_state": ctx.health_report.overall_state.name,
            "applicability_state": ctx.applicability_result.state.name,
            "SOP_FIXTURE": ep.decisions[R.SOP][i].action,
            "POINT_THRESHOLD": ep.decisions[R.POINT_THRESHOLD][i].action,
            "PRIMEPATH": ep.decisions[R.PRIMEPATH][i].action,
            "ORACLE_DIAGNOSTIC_ONLY": ep.decisions[R.ORACLE][i].action,
            "revealed_mfi": truth.get("revealed_mfi") if reveal_future_truth else None,
            "was_in_spec": truth.get("was_in_spec") if reveal_future_truth else None,
        }
        timeline_rows.append(row)

    # Lab blind spots: intervals between sample collection and result arrival
    # Mask future lab MFI values when reveal_future_truth is False and result_at > current_dt
    lab_windows = [
        {
            "sample_id": l.sample_id,
            "collected_min": round((l.collected_at - ev.started_at).total_seconds() / 60.0, 1),
            "result_min": round((l.result_at - ev.started_at).total_seconds() / 60.0, 1),
            "latency_min": round(l.latency_min, 1),
            "known_as_of_step": l.result_at <= current_dt,
            "mfi": round(l.mfi, 4) if (reveal_future_truth or l.result_at <= current_dt) else None,
        }
        for l in ev.labs
    ]

    return {
        "event_id": ev.event_id,
        "partition": ep.partition,
        "direction": ev.direction,
        "unit": ev.unit,
        "spec": {
            "grade_id": spec.grade_id,
            "name": spec.name,
            "target_mfi": spec.target_mfi,
            "mfi_low": spec.mfi_low,
            "mfi_high": spec.mfi_high,
        },
        "step_idx": idx,
        "n_steps": n_steps,
        "reveal_future_truth": reveal_future_truth,
        "timeline": timeline_rows,
        "comparison_table": comp["rows"],
        "oracle_label": comp["oracle_label"],
        "step_trace": trace,
        "lab_windows": lab_windows,
        "locked_summary": rt.phase12_report.get("locked_evaluation", {}),
        "firewall_info": rt.phase12_report.get("future_truth_firewall", {}),
        "locked_honest_explanation": LOCKED_HONEST_EXPLANATION,
    }


# ──────────────────────────────────────────────────────────────────────────
# 4. PAGE 2 — QUALITY EVIDENCE VIEW (`build_quality_view`)
# ──────────────────────────────────────────────────────────────────────────

def build_quality_view(
    rt: RuntimeContext,
    event_id: str = "EP-AB-00",
) -> Dict[str, Any]:
    """Return real GBM point predictions + split-conformal intervals + delayed
    laboratory reconciliation + Phase 5/6 evaluation metrics (zero mock noise).
    """
    ev = rt.events_by_id.get(event_id, rt.corpus[0])
    ep = rt.get_replay_episode(ev.event_id)
    spec = C.get_grade(ev.grade_to)

    trajectory: List[Dict[str, Any]] = []
    for i, ctx in enumerate(ep.contexts):
        truth = ep.truths[i]
        online_obs = [
            o.value for o in ctx.as_of_event.series if o.tag == "MFI_online"
        ]
        known_labs = ctx.snapshot.lab_results
        trajectory.append(
            {
                "step": i,
                "elapsed_min": round(ctx.elapsed_min, 1),
                "decision_time": ctx.decision_time.isoformat(),
                "online_analyzer_mfi": round(online_obs[-1], 4) if online_obs else None,
                "last_known_lab_mfi": round(known_labs[-1].mfi, 4) if known_labs else None,
                "gbm_point_mfi": round(ctx.prediction.point_mfi, 4),
                "conformal_lower_mfi": round(ctx.prediction.lower_mfi, 4),
                "conformal_upper_mfi": round(ctx.prediction.upper_mfi, 4),
                "interval_width": round(
                    ctx.prediction.upper_mfi - ctx.prediction.lower_mfi, 4
                ),
                "later_lab_truth_mfi": round(float(truth["revealed_mfi"]), 4)
                if truth.get("revealed_mfi") is not None
                else None,
                "point_in_spec": spec.in_spec(ctx.prediction.point_mfi),
                "interval_in_spec": (
                    ctx.prediction.lower_mfi >= spec.mfi_low
                    and ctx.prediction.upper_mfi <= spec.mfi_high
                ),
            }
        )

    p5_locked = rt.phase5_metrics.get("metrics", {}).get("LOCKED_TEST", {})
    p5_calib = rt.phase5_metrics.get("metrics", {}).get("CALIBRATION", {})
    model_comparison = []
    for model_key, label in [
        ("last_lab", "Last-Lab Baseline (Naive Hold)"),
        ("deterministic_online", "Deterministic Online Analyzer"),
        ("linear_process", "Linear Process Baseline (Ridge)"),
        ("gbm", "PrimePath HistGBM Estimator (gbm-mfi-v1)"),
    ]:
        cal_m = p5_calib.get(model_key, {}).get("overall", {})
        loc_m = p5_locked.get(model_key, {}).get("overall", {})
        model_comparison.append(
            {
                "model_key": model_key,
                "model_label": label,
                "calib_mae": cal_m.get("mae"),
                "calib_rmse": cal_m.get("rmse"),
                "locked_mae": loc_m.get("mae"),
                "locked_rmse": loc_m.get("rmse"),
                "locked_bias": loc_m.get("bias"),
            }
        )

    gbm_cal_info = rt.phase6_metrics.get("estimators", {}).get("gbm", {})

    return {
        "event_id": ev.event_id,
        "partition": rt.partitions[ev.event_id].value,
        "direction": ev.direction,
        "spec": {
            "grade_id": spec.grade_id,
            "name": spec.name,
            "target_mfi": spec.target_mfi,
            "mfi_low": spec.mfi_low,
            "mfi_high": spec.mfi_high,
        },
        "trajectory": trajectory,
        "model_comparison": model_comparison,
        "conformal_summary": {
            "chosen_method": gbm_cal_info.get("chosen_method", "marginal_symmetric"),
            "nominal_coverage": rt.phase6_metrics.get("nominal_coverage", 0.90),
            "calibration_rows": rt.phase6_metrics.get("calibration_rows", 141),
            "calibration_events": rt.phase6_metrics.get("calibration_events", 3),
            "half_width_mfi": gbm_cal_info.get("calibrator_manifest", {})
            .get("marginal", {})
            .get("lo", 0.2369),
            "locked_overall": gbm_cal_info.get("locked_overall", {}),
            "locked_by_phase": gbm_cal_info.get("locked_by_phase", {}),
            "locked_by_direction": gbm_cal_info.get("locked_by_direction", {}),
            "calibration_coverage_by_method": gbm_cal_info.get(
                "calibration_coverage_by_method", {}
            ),
            "spec_crossing_examples": gbm_cal_info.get("spec_crossing_examples", []),
        },
        "feature_schema": rt.phase5_manifest.get("feature_schema", []),
        "largest_residuals": rt.phase5_metrics.get("largest_residuals_locked_gbm", []),
    }


# ──────────────────────────────────────────────────────────────────────────
# 5. PAGE 3 — DISPOSITION WORKBENCH VIEW (`build_disposition_view`)
# ──────────────────────────────────────────────────────────────────────────

def build_disposition_view(
    rt: RuntimeContext,
    scenario_name: str = C.DEFAULT_SCENARIO,
    grade_to: str = "B",
    lower_mfi: float = 7.70,
    upper_mfi: float = 8.30,
    dwell_elapsed_min: float = 45.0,
    sample_available: bool = True,
    mapping_quality: str = "WELL_SUPPORTED",
    residence_uncertainty_min: float = 10.0,
    health_state: str = "NORMAL",
    applicability_state: str = "NORMAL",
    mass_tonnes: float = 50.0,
    recommendation_age_min: float = 5.0,
) -> Dict[str, Any]:
    """Interactive Disposition Workbench calling the real `evaluate_disposition`
    and `evaluate_economics` engines on operator-configured or preset evidence.
    """
    base_time = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ev = generate_episode("WORKBENCH-TX", "A", grade_to, seed=4242, start_time=base_time)
    spec = C.get_grade(grade_to)
    sc = C.get_scenario(scenario_name)
    dt = base_time + timedelta(minutes=400)
    now = dt + timedelta(minutes=recommendation_age_min)

    point_mfi = round((lower_mfi + upper_mfi) / 2.0, 4)
    pred = PredictionBundle(
        event_id=ev.event_id,
        decision_time=dt,
        point_mfi=point_mfi,
        lower_mfi=lower_mfi,
        upper_mfi=upper_mfi,
        nominal_coverage=0.90,
        prob_bad=0.15 if (lower_mfi < spec.mfi_low or upper_mfi > spec.mfi_high) else 0.02,
        model_version=rt.gbm.model_version,
        calibration_version=f"{rt.calibrator.calibration_version}:{rt.calibrator.method}",
    )

    mq_enum = MappingQuality(mapping_quality)
    is_blocking_mat = mq_enum is MappingQuality.UNAVAILABLE
    route_known = mq_enum in (
        MappingQuality.WELL_SUPPORTED,
        MappingQuality.PARTIALLY_SUPPORTED,
    )
    mat_elig = MaterialEligibilityResult(
        material_window_available=(mq_enum is not MappingQuality.UNAVAILABLE),
        mapping_quality=mq_enum,
        route_known=route_known,
        mass_reconciled=not is_blocking_mat,
        residence_uncertainty_min=residence_uncertainty_min,
        route_ambiguity=0.0 if route_known else 0.35,
        blocking_reason_codes=("MATERIAL_UNAVAILABLE",) if is_blocking_mat else (),
        reason_codes=(f"MAPPING_{mapping_quality}",),
        provenance=Provenance.SIMULATED,
        service_version=MATERIAL_SERVICE_VERSION,
    )

    hs_enum = HealthState[health_state]
    hr = SensorHealthReport(
        as_of=dt,
        overall_state=hs_enum,
        required_available=(hs_enum is not HealthState.UNAVAILABLE),
        signal_states={
            "MFI_online": hs_enum,
            "H2_ratio": HealthState.NORMAL,
            "bed_temp": HealthState.NORMAL,
        },
        findings=(),
        rule_version="health-v1",
        provenance=Provenance.SIMULATED,
    )

    ap_enum = ApplicabilityState[applicability_state]
    ap = ApplicabilityResult(
        state=ap_enum,
        score=0.12 if ap_enum is ApplicabilityState.NORMAL else -0.35,
        reason_codes=("IN_DOMAIN",) if ap_enum is ApplicabilityState.NORMAL else (f"STATE_{applicability_state}",),
        detail={"state": applicability_state},
        feature_version="feat-v1",
        detector_version=rt.detector.detector_version,
        applicability_version="applicability-v1",
        provenance=Provenance.SIMULATED,
    )

    dwell = D.DwellStatus(
        required_min=spec.dwell_min,
        elapsed_min=dwell_elapsed_min,
        satisfied=(dwell_elapsed_min >= spec.dwell_min and spec.in_spec(point_mfi)),
        in_spec_now=spec.in_spec(point_mfi),
        as_of=dt,
    )

    evid = D.DispositionEvidence(
        event=ev,
        decision_time=dt,
        spec=spec,
        prediction=pred,
        material_eligibility=mat_elig,
        health_report=hr,
        applicability_result=ap,
        dwell_status=dwell,
        sample_available=sample_available,
        versions=rt.versions,
        current_time=now,
    )
    disp = D.evaluate_disposition(evid)
    econ_in = E.EconomicInputs(
        event_id=ev.event_id,
        decision_id="WORKBENCH-EVAL",
        mass_tonnes=mass_tonnes,
        recoverable_mass_tonnes=mass_tonnes,
        actual_route_value_per_tonne=float(sc.downgrade_price),
        scenario=sc,
    )
    econ = E.evaluate_economics(disp, econ_in)

    return {
        "action": disp.action,
        "action_meta": ACTION_META[disp.action],
        "fallback_action": disp.fallback_action,
        "reason_codes": list(disp.reason_codes),
        "note": disp.note,
        "expired": disp.expired,
        "approver_role": disp.approver_role,
        "prediction": {
            "point_mfi": point_mfi,
            "lower_mfi": lower_mfi,
            "upper_mfi": upper_mfi,
            "width": round(upper_mfi - lower_mfi, 4),
        },
        "spec": {
            "grade_id": spec.grade_id,
            "name": spec.name,
            "target_mfi": spec.target_mfi,
            "mfi_low": spec.mfi_low,
            "mfi_high": spec.mfi_high,
            "dwell_min": spec.dwell_min,
        },
        "gates": [g.to_dict() for g in disp.gates],
        "hard_gates": [
            g.to_dict() for g in disp.gates if g.severity == D.Severity.BLOCK
        ],
        "candidacy_gates": [
            g.to_dict() for g in disp.gates if g.severity == D.Severity.CANDIDACY
        ],
        "sample_eligibility": disp.sample_eligibility.to_dict(),
        "permitted_actions": list(econ.permitted_actions),
        "economic_preferred_action": econ.economic_preferred_action,
        "economics_ledger": econ.to_ledger(),
        "canonical_scenarios": rt.phase9_report.get("canonical_scenarios", []),
    }


# ──────────────────────────────────────────────────────────────────────────
# 6. PAGE 4 — TRANSITION GUARDIAN VIEW (`build_guardian_view`)
# ──────────────────────────────────────────────────────────────────────────

def build_guardian_view(
    rt: RuntimeContext,
    event_id: str = "EP-AB-00",
    step_idx: int = 18,
    fault_kind: str = "NONE",
) -> Dict[str, Any]:
    """Evaluate sensor health checks, fault injection, OOD applicability,
    13 hard gates, 11-scenario robustness matrix, and locked abstention decomposition.
    """
    ev = rt.events_by_id.get(event_id, rt.corpus[0])
    grid = rt.decision_grid(ev)
    idx = max(0, min(step_idx, len(grid) - 1))
    t = grid[idx]

    ctx, disp, _ = rt.evaluate_event_at(
        ev,
        t,
        sample_available=True,
        fault_kind=fault_kind,
    )
    hr = ctx.health_report
    ap = ctx.applicability_result

    signal_table = [
        {
            "tag": tag,
            "state": state.name,
            "is_blocking": state in (HealthState.ABNORMAL, HealthState.UNAVAILABLE),
        }
        for tag, state in hr.signal_states.items()
    ]

    findings_table = [f.to_dict() for f in hr.findings]
    robustness = rt.final_validation.get("robustness_matrix", {}) or V.robustness_matrix()
    abstention_decomp = rt.final_validation.get("abstention_decomposition", {})

    return {
        "event_id": ev.event_id,
        "partition": rt.partitions[ev.event_id].value,
        "direction": ev.direction,
        "unit": ev.unit,
        "decision_time": t.isoformat(),
        "fault_kind": fault_kind,
        "resulting_action": disp.action,
        "action_meta": ACTION_META[disp.action],
        "reason_codes": list(disp.reason_codes),
        "health_overall": hr.overall_state.name,
        "health_is_blocking": hr.is_blocking,
        "signal_table": signal_table,
        "findings_table": findings_table,
        "applicability": {
            "state": ap.state.name,
            "score": round(float(ap.score), 4),
            "is_blocking": ap.is_blocking,
            "reason_codes": list(ap.reason_codes),
            "detail": dict(ap.detail) if isinstance(ap.detail, dict) else {"info": str(ap.detail)},
        },
        "gates": [g.to_dict() for g in disp.gates],
        "robustness_matrix": robustness,
        "abstention_decomposition": abstention_decomp,
        "locked_honest_explanation": LOCKED_HONEST_EXPLANATION,
        "phase7_summary": rt.phase7_report,
    }


# ──────────────────────────────────────────────────────────────────────────
# 7. PAGE 5 — ECONOMIC LEDGER VIEW (`build_economic_view`)
# ──────────────────────────────────────────────────────────────────────────

def build_economic_view(
    rt: RuntimeContext,
    scenario_name: str = C.DEFAULT_SCENARIO,
    mass_tonnes: float = 50.0,
    recoverable_mass_tonnes: float = 50.0,
    eligible_transitions_per_year: float = 50.0,
    availability: float = 0.90,
    adoption: float = 0.50,
    episode_value_override: Optional[float] = None,
) -> Dict[str, Any]:
    """Build the Phase-10 Economic Ledger view across LOW/BASE/HIGH scenarios,
    showing Demo T3/T5 reconciliation, Locked Validation replay economics, and
    the parameterized annual scenario scale-up calculator.
    """
    sc = C.get_scenario(scenario_name)
    demo = build_demo_walkthrough(
        rt, scenario_name=scenario_name, selected_step="T5_ECONOMIC_LEDGER"
    )
    demo_step = demo["active_step"]
    disp_t3 = demo_step["disposition_result"]

    # Re-evaluate Demo T3/T5 with user-selected mass & scenario
    rec_mass = min(mass_tonnes, recoverable_mass_tonnes)
    econ_in = E.EconomicInputs(
        event_id="DEMO-A2B",
        decision_id="LEDGER-EVAL",
        mass_tonnes=mass_tonnes,
        recoverable_mass_tonnes=rec_mass,
        actual_route_value_per_tonne=float(sc.downgrade_price),
        scenario=sc,
    )
    econ_good = E.evaluate_economics(disp_t3, econ_in, realized_good=True)
    sanity = V.economic_sanity(econ_good)

    # Compare across LOW / BASE / HIGH for the same decision
    scenario_comparison = []
    for s_name, s_obj in C.ECON_SCENARIOS.items():
        s_in = E.EconomicInputs(
            event_id="DEMO-A2B",
            decision_id=f"LEDGER-{s_name}",
            mass_tonnes=mass_tonnes,
            recoverable_mass_tonnes=rec_mass,
            actual_route_value_per_tonne=float(s_obj.downgrade_price),
            scenario=s_obj,
        )
        s_res = E.evaluate_economics(disp_t3, s_in, realized_good=True)
        scenario_comparison.append(
            {
                "scenario": s_name,
                "prime_price_per_t": s_obj.prime_price,
                "downgrade_price_per_t": s_obj.downgrade_price,
                "spread_per_t": s_obj.downgrade_spread,
                "false_prime_consequence_per_t": s_obj.false_prime_consequence,
                "sample_cost": s_obj.sample_cost,
                "workflow_cost": s_obj.workflow_cost,
                "counterfactual_opportunity_currency": s_res.value_split.counterfactual_opportunity_currency,
                "realized_downgrade_value_currency": s_res.value_split.realized_value_currency,
                "counterfactual_prime_value_currency": s_res.value_split.counterfactual_prime_value_currency,
            }
        )

    ep_val = (
        episode_value_override
        if episode_value_override is not None
        else econ_good.value_split.counterfactual_opportunity_currency
    )
    annual = E.scale_up_annual(
        validated_episode_value_currency=ep_val,
        eligible_transitions_per_year=eligible_transitions_per_year,
        availability=availability,
        adoption=adoption,
        scenario=scenario_name,
    )

    vs = econ_good.value_split
    how_constructed = [
        {
            "metric": "REALIZED VALUE (Current Plant Routing)",
            "category": "REALIZED VALUE",
            "formula": "mapped_mass_tonnes × actual_route_value_per_tonne (downgrade_price)",
            "inputs": f"{mass_tonnes:.1f} t × ₹{sc.downgrade_price:,.0f}/t",
            "value_currency": vs.realized_value_currency,
            "evidence_class": "E0 / E2 (Simulated Mass × Assumption Price)",
            "explanation": (
                "Baseline revenue of transitional material routed to the wide-spec/downgrade silo "
                "prior to prime disposition authorization."
            ),
        },
        {
            "metric": "COUNTERFACTUAL PRIME VALUE (Reconciled In-Spec Lot)",
            "category": "COUNTERFACTUAL VALUE",
            "formula": "recoverable_mass_tonnes × prime_price + unrecoverable_mass × downgrade_price − workflow_cost",
            "inputs": f"{rec_mass:.1f} t × ₹{sc.prime_price:,.0f}/t − ₹{sc.workflow_cost:,.0f}",
            "value_currency": vs.counterfactual_prime_value_currency,
            "evidence_class": "E2 (Counterfactual Simulation after Delayed Lab Reconciliation)",
            "explanation": (
                "Value of the mapped downstream pellet window if routed to prime silo after "
                "Shift Quality Approver (QC) authorization and confirmed in-spec by delayed laboratory truth."
            ),
        },
        {
            "metric": "COUNTERFACTUAL OPPORTUNITY VALUE (Net Episode Uplift)",
            "category": "COUNTERFACTUAL VALUE",
            "formula": "recoverable_mass_tonnes × (prime_price − downgrade_price) − workflow_cost",
            "inputs": f"{rec_mass:.1f} t × ₹{sc.downgrade_spread:,.0f}/t − ₹{sc.workflow_cost:,.0f}",
            "value_currency": vs.counterfactual_opportunity_currency,
            "evidence_class": "E0 / E2 (Illustrative Scenario — Not Realized HMEL Savings)",
            "explanation": (
                "Incremental commercial spread between prime and downgrade routing on a single reconciled "
                "in-spec window. Explicitly separated from realized plant accounting."
            ),
        },
        {
            "metric": "FALSE-PRIME EXPOSURE (Prevented Contamination Consequence)",
            "category": "COUNTERFACTUAL VALUE",
            "formula": "false_prime_mass_tonnes × false_prime_consequence_per_t",
            "inputs": f"0.0 t (PrimePath) vs 1,356.0 t (SOP) × ₹{sc.false_prime_consequence:,.0f}/t",
            "value_currency": 0.0,
            "evidence_class": "E2 / E3 (Frozen Locked Validation Replay)",
            "explanation": (
                "Customer claim / silo blending penalty incurred when off-spec polymer is falsely "
                "released as prime. PrimePath achieves 0.0 t false-prime mass on locked test episodes."
            ),
        },
        {
            "metric": "ANNUAL SCENARIO SCALE-UP (Parameterized Plant Projection)",
            "category": "ILLUSTRATIVE SCENARIO",
            "formula": "episode_opportunity × eligible_transitions_per_year × availability × adoption",
            "inputs": (
                f"₹{ep_val:,.0f} × {eligible_transitions_per_year:.0f} tx/yr "
                f"× {availability:.0%} avail × {adoption:.0%} adoption"
            ),
            "value_currency": annual.annual_value_currency,
            "evidence_class": "E0 (Assumption-Based Scenario Projection — Not an HMEL Savings Claim)",
            "explanation": (
                "Parameterized sensitivity projection showing how single-episode counterfactual value "
                "scales with transition frequency, analyzer availability, and QC adoption."
            ),
        },
    ]

    return {
        "scenario": sc,
        "scenario_comparison": scenario_comparison,
        "active_ledger": econ_good.to_ledger(),
        "sanity_checks": sanity,
        "annual_scale_up": annual.to_dict(),
        "economic_framing": {
            "badges": [
                "Illustrative scenario",
                "Assumption-based economics (E0/E2)",
                "Not an HMEL savings claim",
            ],
            "realized_vs_counterfactual_note": (
                "PrimePath strictly separates REALIZED VALUE (actual downgrade routing), "
                "COUNTERFACTUAL VALUE (simulated prime uplift after delayed laboratory truth reconciliation), "
                "and ILLUSTRATIVE SCENARIO projections (parameterized annual scale-up). "
                "No figure in this ledger represents measured or audited HMEL Bathinda plant savings."
            ),
        },
        "how_constructed": how_constructed,
        "locked_level_b": rt.final_validation.get("level_b_decision", {}),
        "locked_level_c": rt.final_validation.get("level_c_economic", {}),
        "diagnostic_sensitivity": rt.final_validation.get("diagnostic_sensitivity", {}),
        "canonical_scenarios": rt.phase10_report.get("canonical_economic_scenarios", []),
    }


# ──────────────────────────────────────────────────────────────────────────
# 8. PAGE 6 — TRANSITION MEMORY & MODEL ASSURANCE (`build_memory_assurance_view`)
# ──────────────────────────────────────────────────────────────────────────

def build_memory_assurance_view(
    rt: RuntimeContext,
    query_event_id: str = "DEMO-A2B",
    k: int = 3,
    unit_policy: str = M.UnitPolicy.PREFER_SAME_UNIT.value,
) -> Dict[str, Any]:
    """Retrieve k directional analogs from the immutable `TransitionMemoryStore`
    with explicit scope-isolation proofs, plus Phase-13 validation & claim ledger.
    """
    rec = rt.memory_store.latest(query_event_id)
    effective_query_id = query_event_id
    if rec is None:
        rec = rt.memory_store.latest("EP-AB-00") or rt.memory_store.all_latest()[0]

    q_ctx = M.RetrievalContext.from_record(rec)
    # Give query a late timestamp so reconciled TRAIN records are visible as-of query
    q_ctx = M.RetrievalContext(
        event_id=effective_query_id,
        direction=q_ctx.direction,
        grade_from=q_ctx.grade_from,
        grade_to=q_ctx.grade_to,
        unit=q_ctx.unit,
        phase=q_ctx.phase,
        process_context=q_ctx.process_context,
        material_window_summary=q_ctx.material_window_summary,
        feature_summary=q_ctx.feature_summary,
        decision_time=datetime(2026, 12, 31, tzinfo=timezone.utc),
    )
    scope = M.MemoryScope(
        direction=rec.direction,
        allowed_partition=Partition.TRAIN,
        excluded_event_ids=frozenset({effective_query_id}),
        unit=rec.unit,
        unit_policy=M.UnitPolicy(unit_policy),
        require_reconciled=True,
        require_eligible=True,
    )
    analogs = M.retrieve_transition_memory(q_ctx, scope, k=k, store=rt.memory_store)

    all_records = [r.to_dict() for r in rt.memory_store.all_latest()]
    opposite_dir = f"{rec.grade_to}->{rec.grade_from}"
    opp_ids = [r["event_id"] for r in all_records if r["direction"] == opposite_dir]
    locked_ids = [
        r["event_id"] for r in all_records if r["partition"] == Partition.LOCKED_TEST.value
    ]
    retrieved_ids = [a.event_id for a in analogs]

    return {
        "assurance_statement": (
            "Historical context is retrieved for auditability. "
            "It is not silently used to retrain the locked evaluation."
        ),
        "store_stats": rt.memory_store.statistics(),
        "query_record": rec.to_dict(),
        "scope": scope.to_dict(),
        "analogs": [a.to_dict() for a in analogs],
        "exclusion_proof": {
            "query_event_id": effective_query_id,
            "query_direction": rec.direction,
            "opposite_direction": opposite_dir,
            "opposite_direction_events_in_store": opp_ids,
            "locked_test_events_in_store": locked_ids,
            "retrieved_event_ids": retrieved_ids,
            "self_excluded": effective_query_id not in retrieved_ids,
            "opposite_direction_excluded": all(eid not in opp_ids for eid in retrieved_ids),
            "locked_test_excluded": all(eid not in locked_ids for eid in retrieved_ids),
            "online_learning_disabled": True,
        },
        "all_records": all_records,
        "claim_ledger": rt.final_validation.get("claim_ledger", []),
        "evidence_ladder": rt.final_validation.get("evidence_ladder", {}),
        "pass_fail_criteria": rt.final_validation.get("pass_fail_criteria", {}),
        "fingerprints": rt.fingerprints,
        "versions": rt.versions,
        "limitations": rt.final_validation.get("limitations", []),
        "locked_honest_explanation": LOCKED_HONEST_EXPLANATION,
    }


# ──────────────────────────────────────────────────────────────────────────
# 9. EXECUTIVE VALUE VIEW (`build_executive_view`)
# ──────────────────────────────────────────────────────────────────────────

def build_executive_view(
    rt: RuntimeContext,
    scenario_name: str = C.DEFAULT_SCENARIO,
) -> Dict[str, Any]:
    """Synthesize the 30-second executive summary comparing SOP, Point-Only,
    and PrimePath across both the Illustrative Demo and Locked Validation.
    """
    sc = C.get_scenario(scenario_name)
    demo = build_demo_walkthrough(rt, scenario_name=scenario_name)
    lv = rt.final_validation

    return {
        "product_definition": (
            "An uncertainty-aware, human-authorized commercial-disposition "
            "decision layer for polyolefin grade transitions."
        ),
        "tagline": "Know when it is a prime-release candidate. Prove why. Learn every transition.",
        "problem_statement": (
            "During polyolefin grade transitions, laboratory MFI confirmation lags reactor "
            "production by 45–75 minutes while pelletizer output flows at ~50 t/h. Fixed-time "
            "SOP routing either downgrades good prime polymer (false hold) or risks shipping "
            "off-spec transition material as prime (false prime)."
        ),
        "why_point_fails": (
            "A point-only soft sensor cannot tell whether an in-spec point prediction (e.g., "
            "7.90 g/10min) has a wide uncertainty tail crossing the specification boundary "
            "([7.50, 8.30] vs [7.60, 8.40]) or whether the transition direction is out-of-domain."
        ),
        "how_primepath_works": [
            "1. Causal As-Of Firewall & Residence-Time Material Window Mapping",
            "2. HistGBM Point Estimator (gbm-mfi-v1) + Split-Conformal 90% Interval (split-conformal-v1)",
            "3. 7-Check Sensor Health Guardian + Train-Only OOD Applicability Detector",
            "4. 13 Hard Policy Gates Evaluated FIRST (Block -> ABSTAIN / FOLLOW SOP)",
            "5. Expected Loss & Discrete VOI Ranking Over Permitted Actions Only",
            "6. Mandatory Human / Shift Quality Approver (QC) Authorization",
        ],
        "illustrative_demo_summary": {
            "label": "ILLUSTRATIVE DEMO (DEMO-A2B, Controlled A→B Walkthrough)",
            "steps": [
                {
                    "step": s["step_id"],
                    "t_min": s["t_min"],
                    "action": s["action"],
                    "interval": f"[{s['prediction']['lower_mfi']:.2f}, {s['prediction']['upper_mfi']:.2f}]",
                    "narrative": s["narrative"],
                    "why_action_changed": s["why_action_changed"],
                }
                for s in demo["steps"]
            ],
            "episode_mass_tonnes": 50.0,
            "scenario_spread_per_tonne": sc.downgrade_spread,
            "counterfactual_opportunity_currency": 50.0 * sc.downgrade_spread,
        },
        "locked_validation_summary": {
            "label": "LOCKED VALIDATION (5 Unseen Test Episodes, 235 Decisions)",
            "level_a_quality": lv.get("level_a_quality", {}),
            "level_b_decision": lv.get("level_b_decision", {}),
            "level_c_economic": lv.get("level_c_economic", {}),
            "abstention_decomposition": lv.get("abstention_decomposition", {}),
            "zero_candidate_diagnostic": lv.get("zero_candidate_diagnostic", {}),
        },
        "locked_honest_explanation": LOCKED_HONEST_EXPLANATION,
        "versions": rt.versions,
        "fingerprints": rt.fingerprints,
    }


# ──────────────────────────────────────────────────────────────────────────
# 10. LOCKED VALIDATION INSPECTOR (`build_locked_validation_view`)
# ──────────────────────────────────────────────────────────────────────────

def build_locked_validation_view(rt: RuntimeContext) -> Dict[str, Any]:
    """Return the complete, read-only Phase-13 frozen validation package."""
    lv = rt.final_validation
    return {
        "mode": ExecutionMode.LOCKED_VALIDATION.value,
        "mode_meta": MODE_META[ExecutionMode.LOCKED_VALIDATION.value],
        "validation_version": lv.get("validation_version", "validation-v1"),
        "frozen_manifest": lv.get("frozen_manifest", {}),
        "fingerprints": lv.get("reproducibility_fingerprints", {}),
        "level_a_quality": lv.get("level_a_quality", {}),
        "level_b_decision": lv.get("level_b_decision", {}),
        "level_c_economic": lv.get("level_c_economic", {}),
        "abstention_decomposition": lv.get("abstention_decomposition", {}),
        "abstention_quality": lv.get("abstention_quality", {}),
        "zero_candidate_diagnostic": lv.get("zero_candidate_diagnostic", {}),
        "robustness_matrix": lv.get("robustness_matrix", {}),
        "diagnostic_sensitivity": lv.get("diagnostic_sensitivity", {}),
        "sample_value_analysis": lv.get("sample_value_analysis", {}),
        "economic_sanity": lv.get("economic_sanity", {}),
        "determinism_evidence": lv.get("determinism_evidence", {}),
        "pass_fail_criteria": lv.get("pass_fail_criteria", {}),
        "claim_ledger": lv.get("claim_ledger", []),
        "evidence_ladder": lv.get("evidence_ladder", {}),
        "limitations": lv.get("limitations", []),
        "locked_honest_explanation": LOCKED_HONEST_EXPLANATION,
    }

