"""Phase 10 tests — EXPECTED LOSS + VOI + ECONOMIC LEDGER (sanity A-N + guards).

These exercise the pure economic engine that sits BEHIND the Phase-9 gates. The
central invariant under test: economics rank only PERMITTED actions and can
NEVER resurrect a blocked action or override a hard gate. Everything is
SIMULATION/ILLUSTRATIVE — no HMEL cost, saving, or validation is implied.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift import config as C
from gradeshift.provenance import Provenance
from gradeshift.schemas import PredictionBundle
from gradeshift.health import SensorHealthReport, HealthState
from gradeshift.applicability import ApplicabilityResult, ApplicabilityState
from gradeshift.material_service import (
    MaterialEligibilityResult, MappingQuality, MATERIAL_SERVICE_VERSION,
)
from gradeshift.disposition import (
    evaluate_disposition, DispositionEvidence, ApprovalConfig, DwellStatus,
    HOLD, SAMPLE_NOW, PRIME_RELEASE_CANDIDATE, ABSTAIN,
)
from gradeshift import economics as E
from gradeshift.economics import (
    evaluate_economics, EconomicInputs, EconomicResult,
    IntervalDerivedRisk, ProvisionalProbabilityRisk, IllustrativeRisk,
    derive_permitted_actions, compute_voi, scale_up_annual,
    ECONOMICS_VERSION, COST_MODEL_VERSION, VOI_MODEL_VERSION,
)

BASE = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)
SPEC = C.get_grade("B")   # band [7.6, 8.4]


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


def _event():
    return S.generate_episode("EP-ECON", "A", "B", seed=9, start_time=BASE)


def _pred(lower=7.7, upper=8.3, point=None, prob_bad=0.2):
    pt = point if point is not None else (lower + upper) / 2
    return PredictionBundle(event_id="EP-ECON", decision_time=_mins(400),
                            point_mfi=pt, lower_mfi=lower, upper_mfi=upper,
                            nominal_coverage=0.9, prob_bad=prob_bad,
                            model_version="m1", calibration_version="c1")


def _mat(quality=MappingQuality.WELL_SUPPORTED, route_known=True, available=True):
    return MaterialEligibilityResult(available, quality, route_known, True, 10.0, 0.0,
                                     (), ("X",), Provenance.ASSUMPTION,
                                     MATERIAL_SERVICE_VERSION)


def _evidence(**over):
    base = dict(event=_event(), decision_time=_mins(400), spec=SPEC,
                prediction=_pred(), material_eligibility=_mat(),
                health_report=SensorHealthReport(_mins(400), HealthState.NORMAL,
                                                  True, {}, (), "h", Provenance.SIMULATED),
                applicability_result=ApplicabilityResult(ApplicabilityState.NORMAL,
                                                         0.0, (), "", "f", "d", "a",
                                                         Provenance.SIMULATED),
                dwell_status=DwellStatus(30.0, 60.0, True, True, _mins(400)),
                approval=ApprovalConfig(), sample_available=False)
    base.update(over)
    return DispositionEvidence(**base)


def _result(**over):
    return evaluate_disposition(_evidence(**over))


def _inputs(mass=50.0, recoverable=None, route_value=75000.0,
            scenario="BASE", latency=None, horizon=240.0):
    rec = mass if recoverable is None else recoverable
    kw = dict(event_id="EP-ECON", decision_id="D1", mass_tonnes=mass,
              recoverable_mass_tonnes=rec, actual_route_value_per_tonne=route_value,
              scenario=C.ECON_SCENARIOS[scenario], decision_horizon_min=horizon)
    if latency is not None:
        kw["sample_latency_min"] = latency
    return EconomicInputs(**kw)


def _borderline(sample=True):
    """Prime blocked ONLY by the interval (candidacy), hard gates pass -> a
    sample could unlock prime. Used for VOI / SAMPLE tests."""
    return _result(prediction=_pred(lower=7.5, upper=8.3), sample_available=sample)


# ── A. zero mass -> zero mass-driven exposure ────────────────────────────────
def test_A_zero_mass_zero_exposure():
    r = _result()
    er = evaluate_economics(r, _inputs(mass=0.0))
    prime = er.expected_loss.get(PRIME_RELEASE_CANDIDATE)
    assert prime.false_prime_exposure_currency == 0.0
    hold = er.expected_loss.get(HOLD)
    assert hold.false_hold_exposure_currency == 0.0


# ── B. higher prime/downgrade spread -> higher false-hold EL on HOLD ─────────
def test_B_higher_spread_higher_false_hold():
    r = _result(prediction=_pred(lower=7.5, upper=8.3))  # p_bad>0 so p_good<1
    low = evaluate_economics(r, _inputs(scenario="LOW")).expected_loss.get(HOLD)
    high = evaluate_economics(r, _inputs(scenario="HIGH")).expected_loss.get(HOLD)
    # HIGH spread = 98000-73000=25000 > LOW spread = 90000-78000=12000
    assert high.false_hold_exposure_currency > low.false_hold_exposure_currency


# ── C. higher false-prime consequence -> higher PRIME false-prime exposure ───
def test_C_higher_consequence_higher_prime_exposure():
    r = _result(prediction=_pred(lower=7.5, upper=8.3))
    base = evaluate_economics(r, _inputs(scenario="BASE")).expected_loss.get(PRIME_RELEASE_CANDIDATE)
    high = evaluate_economics(r, _inputs(scenario="HIGH")).expected_loss.get(PRIME_RELEASE_CANDIDATE)
    if base is not None and high is not None:  # prime may be blocked; guard
        assert high.false_prime_exposure_currency > base.false_prime_exposure_currency
    else:
        # exposure is computed directly, independent of permission
        ib = _inputs(scenario="BASE"); ih = _inputs(scenario="HIGH")
        risk = IntervalDerivedRisk().estimate(r)
        from gradeshift.economics import compute_action_economics
        eb = compute_action_economics(PRIME_RELEASE_CANDIDATE, ib, risk, True)
        eh = compute_action_economics(PRIME_RELEASE_CANDIDATE, ih, risk, True)
        assert eh.false_prime_exposure_currency > eb.false_prime_exposure_currency


# ── D. more expensive sample -> lower VOI (sample cost isolated) ─────────────
def test_D_expensive_sample_lower_voi():
    from dataclasses import replace
    r = _borderline()
    base_sc = C.ECON_SCENARIOS["BASE"]
    cheap_in = EconomicInputs("EP-ECON", "D1", 50.0, 50.0, 75000.0,
                              scenario=replace(base_sc, sample_cost=5000))
    dear_in = EconomicInputs("EP-ECON", "D1", 50.0, 50.0, 75000.0,
                             scenario=replace(base_sc, sample_cost=60000))
    cheap = compute_voi(r, cheap_in, IntervalDerivedRisk())
    dear = compute_voi(r, dear_in, IntervalDerivedRisk())
    assert dear.voi_currency < cheap.voi_currency


# ── E. slower sample (result after horizon) -> VOI not applicable ────────────
def test_E_slow_sample_not_applicable():
    r = _borderline()
    v = compute_voi(r, _inputs(latency=1000.0, horizon=240.0), IntervalDerivedRisk())
    assert v.applicable is False
    assert v.recommend_sample is False


# ── F. zero sample usefulness (PRIME already permitted) -> no SAMPLE ─────────
def test_F_no_benefit_no_sample():
    r = _result(sample_available=True)   # fully in-spec -> PRIME already permitted
    v = compute_voi(r, _inputs(), IntervalDerivedRisk())
    assert v.applicable is False
    assert v.recommend_sample is False


# ── G. prohibited action never appears / never preferred (hard gate ABSTAIN) ─
def test_G_hard_gate_blocks_economics():
    r = _result(health_report=SensorHealthReport(_mins(400), HealthState.ABNORMAL,
                                                  True, {}, (), "h", Provenance.SIMULATED))
    assert r.action == ABSTAIN
    er = evaluate_economics(r, _inputs())
    assert er.permitted_actions == (ABSTAIN,)
    assert er.economic_preferred_action == ABSTAIN
    assert PRIME_RELEASE_CANDIDATE not in er.expected_loss.as_action_map()
    assert HOLD not in er.expected_loss.as_action_map()


# ── H. LOW/BASE/HIGH monotonic false-prime exposure ──────────────────────────
def test_H_scenario_monotonicity():
    r = _result(prediction=_pred(lower=7.5, upper=8.3))
    risk = IntervalDerivedRisk().estimate(r)
    from gradeshift.economics import compute_action_economics
    exp = [compute_action_economics(PRIME_RELEASE_CANDIDATE, _inputs(scenario=s),
                                    risk, True).false_prime_exposure_currency
           for s in ("LOW", "BASE", "HIGH")]
    # consequence/t: LOW 40000 < BASE 60000 < HIGH 90000
    assert exp[0] < exp[1] < exp[2]


# ── I. counterfactual value is kept separate from realized value ─────────────
def test_I_realized_vs_counterfactual_separate():
    r = _result()
    er = evaluate_economics(r, _inputs(mass=50.0, route_value=75000.0),
                            realized_good=None)
    vs = er.value_split
    assert vs.realized_value_currency == 50.0 * 75000.0
    assert vs.counterfactual_opportunity_currency == 50.0 * (95000.0 - 75000.0)
    assert vs.realized_value_currency != vs.counterfactual_opportunity_currency
    assert vs.avoided_loss_currency is None   # not supported without ground truth
    # only populated where ground truth supports it
    er2 = evaluate_economics(r, _inputs(), realized_good=True)
    assert er2.value_split.avoided_loss_currency is not None


# ── J. mass conservation: exposure scales linearly with mass ─────────────────
def test_J_exposure_linear_in_mass():
    r = _result(prediction=_pred(lower=7.5, upper=8.3))
    from gradeshift.economics import compute_action_economics
    risk = IntervalDerivedRisk().estimate(r)
    e1 = compute_action_economics(PRIME_RELEASE_CANDIDATE, _inputs(mass=10.0), risk, True)
    e2 = compute_action_economics(PRIME_RELEASE_CANDIDATE, _inputs(mass=20.0), risk, True)
    assert e2.false_prime_exposure_currency == pytest.approx(2 * e1.false_prime_exposure_currency)


# ── K. components sum EXACTLY to expected loss (dimensional audit) ───────────
def test_K_components_sum_to_expected_loss():
    r = _result(prediction=_pred(lower=7.5, upper=8.3), sample_available=True)
    er = evaluate_economics(r, _inputs())
    for row in er.expected_loss.rows:
        s = sum(c.amount_currency for c in row.components)
        assert s == pytest.approx(row.expected_loss_currency)


# ── L. deterministic replay ──────────────────────────────────────────────────
def test_L_deterministic_replay():
    r = _result(prediction=_pred(lower=7.5, upper=8.3), sample_available=True)
    a = evaluate_economics(r, _inputs()).to_dict()
    b = evaluate_economics(r, _inputs()).to_dict()
    assert a == b


# ── M. serialization + versioning round-trip ─────────────────────────────────
def test_M_serialization_and_versions():
    r = _result(prediction=_pred(lower=7.5, upper=8.3), sample_available=True)
    er = evaluate_economics(r, _inputs())
    d = er.to_ledger()
    s = json.dumps(d, default=str)
    back = json.loads(s)
    assert back["versions"]["economics"] == ECONOMICS_VERSION
    assert back["versions"]["cost_model"] == COST_MODEL_VERSION
    assert back["versions"]["voi_model"] == VOI_MODEL_VERSION
    assert back["phase9_action"] == r.action


# ── N. permitted-action constraint: economics never resurrect blocked action ─
def test_N_never_resurrect_blocked_action():
    # OOD forces ABSTAIN; even though a (hypothetical) PRIME would be far cheaper,
    # the economic engine must offer ONLY ABSTAIN.
    r = _result(applicability_result=ApplicabilityResult(ApplicabilityState.OOD,
                                                        0.0, (), "", "f", "d", "a",
                                                        Provenance.SIMULATED))
    assert r.action == ABSTAIN
    er = evaluate_economics(r, _inputs())
    assert er.permitted_actions == (ABSTAIN,)
    assert set(er.expected_loss.as_action_map()) == {ABSTAIN}
    # VOI must not propose sampling to unlock a hard-gate-blocked prime
    assert er.voi.applicable is False and er.voi.recommend_sample is False


# ── positive VOI: borderline interval, sample unlocks prime -> SAMPLE worth it
def test_positive_voi_recommends_sample():
    r = _borderline(sample=True)
    assert PRIME_RELEASE_CANDIDATE not in derive_permitted_actions(r)
    v = compute_voi(r, _inputs(latency=120.0, horizon=240.0), IntervalDerivedRisk(),
                    min_voi_threshold=0.0)
    assert v.applicable is True
    assert v.voi_currency > 0.0
    assert v.recommend_sample is True


# ── risk proxy is never a validated probability ──────────────────────────────
def test_risk_proxy_not_validated():
    r = _result()
    for ri in (IntervalDerivedRisk(), ProvisionalProbabilityRisk(), IllustrativeRisk(0.3)):
        est = ri.estimate(r)
        assert est.validated is False
        d = est.to_dict()
        assert "p_bad_PROXY" in d and "PROXY" in "".join(d.keys())
        assert "prob_good" not in d
    with pytest.raises(ValueError):
        E.RiskEstimate(0.5, "x", Provenance.SIMULATED, validated=True)


# ── provisional prob_bad proxy is isolated, labelled, never drives permission ─
def test_provisional_proxy_isolated():
    r = _result(prediction=_pred(lower=7.7, upper=8.3, prob_bad=0.99))
    # even an alarming provisional prob_bad does not change the PERMITTED set
    assert PRIME_RELEASE_CANDIDATE in derive_permitted_actions(r)
    er = evaluate_economics(r, _inputs(), risk_input=ProvisionalProbabilityRisk())
    assert "prob_good" not in json.dumps(er.to_ledger())


# ── annual scale-up is a scenario function with no hard-coded savings ────────
def test_annual_scaleup_is_scenario_function():
    a = scale_up_annual(validated_episode_value_currency=1_000_000.0,
                        eligible_transitions_per_year=50, availability=0.9,
                        adoption=0.5)
    assert a.annual_value_currency == pytest.approx(50 * 1_000_000.0 * 0.9 * 0.5)
    # zero adoption -> zero annual value (no fixed headline)
    z = scale_up_annual(1_000_000.0, 50, 0.9, 0.0)
    assert z.annual_value_currency == 0.0
    with pytest.raises(ValueError):
        scale_up_annual(1.0, 10, 1.5, 0.5)


# ── derive_permitted_actions mirrors the frozen gate table ───────────────────
def test_permitted_actions_from_gates():
    assert derive_permitted_actions(_result()) == (PRIME_RELEASE_CANDIDATE, HOLD, ABSTAIN)
    r_sample = _borderline(sample=True)
    assert SAMPLE_NOW in derive_permitted_actions(r_sample)
    assert PRIME_RELEASE_CANDIDATE not in derive_permitted_actions(r_sample)


# ── invalid economic inputs are rejected ─────────────────────────────────────
def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        EconomicInputs("E", "D", mass_tonnes=-1.0, recoverable_mass_tonnes=0.0,
                       actual_route_value_per_tonne=75000.0)
    with pytest.raises(ValueError):
        EconomicInputs("E", "D", mass_tonnes=10.0, recoverable_mass_tonnes=20.0,
                       actual_route_value_per_tonne=75000.0)
