"""Phase 13 — FINAL VALIDATION analyses.

Pure, deterministic evidence-generation helpers used to assemble the final
validation package. NONE of these tune the production policy: robustness and
sensitivity run on CONTROLLED fixtures or purely offline, and are labelled as
diagnostics. Everything is SIMULATION/ASSUMPTION — no HMEL claim is implied.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .provenance import Provenance

VALIDATION_VERSION = "validation-v1"

# ── evidence ladder (E0..E5) ────────────────────────────────────────────────
EVIDENCE_LADDER = {
    "E0": "assumption",
    "E1": "theory / formulation",
    "E2": "synthetic simulation",
    "E3": "controlled prototype",
    "E4": "historical / public-data validation",
    "E5": "industrial validation",
}


# ── blocking-gate category map (for the abstention decomposition) ───────────
GATE_CATEGORY = {
    "valid_transition": "transition_identity",
    "timestamp_alignment": "timestamp",
    "prediction_available": "calibration_prediction",
    "calibrated_interval": "calibration_prediction",
    "model_version": "calibration_prediction",
    "material_window_available": "material_mapping",
    "material_support_sufficient": "material_mapping",
    "route_known": "material_mapping",
    "mapping_uncertainty": "material_mapping",
    "sensor_health": "sensor_health",
    "applicability": "ood",
    "specification_available": "specification",
    "approval_path_configured": "approval",
}


def gate_decomposition(disposition_results: List) -> dict:
    """Decompose WHY PrimePath abstained across a set of DispositionResults.
    Counts blocking gates by category and how many decisions had multiple
    simultaneous blocking gates."""
    from . import disposition as D
    by_category: Dict[str, int] = {}
    multi_gate_decisions = 0
    abstained = 0
    total = len(disposition_results)
    for res in disposition_results:
        blocking = [g for g in res.gates
                    if (not g.passed) and g.severity == D.Severity.BLOCK]
        if res.action == D.ABSTAIN:
            abstained += 1
        if len(blocking) > 1:
            multi_gate_decisions += 1
        cats = {GATE_CATEGORY.get(g.gate_id, g.gate_id) for g in blocking}
        for c in cats:
            by_category[c] = by_category.get(c, 0) + 1
    return {"total_decisions": total, "abstained_decisions": abstained,
            "blocking_by_category": dict(sorted(by_category.items())),
            "multi_gate_decisions": multi_gate_decisions,
            "note": "A decision counts once per blocking category; multi_gate "
                    "decisions were blocked by >1 hard gate simultaneously."}


# ── robustness matrix (deterministic fault/restriction fixtures) ────────────
def robustness_matrix() -> dict:
    """Each row is a CONTROLLED fixture (not the locked set) with its expected
    forced state/action. Proves the fail-safe behaviour of the gates."""
    from . import disposition as D
    from . import config as _C
    from . import simulate as S
    from .provenance import Provenance
    from .schemas import PredictionBundle
    from .health import SensorHealthReport, HealthState
    from .applicability import ApplicabilityResult, ApplicabilityState
    from .material_service import (MaterialEligibilityResult, MappingQuality,
                                   MATERIAL_SERVICE_VERSION, MR_INSUFFICIENT)

    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    ev = S.generate_episode("ROBUST", "A", "B", seed=77, start_time=base)
    spec = _C.get_grade("B")
    t = base + timedelta(minutes=400)

    def pred(lo=7.7, hi=8.3, calib="c1", dt=None):
        return PredictionBundle(event_id="ROBUST", decision_time=dt or t,
                                point_mfi=(lo + hi) / 2, lower_mfi=lo, upper_mfi=hi,
                                nominal_coverage=0.9, prob_bad=0.2,
                                model_version="m1", calibration_version=calib)

    def mat(q=MappingQuality.WELL_SUPPORTED, rk=True, avail=True, blk=(), amb=0.0):
        return MaterialEligibilityResult(avail, q, rk, True, 10.0, amb, tuple(blk),
                                         ("X",), Provenance.ASSUMPTION, MATERIAL_SERVICE_VERSION)

    def hr(state=HealthState.NORMAL):
        return SensorHealthReport(t, state, True, {}, (), "h", Provenance.SIMULATED)

    def ap(state=ApplicabilityState.NORMAL):
        return ApplicabilityResult(state, 0.0, (), "", "f", "d", "a", Provenance.SIMULATED)

    def evid(**over):
        kw = dict(event=ev, decision_time=t, spec=spec, prediction=pred(),
                  material_eligibility=mat(), health_report=hr(),
                  applicability_result=ap(),
                  dwell_status=D.DwellStatus(30.0, 60.0, True, True, t),
                  approval=D.ApprovalConfig(), sample_available=False)
        kw.update(over)
        return D.DispositionEvidence(**kw)

    cases = [
        ("normal_evidence", evid(), D.PRIME_RELEASE_CANDIDATE),
        ("missing_sensor", evid(health_report=None), D.ABSTAIN),
        ("frozen_sensor", evid(health_report=hr(HealthState.ABNORMAL)), D.ABSTAIN),
        ("stale_data", evid(health_report=hr(HealthState.UNAVAILABLE)), D.ABSTAIN),
        ("timestamp_disorder", evid(decision_time=base - timedelta(minutes=10)), D.ABSTAIN),
        ("ood_shift", evid(applicability_result=ap(ApplicabilityState.OOD)), D.ABSTAIN),
        ("unknown_grade_pair", evid(applicability_result=ap(ApplicabilityState.UNSUPPORTED)), D.ABSTAIN),
        ("ambiguous_routing", evid(material_eligibility=mat(
            q=MappingQuality.AMBIGUOUS, rk=False, amb=0.5)), D.ABSTAIN),
        ("incomplete_material_mapping", evid(material_eligibility=mat(
            q=MappingQuality.UNAVAILABLE, rk=False, avail=False, blk=(MR_INSUFFICIENT,))), D.ABSTAIN),
        ("unavailable_calibration", evid(prediction=pred(calib="")), D.ABSTAIN),
        ("expired_recommendation", evid(current_time=t + timedelta(
            minutes=_C.POLICY.recommendation_expiry_min + 1)), D.FALLBACK_FOLLOW_SOP),
    ]
    rows = []
    for name, e, expected in cases:
        res = D.evaluate_disposition(e)
        rows.append({"scenario": name, "expected_forced_action": expected,
                     "observed_action": res.action,
                     "match": res.action == expected,
                     "reason_codes": list(res.reason_codes)})
    return {"rows": rows, "all_match": all(r["match"] for r in rows),
            "note": "Controlled fail-safe fixtures (NOT the locked set). "
                    "SIMULATION/ASSUMPTION."}


# ── offline diagnostic sensitivity (NOT a validated policy change) ──────────
def sensitivity_analysis(scenario=None) -> dict:
    """Offline sweeps on CONTROLLED fixtures to see which assumptions dominate
    decision behaviour. Never applied back to the production policy."""
    from dataclasses import replace
    from . import disposition as D
    from . import economics as E
    from . import config as _C
    from . import simulate as S
    from .provenance import Provenance
    from .schemas import PredictionBundle
    from .health import SensorHealthReport, HealthState
    from .applicability import ApplicabilityResult, ApplicabilityState
    from .material_service import (MaterialEligibilityResult, MappingQuality,
                                   MATERIAL_SERVICE_VERSION)
    sc = scenario or _C.ECON_SCENARIOS[_C.DEFAULT_SCENARIO]
    base = datetime(2026, 10, 2, tzinfo=timezone.utc)
    ev = S.generate_episode("SENS", "A", "B", seed=88, start_time=base)
    spec = _C.get_grade("B")
    t = base + timedelta(minutes=400)

    def evid(lo, hi, sample=False):
        return D.DispositionEvidence(
            event=ev, decision_time=t, spec=spec,
            prediction=PredictionBundle("SENS", t, (lo + hi) / 2, lo, hi, 0.9, 0.2, "m", "c"),
            material_eligibility=MaterialEligibilityResult(
                True, MappingQuality.WELL_SUPPORTED, True, True, 10.0, 0.0, (), ("X",),
                Provenance.ASSUMPTION, MATERIAL_SERVICE_VERSION),
            health_report=SensorHealthReport(t, HealthState.NORMAL, True, {}, (), "h",
                                             Provenance.SIMULATED),
            applicability_result=ApplicabilityResult(ApplicabilityState.NORMAL, 0.0, (),
                                                     "", "f", "d", "a", Provenance.SIMULATED),
            dwell_status=D.DwellStatus(30.0, 60.0, True, True, t), sample_available=sample)

    # 1) interval width: how wide before PRIME stops being permitted?
    width_sweep = []
    for half in (0.2, 0.4, 0.6, 0.8):
        lo, hi = 8.0 - half, 8.0 + half
        res = D.evaluate_disposition(evid(lo, hi))
        width_sweep.append({"half_width": half, "interval": (lo, hi), "action": res.action})

    # 2) sample cost: VOI sign on a borderline (interval-crossing) fixture
    borderline = D.evaluate_disposition(evid(7.5, 8.3, sample=True))
    cost_sweep = []
    for scost in (5000, 20000, 60000, 150000):
        inp = E.EconomicInputs("SENS", "D", 50.0, 50.0, float(sc.downgrade_price),
                               scenario=replace(sc, sample_cost=scost))
        voi = E.compute_voi(borderline, inp, E.IntervalDerivedRisk())
        cost_sweep.append({"sample_cost": scost, "voi_currency": voi.voi_currency,
                           "recommend_sample": voi.recommend_sample})

    # 3) false-prime consequence: economic preferred action among permitted
    inspec = D.evaluate_disposition(evid(7.7, 8.3))
    consequence_sweep = []
    for cons in (20000, 60000, 120000):
        inp = E.EconomicInputs("SENS", "D", 50.0, 50.0, float(sc.downgrade_price),
                               scenario=replace(sc, false_prime_consequence=cons))
        er = E.evaluate_economics(inspec, inp, risk_input=E.ProvisionalProbabilityRisk())
        consequence_sweep.append({"false_prime_consequence": cons,
                                  "economic_preferred_action": er.economic_preferred_action})

    return {"label": "DIAGNOSTIC SENSITIVITY — NOT VALIDATED POLICY",
            "interval_width_sweep": width_sweep, "sample_cost_sweep": cost_sweep,
            "false_prime_consequence_sweep": consequence_sweep,
            "note": "Offline diagnostics on controlled fixtures; production policy "
                    "parameters are unchanged. SIMULATION/ASSUMPTION."}


# ── economic sanity checks ──────────────────────────────────────────────────
def economic_sanity(econ_result) -> dict:
    """Reconcile a demo EconomicResult: components sum to EL, mass is non-negative
    and bounded, realized vs counterfactual are separated."""
    inp = econ_result.inputs
    checks = {}
    checks["no_double_counting"] = all(
        abs(sum(c.amount_currency for c in row.components) - row.expected_loss_currency) < 1e-6
        for row in econ_result.expected_loss.rows)
    checks["mass_non_negative"] = inp.mass_tonnes >= 0
    checks["recoverable_bounded"] = 0.0 <= inp.recoverable_mass_tonnes <= inp.mass_tonnes + 1e-9
    led = econ_result.to_ledger()
    checks["realized_value_present"] = "realized_value_currency" in led
    checks["counterfactual_labelled"] = "counterfactual_opportunity_currency" in led
    checks["realized_separate_from_counterfactual"] = (
        led["realized_value_currency"] != led.get("counterfactual_opportunity_currency")
        or inp.recoverable_mass_tonnes == 0)
    checks["all_passed"] = all(v for k, v in checks.items() if k != "all_passed")
    return checks


# ── final claim ledger (every claim carries an evidence level + wording) ────
def claim_ledger() -> List[dict]:
    """Each claim is tagged with its evidence level and the wording allowed vs
    prohibited. For this synthetic competition POC claims stay at E2/E3."""
    def c(topic, claim, evidence, artifact, level, allowed, prohibited):
        return {"topic": topic, "claim": claim, "evidence": evidence,
                "source_artifact": artifact, "evidence_level": level,
                "allowed_wording": allowed, "prohibited_wording": prohibited}
    return [
        c("quality_accuracy",
          "The GBM point estimator achieves a measurable MAE/RMSE on the frozen "
          "synthetic locked set.", "locked point metrics", "final_validation.json#quality",
          "E2", "on simulated data the estimator shows MAE=…",
          "proven accurate / R2>0.95 on plant data"),
        c("uncertainty",
          "Split-conformal intervals report empirical coverage near nominal on the "
          "locked set, from only a few INDEPENDENT events.",
          "locked coverage/width + n_events", "final_validation.json#quality", "E2",
          "intervals are calibrated on simulated data (3 independent cal events)",
          "141 independent validation points / field-calibrated"),
        c("ood",
          "The applicability layer forces ABSTAIN on OOD / unsupported grade pairs.",
          "robustness matrix", "final_validation.json#robustness", "E3",
          "OOD inputs are refused by design", "detects all real plant anomalies"),
        c("material_mapping",
          "Residence-time material mapping ties a decision to a downstream window "
          "with explicit uncertainty.", "material window summary", "replay/material_service",
          "E2", "simulated residence mapping with surfaced uncertainty",
          "digital-twin / plant-calibrated / exact material tracking"),
        c("false_prime_protection",
          "On the locked set PrimePath produced 0 t false-prime mass vs the baselines.",
          "replay comparison", "final_validation.json#decision", "E2",
          "on this synthetic corpus PrimePath avoided false-prime mass",
          "guarantees zero bad releases / safety-certified"),
        c("false_hold_value",
          "PrimePath's conservatism carries a false-hold/opportunity cost, reported "
          "explicitly.", "replay + economics", "final_validation.json#economic", "E2",
          "conservatism has a quantified opportunity cost on simulated data",
          "net savings proven / realized plant value"),
        c("sampling",
          "VOI recommends SAMPLE NOW only when it can change the permissible action "
          "and VOI>threshold.", "demo VOI", "final_validation.json#sample_value", "E3",
          "sampling value illustrated on a controlled fixture",
          "plant-wide sampling savings"),
        c("annual_value",
          "Annual value is a SCENARIO function of explicit inputs.", "scale-up function",
          "economics.scale_up_annual", "E0",
          "illustrative scenario: value = transitions×episode×availability×adoption",
          "₹X Cr/year savings / fixed annual benefit"),
        c("hmel_applicability",
          "The approach is framed for polyolefin grade transitions; no HMEL data was "
          "used.", "design docs", "FINAL_VALIDATION_REPORT.md", "E1",
          "conceptually applicable to grade transitions",
          "validated on HMEL / HMEL-approved / plant-proven"),
        c("scalability",
          "The architecture is modular and deterministic.", "module layout + tests",
          "test suite", "E3", "prototype is modular and reproducible",
          "production-ready / deployed at scale"),
        c("safety_authority",
          "PrimePath is ADVISORY; PRIME-RELEASE CANDIDATE always requires human/QC "
          "authorization.", "disposition engine", "disposition.py", "E1",
          "advisory decision support requiring human authorization",
          "autonomous release / certifies material / writes setpoints"),
    ]


