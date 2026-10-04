"""Phase 9 tests — DISPOSITION DECISION ENGINE (decision-table A–T + contract).

These exercise the pure `evaluate_disposition` engine: hard gates FIRST, the
frozen action vocabulary (HOLD / SAMPLE NOW / PRIME-RELEASE CANDIDATE / ABSTAIN),
machine-readable reason codes, expiry/approval/fallback, provisional p(bad)
isolation, determinism, serialization and future-information invariance.

Everything is SIMULATION/ASSUMPTION — no HMEL validation is implied, and a
PRIME-RELEASE CANDIDATE is never a release/certification.
"""
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift import config as C
from gradeshift.provenance import Provenance
from gradeshift.schemas import PredictionBundle, ProvenancedObservation, DecisionSnapshot
from gradeshift.health import SensorHealthReport, HealthState
from gradeshift.applicability import ApplicabilityResult, ApplicabilityState
from gradeshift.material_service import (
    MaterialEligibilityResult, MappingQuality, MATERIAL_SERVICE_VERSION,
    MR_INSUFFICIENT,
)
from gradeshift.disposition import (
    evaluate_disposition, DispositionEvidence, DispositionPolicy, DispositionResult,
    ApprovalConfig, DwellStatus, SampleEligibility, IllustrativeCostProvider,
    compute_dwell_status, evaluate_hard_gates,
    HOLD, SAMPLE_NOW, PRIME_RELEASE_CANDIDATE, ABSTAIN, FALLBACK_FOLLOW_SOP,
    PRIME_INTERVAL_PASS, PRIME_DWELL_PASS, PRIME_MATERIAL_SUPPORTED,
    PRIME_CANDIDATE_REQUIRES_AUTHORIZATION,
    HOLD_INTERVAL_CROSSES_SPEC, HOLD_DWELL_INCOMPLETE, HOLD_MATERIAL_SUPPORT_INCOMPLETE,
    SAMPLE_ELIGIBLE,
    ABSTAIN_SENSOR_HEALTH, ABSTAIN_OOD, ABSTAIN_MATERIAL_MAPPING, ABSTAIN_ROUTE_AMBIGUOUS,
    ABSTAIN_NO_CALIBRATION, ABSTAIN_NO_PREDICTION, ABSTAIN_NO_SPECIFICATION,
    ABSTAIN_MODEL_VERSION, ABSTAIN_NO_APPROVAL_PATH, RECOMMENDATION_EXPIRED,
    DISPOSITION_VERSION,
)

BASE = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
SPEC = C.get_grade("B")   # band [7.6, 8.4], dwell 30 min


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


def _event():
    return S.generate_episode("EP-DISP", "A", "B", seed=9, start_time=BASE)


# ── builders ──────────────────────────────────────────────────────────────
def _pred(lower=7.7, upper=8.3, point=None, prob_bad=0.2, model="m1", calib="c1"):
    pt = point if point is not None else (lower + upper) / 2
    return PredictionBundle(event_id="EP-DISP", decision_time=_mins(400), point_mfi=pt,
                            lower_mfi=lower, upper_mfi=upper, nominal_coverage=0.9,
                            prob_bad=prob_bad, model_version=model, calibration_version=calib)


def _mat(quality=MappingQuality.WELL_SUPPORTED, route_known=True, available=True,
         blocking=(), resid=10.0, ambig=0.0):
    return MaterialEligibilityResult(available, quality, route_known, True, resid, ambig,
                                     tuple(blocking), ("MATERIAL_WELL_SUPPORTED",),
                                     Provenance.ASSUMPTION, MATERIAL_SERVICE_VERSION)


def _health(state=HealthState.NORMAL):
    return SensorHealthReport(_mins(400), state, True, {}, (), "health-v1", Provenance.SIMULATED)


def _appl(state=ApplicabilityState.NORMAL):
    return ApplicabilityResult(state, 0.0, (), "", "f", "d", "a", Provenance.SIMULATED)


def _dwell(satisfied=True):
    return DwellStatus(30.0, 60.0 if satisfied else 5.0, satisfied, True, _mins(400))


def _evidence(**over):
    base = dict(event=_event(), decision_time=_mins(400), spec=SPEC,
                prediction=_pred(), material_eligibility=_mat(),
                health_report=_health(), applicability_result=_appl(),
                dwell_status=_dwell(True), approval=ApprovalConfig(),
                sample_available=False)
    base.update(over)
    return DispositionEvidence(**base)


# ── A. valid + in-spec interval + supported -> PRIME-RELEASE CANDIDATE ────
def test_A_prime_candidate():
    r = evaluate_disposition(_evidence())
    assert r.action == PRIME_RELEASE_CANDIDATE
    assert PRIME_INTERVAL_PASS in r.reason_codes
    assert PRIME_DWELL_PASS in r.reason_codes
    assert PRIME_MATERIAL_SUPPORTED in r.reason_codes
    assert PRIME_CANDIDATE_REQUIRES_AUTHORIZATION in r.reason_codes
    assert "CANDIDATE" in r.note and "authoriz" in r.note.lower()


# ── B. point in-spec but interval crosses limit -> HOLD (not prime) ──────
def test_B_interval_crosses_holds():
    r = evaluate_disposition(_evidence(prediction=_pred(lower=7.5, upper=8.3, point=7.9)))
    assert r.action == HOLD
    assert HOLD_INTERVAL_CROSSES_SPEC in r.reason_codes
    assert r.action != PRIME_RELEASE_CANDIDATE


# ── C. dwell incomplete -> HOLD ──────────────────────────────────────────
def test_C_dwell_incomplete_holds():
    r = evaluate_disposition(_evidence(dwell_status=_dwell(False)))
    assert r.action == HOLD
    assert HOLD_DWELL_INCOMPLETE in r.reason_codes


# ── D. sensor data missing -> ABSTAIN ────────────────────────────────────
def test_D_sensor_missing_abstains():
    r = evaluate_disposition(_evidence(health_report=None))
    assert r.action == ABSTAIN
    assert ABSTAIN_SENSOR_HEALTH in r.reason_codes


# ── E. sensor frozen (ABNORMAL) -> ABSTAIN ───────────────────────────────
def test_E_sensor_frozen_abstains():
    r = evaluate_disposition(_evidence(health_report=_health(HealthState.ABNORMAL)))
    assert r.action == ABSTAIN
    assert ABSTAIN_SENSOR_HEALTH in r.reason_codes


# ── F. OOD applicability -> ABSTAIN ──────────────────────────────────────
def test_F_ood_abstains():
    r = evaluate_disposition(_evidence(applicability_result=_appl(ApplicabilityState.OOD)))
    assert r.action == ABSTAIN
    assert ABSTAIN_OOD in r.reason_codes


# ── G. unseen grade pair (UNSUPPORTED applicability) -> ABSTAIN ──────────
def test_G_unseen_grade_pair_abstains():
    r = evaluate_disposition(_evidence(
        applicability_result=_appl(ApplicabilityState.UNSUPPORTED)))
    assert r.action == ABSTAIN
    assert ABSTAIN_OOD in r.reason_codes


# ── H. material window unavailable -> ABSTAIN ────────────────────────────
def test_H_material_unavailable_abstains():
    r = evaluate_disposition(_evidence(material_eligibility=_mat(
        quality=MappingQuality.UNAVAILABLE, route_known=False, available=False,
        blocking=(MR_INSUFFICIENT,))))
    assert r.action == ABSTAIN
    assert ABSTAIN_MATERIAL_MAPPING in r.reason_codes


# ── I. ambiguous route -> ABSTAIN by default, HOLD under explicit policy ─
def test_I_ambiguous_route_policy():
    amb = _mat(quality=MappingQuality.AMBIGUOUS, route_known=False, ambig=0.5)
    r = evaluate_disposition(_evidence(material_eligibility=amb))
    assert r.action == ABSTAIN
    assert ABSTAIN_ROUTE_AMBIGUOUS in r.reason_codes
    hold_pol = DispositionPolicy(ambiguous_route_action=HOLD)
    r2 = evaluate_disposition(_evidence(material_eligibility=amb), policy=hold_pol)
    assert r2.action == HOLD
    assert HOLD_MATERIAL_SUPPORT_INCOMPLETE in r2.reason_codes


# ── J. expired recommendation -> fallback / recompute (never retained) ───
def test_J_expired_falls_back():
    exp_min = C.POLICY.recommendation_expiry_min
    stale = _evidence(current_time=_mins(400) + timedelta(minutes=exp_min + 1))
    r = evaluate_disposition(stale)
    assert r.expired is True
    assert r.action == FALLBACK_FOLLOW_SOP
    assert RECOMMENDATION_EXPIRED in r.reason_codes


# ── K. missing specification -> ABSTAIN ──────────────────────────────────
def test_K_missing_spec_abstains():
    r = evaluate_disposition(_evidence(spec=None))
    assert r.action == ABSTAIN
    assert ABSTAIN_NO_SPECIFICATION in r.reason_codes


# ── L. missing calibration -> ABSTAIN ────────────────────────────────────
def test_L_missing_calibration_abstains():
    r = evaluate_disposition(_evidence(prediction=_pred(calib="")))
    assert r.action == ABSTAIN
    assert ABSTAIN_NO_CALIBRATION in r.reason_codes


# ── M. model/calibration version mismatch -> ABSTAIN ─────────────────────
def test_M_version_mismatch_abstains():
    pol = DispositionPolicy(expected_model_version="EXPECTED-MODEL")
    r = evaluate_disposition(_evidence(), policy=pol)
    assert r.action == ABSTAIN
    assert ABSTAIN_MODEL_VERSION in r.reason_codes


# ── N. insufficient evidence BUT a sample path exists -> SAMPLE NOW ──────
def test_N_sample_path_eligible():
    r = evaluate_disposition(_evidence(
        prediction=_pred(lower=7.5, upper=8.3), sample_available=True))
    assert r.action == SAMPLE_NOW
    assert SAMPLE_ELIGIBLE in r.reason_codes
    assert r.sample_eligibility.eligible is True


# ── O. no approval path -> cannot reach executable prime-release state ────
def test_O_no_approval_path_abstains():
    r = evaluate_disposition(_evidence(approval=ApprovalConfig(required_role="")))
    assert r.action != PRIME_RELEASE_CANDIDATE
    assert r.action == ABSTAIN
    assert ABSTAIN_NO_APPROVAL_PATH in r.reason_codes
    snap = evaluate_disposition(_evidence()).to_snapshot()
    assert snap.action == PRIME_RELEASE_CANDIDATE
    assert snap.authorized_by is None and snap.authorized_at is None


# ── P. exact spec boundary: interval == band is inclusive (prime) ────────
def test_P_boundary_conditions():
    # interval exactly equal to the spec band -> still within (inclusive)
    on_edge = evaluate_disposition(_evidence(
        prediction=_pred(lower=SPEC.mfi_low, upper=SPEC.mfi_high)))
    assert on_edge.action == PRIME_RELEASE_CANDIDATE
    # a hair outside the upper limit -> crosses -> HOLD
    over = evaluate_disposition(_evidence(
        prediction=_pred(lower=SPEC.mfi_low, upper=SPEC.mfi_high + 1e-6)))
    assert over.action == HOLD
    assert HOLD_INTERVAL_CROSSES_SPEC in over.reason_codes


# ── Q. serialization round-trip (result + snapshot) ──────────────────────
def test_Q_serialization_roundtrip():
    r = evaluate_disposition(_evidence())
    s = json.dumps(r.to_dict(), default=str)
    back = json.loads(s)
    assert back["action"] == r.action
    assert back["disposition_version"] == DISPOSITION_VERSION
    # the frozen DecisionSnapshot also round-trips
    snap = r.to_snapshot()
    d = snap.to_dict()
    assert DecisionSnapshot.from_dict(d).action == snap.action
    json.dumps(d, default=str)


# ── R. deterministic replay ──────────────────────────────────────────────
def test_R_deterministic_replay():
    a = evaluate_disposition(_evidence()).to_dict()
    b = evaluate_disposition(_evidence()).to_dict()
    assert a == b


# ── S. future-information invariance (as-of dwell is causal) ─────────────
def test_S_future_information_invariance():
    ev = _event()
    t = _mins(400)
    # engine computes dwell itself from the series; result must not depend on
    # observations AFTER t
    base = _evidence(event=ev, dwell_status=None)
    r0 = evaluate_disposition(base)
    future_obs = ProvenancedObservation("MFI_online", 999.0, "g/10min",
                                         _mins(900), Provenance.SIMULATED)
    ev2 = replace(ev, series=ev.series + (future_obs,))
    r1 = evaluate_disposition(_evidence(event=ev2, dwell_status=None))
    assert r0.dwell_status.to_dict() == r1.dwell_status.to_dict()
    assert r0.action == r1.action


# ── T. fail-safe: a near-empty bundle never raises, always ABSTAINs ──────
def test_T_failsafe_minimal_bundle():
    ev = DispositionEvidence(event=_event(), decision_time=_mins(400), spec=None,
                             prediction=None, material_eligibility=None,
                             health_report=None, applicability_result=None)
    r = evaluate_disposition(ev)
    assert r.action == ABSTAIN
    assert len(r.reason_codes) >= 1
    json.dumps(r.to_dict(), default=str)


# ── gate-combination: hard gate dominates a would-be prime ───────────────
def test_hard_gate_precedence_over_candidacy():
    # a perfect prime bundle except prediction missing -> ABSTAIN, not HOLD/PRIME
    r = evaluate_disposition(_evidence(prediction=None))
    assert r.action == ABSTAIN
    assert ABSTAIN_NO_PREDICTION in r.reason_codes


# ── provisional p(bad) is isolated, never drives prime candidacy ─────────
def test_provisional_prob_bad_isolated():
    # an alarmingly high p(bad) must NOT block a prime candidate whose calibrated
    # interval is fully in-spec (prime relies on the interval, not p(bad))
    r = evaluate_disposition(_evidence(prediction=_pred(lower=7.7, upper=8.3, prob_bad=0.99)))
    assert r.action == PRIME_RELEASE_CANDIDATE
    assert r.prediction_summary["prob_bad_PROVISIONAL"] == 0.99
    assert "PROVISIONAL" in "".join(r.prediction_summary.keys())
    # it is never surfaced as a validated probability of good material
    assert "prob_good" not in r.to_dict()


# ── policy version and provenance appear in the record ───────────────────
def test_versions_and_provenance_recorded():
    r = evaluate_disposition(_evidence())
    assert r.versions["disposition"] == DISPOSITION_VERSION
    assert r.versions["policy"] == C.POLICY.version
    assert r.versions["cost_model"]
    assert r.provenance is Provenance.SIMULATED
    snap = r.to_snapshot()
    assert snap.versions["policy"] == C.POLICY.version


# ── expected-loss table is injected, labelled, and does NOT pick the action
def test_expected_loss_table_illustrative():
    r = evaluate_disposition(_evidence(), cost_provider=IllustrativeCostProvider("HIGH"))
    tbl = r.expected_loss_table
    assert set(tbl.as_action_map()) == {PRIME_RELEASE_CANDIDATE, HOLD, SAMPLE_NOW, ABSTAIN}
    assert "SIMULATED" in tbl.to_dict()["note"] or "ILLUSTRATIVE" in tbl.to_dict()["note"]
    # action chosen by gates/policy, not by minimum expected loss
    assert r.action == PRIME_RELEASE_CANDIDATE


# ── ABSTAIN is a valid successful outcome (not an exception) ─────────────
def test_abstain_is_successful_outcome():
    r = evaluate_disposition(_evidence(health_report=_health(HealthState.ABNORMAL)))
    assert isinstance(r, DispositionResult)
    assert r.action == ABSTAIN
    assert r.fallback_action == FALLBACK_FOLLOW_SOP


# ── as-of dwell helper is causal and correct ─────────────────────────────
def test_compute_dwell_status_causal():
    ev = _event()
    dw_early = compute_dwell_status(ev, _mins(5), SPEC)
    dw_late = compute_dwell_status(ev, _mins(600), SPEC)
    # dwell can only have been satisfied LATER, never earlier
    assert dw_early.as_of == _mins(5)
    assert dw_late.elapsed_min >= dw_early.elapsed_min or not dw_late.satisfied


