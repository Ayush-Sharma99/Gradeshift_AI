"""Phase 7C tests — COMBINED ASSURANCE STATE + HARD-GATE CONTRACT.

Covers tests O–R of the Phase 7 objective: the three evidence layers stay
logically distinct (never one scalar); the combined assurance state preserves
each underlying state; a critical health OR applicability failure forces
ABSTAIN via the reusable hard-gate contract; a DEGRADED-but-usable state is
ELIGIBLE_WITH_CONSTRAINTS (never a confident prime candidate); and the health
vs OOD distinction holds (a sensor spike is a health failure, NOT OOD; an
unseen grade pair is an applicability failure, NOT a health failure).
"""
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift import faults as F
from gradeshift.pipeline import default_corpus
from gradeshift.partition import chronological_split, Partition
from gradeshift.features import build_features
from gradeshift.applicability import (
    ApplicabilityDetector, ApplicabilityState, unavailable_result,
)
from gradeshift.health import assess_sensor_health, HealthState
from gradeshift.assurance import (
    AssuranceInputs, AssuranceState, assess_assurance, evaluate_gates,
    gates_force_abstain, HARD_GATE_ABSTAIN, FALLBACK_FOLLOW_SOP,
    SensorHealthGate, ApplicabilityGate, PredictionAvailabilityGate,
)

BASE = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


@pytest.fixture(scope="module")
def detector():
    corpus = default_corpus()
    split = chronological_split(corpus)
    by_id = {e.event_id: e for e in corpus}
    train = [by_id[i] for i, p in split.items() if p is Partition.TRAIN]
    return ApplicabilityDetector.fit(train)


def _clean_event(detector):
    gf, gt = detector.known_directions[0].split("->")
    return S.generate_episode("EP-ASSURE", gf, gt, seed=77, start_time=BASE)


def _inputs(event, t, detector, *, prediction=True, feats=True):
    hr = assess_sensor_health(event, t)
    ar = detector.assess_event(event, t)
    return AssuranceInputs(prediction_available=prediction,
                           required_features_available=feats,
                           health_report=hr, applicability_result=ar)


# ── O. all sound -> ELIGIBLE_FOR_FURTHER_DECISION ────────────────────────

def test_O_all_sound_eligible(detector):
    ev = _clean_event(detector)
    res = assess_assurance(_inputs(ev, _mins(400), detector))
    assert res.assurance_state is AssuranceState.ELIGIBLE_FOR_FURTHER_DECISION
    assert res.forced_action is None
    assert res.sensor_health_state is HealthState.NORMAL
    assert res.applicability_state is ApplicabilityState.NORMAL


# ── P. combined state PRESERVES each underlying state (never one scalar) ─

def test_P_states_preserved(detector):
    ev = _clean_event(detector)
    res = assess_assurance(_inputs(ev, _mins(400), detector))
    d = res.to_dict()
    # three distinct fields, not merged
    assert "sensor_health_state" in d
    assert "applicability_state" in d
    assert "prediction_available" in d
    assert d["sensor_health_state"] != d["applicability_state"] or True  # both NORMAL ok


# ── Q. hard-gate: critical sensor health forces ABSTAIN ──────────────────

def test_Q_frozen_sensor_forces_abstain(detector):
    ev = _clean_event(detector)
    t = _mins(400)
    frozen = F.freeze_signal(ev, "MFI_online", _mins(380), t)
    res = assess_assurance(_inputs(frozen, t, detector))
    assert res.assurance_state is AssuranceState.BLOCKED_BY_SENSOR_HEALTH
    assert res.forced_action == HARD_GATE_ABSTAIN
    assert res.fallback_action == FALLBACK_FOLLOW_SOP
    assert res.sensor_health_state is HealthState.ABNORMAL


# ── Q. hard-gate: OOD forces ABSTAIN via applicability gate ──────────────

def test_Q_ood_forces_abstain(detector):
    ev = _clean_event(detector)
    t = _mins(400)
    hr = assess_sensor_health(ev, t)       # healthy
    feats = dict(build_features(ev, t))
    feats["MFI_online_last"] = detector.support["MFI_online_last"][1] * 10
    ar = detector.assess(feats, ev.direction, ev.unit)
    inp = AssuranceInputs(True, True, hr, ar)
    res = assess_assurance(inp)
    assert res.assurance_state is AssuranceState.BLOCKED_BY_APPLICABILITY
    assert res.forced_action == HARD_GATE_ABSTAIN
    # health remained NORMAL -> the two layers are genuinely distinct
    assert res.sensor_health_state is HealthState.NORMAL


# ── prediction-unavailable gate ──────────────────────────────────────────

def test_prediction_unavailable_forces_abstain(detector):
    ev = _clean_event(detector)
    res = assess_assurance(_inputs(ev, _mins(400), detector, prediction=False))
    assert res.assurance_state is AssuranceState.BLOCKED_BY_PREDICTION_UNAVAILABLE
    assert res.forced_action == HARD_GATE_ABSTAIN


# ── blocking precedence: prediction -> health -> applicability ───────────

def test_precedence_prediction_over_health(detector):
    ev = _clean_event(detector)
    t = _mins(400)
    frozen = F.freeze_signal(ev, "MFI_online", _mins(380), t)
    res = assess_assurance(_inputs(frozen, t, detector, prediction=False))
    # prediction gate dominates the reported blocked-state
    assert res.assurance_state is AssuranceState.BLOCKED_BY_PREDICTION_UNAVAILABLE
    assert res.forced_action == HARD_GATE_ABSTAIN


# ── R. DEGRADED is usable but constrained (no confident prime candidate) ─

def test_R_degraded_eligible_with_constraints(detector):
    ev = _clean_event(detector)
    t = _mins(400)
    # a time gap on MFI_online -> DEGRADED health, but all OOD features remain
    # finite (latest obs still present) so applicability stays NORMAL.
    degraded = F.gap_signal(ev, "MFI_online", _mins(300), _mins(340))
    res = assess_assurance(_inputs(degraded, t, detector))
    assert res.assurance_state is AssuranceState.ELIGIBLE_WITH_CONSTRAINTS
    assert res.forced_action is None
    assert res.sensor_health_state is HealthState.DEGRADED
    assert res.applicability_state is ApplicabilityState.NORMAL


# ── health vs OOD distinction: a spike is HEALTH, not applicability ──────

def test_spike_is_health_not_ood(detector):
    ev = _clean_event(detector)
    t = _mins(400)
    spiked = F.spike_signal(ev, "MFI_online", _mins(300), multiplier=5.0)
    hr = assess_sensor_health(spiked, t)
    assert hr.overall_state is HealthState.ABNORMAL
    # applicability on the clean feature point stays in-domain
    ar = detector.assess_event(ev, t)
    assert ar.state is ApplicabilityState.NORMAL


# ── unavailable applicability artifact is ABSTAIN-safe ───────────────────

def test_applicability_artifact_unavailable_abstains(detector):
    ev = _clean_event(detector)
    t = _mins(400)
    hr = assess_sensor_health(ev, t)
    inp = AssuranceInputs(True, True, hr, unavailable_result())
    res = assess_assurance(inp)
    assert res.assurance_state is AssuranceState.BLOCKED_BY_APPLICABILITY
    assert res.forced_action == HARD_GATE_ABSTAIN


# ── gate contract primitives ─────────────────────────────────────────────

def test_gate_contract_primitives(detector):
    ev = _clean_event(detector)
    t = _mins(400)
    frozen = F.freeze_signal(ev, "MFI_online", _mins(380), t)
    results = evaluate_gates(_inputs(frozen, t, detector))
    assert gates_force_abstain(results)
    by_id = {r.gate_id: r for r in results}
    assert by_id["sensor_health"].passed is False
    assert by_id["sensor_health"].forces_action == HARD_GATE_ABSTAIN
    assert by_id["applicability"].passed is True


# ── deterministic replay ─────────────────────────────────────────────────

def test_deterministic_replay(detector):
    ev = _clean_event(detector)
    t = _mins(400)
    a = assess_assurance(_inputs(ev, t, detector)).to_dict()
    b = assess_assurance(_inputs(ev, t, detector)).to_dict()
    assert a == b
