"""Phase 1 tests — schema round-trip and invalid-data rejection."""
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift.provenance import Provenance
from gradeshift.schemas import (
    ProvenancedObservation, LabSample, RoutingInterval, TransitionEvent,
    MaterialWindow, PredictionBundle, DecisionSnapshot, TransitionOutcome,
    TransitionMemoryRecord, ACTIONS,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return T0 + timedelta(minutes=n)


# ── round-trip ────────────────────────────────────────────────────────────

def test_observation_round_trip():
    o = ProvenancedObservation("MFI_inst", 7.9, "g/10min", T0)
    assert ProvenancedObservation.from_dict(o.to_dict()) == o


def test_lab_round_trip_and_latency():
    s = LabSample("s1", "B", 8.1, _mins(0), _mins(90))
    assert LabSample.from_dict(s.to_dict()) == s
    assert s.latency_min == 90.0


def test_event_round_trip_nested():
    ev = TransitionEvent(
        "evt-001", "A", "B", T0,
        series=(ProvenancedObservation("H2_ratio", 0.35, "-", T0),),
        labs=(LabSample("s1", "B", 8.0, _mins(0), _mins(90)),),
        routing=(RoutingInterval(_mins(0), _mins(60), "DOWNGRADE", 12.0),),
    )
    assert TransitionEvent.from_dict(ev.to_dict()) == ev
    assert ev.direction == "A->B"


def test_prediction_round_trip():
    p = PredictionBundle("evt-001", T0, 7.9, 7.6, 8.2, 0.90, 0.03, "gbm-v1", "conf-v1")
    assert PredictionBundle.from_dict(p.to_dict()) == p
    assert round(p.width, 4) == 0.6


def test_decision_round_trip():
    d = DecisionSnapshot(
        "evt-001", T0, "SAMPLE_NOW",
        expected_loss={a: float(i) for i, a in enumerate(ACTIONS)},
        reason_codes=("VOI_POSITIVE", "INTERVAL_STRADDLES_SPEC"),
        voi=1234.0, expiry=_mins(30), approver_role="QC",
        fallback_action="HOLD", versions={"model": "gbm-v1"},
    )
    assert DecisionSnapshot.from_dict(d.to_dict()) == d


def test_memory_round_trip():
    d = DecisionSnapshot("evt-001", T0, "PRIME_RELEASE_CANDIDATE", {"HOLD": 1.0},
                         ("INTERVAL_INSIDE_SPEC",), 0.0, _mins(30), "QC", "HOLD")
    oc = TransitionOutcome("evt-001", T0, 8.0, True, "PRIME_RELEASE_CANDIDATE",
                           False, False, 5000.0, _mins(120))
    rec = TransitionMemoryRecord("evt-001", "A->B", d, oc)
    assert TransitionMemoryRecord.from_dict(rec.to_dict()) == rec


# ── invalid-data rejection ──────────────────────────────────────────────────

def test_naive_timestamp_rejected():
    with pytest.raises(ValueError):
        ProvenancedObservation("x", 1.0, "-", datetime(2026, 1, 1, 12, 0))


def test_lab_result_before_collection_rejected():
    with pytest.raises(ValueError):
        LabSample("s", "B", 8.0, _mins(90), _mins(0))


def test_nonpositive_mfi_rejected():
    with pytest.raises(ValueError):
        LabSample("s", "B", 0.0, _mins(0), _mins(10))


def test_transition_to_same_grade_rejected():
    with pytest.raises(ValueError):
        TransitionEvent("e", "A", "A", T0)


def test_prediction_prob_bad_out_of_range_rejected():
    with pytest.raises(ValueError):
        PredictionBundle("e", T0, 8.0, 7.0, 9.0, 0.90, 1.5, "m", "c")


def test_prediction_inverted_interval_rejected():
    with pytest.raises(ValueError):
        PredictionBundle("e", T0, 8.0, 9.0, 7.0, 0.90, 0.1, "m", "c")


def test_decision_unknown_action_rejected():
    with pytest.raises(ValueError):
        DecisionSnapshot("e", T0, "RELEASE", {}, (), 0.0, _mins(5), "QC", "HOLD")


def test_decision_expiry_before_decision_rejected():
    with pytest.raises(ValueError):
        DecisionSnapshot("e", T0, "HOLD", {}, (), 0.0, _mins(-5), "QC", "HOLD")


def test_outcome_cannot_be_both_false_prime_and_false_hold():
    with pytest.raises(ValueError):
        TransitionOutcome("e", T0, 8.0, True, "HOLD", True, True, 0.0, _mins(10))


def test_memory_requires_matching_event_id():
    d = DecisionSnapshot("evt-001", T0, "HOLD", {}, (), 0.0, _mins(5), "QC", "HOLD")
    oc = TransitionOutcome("evt-999", T0, 8.0, True, "HOLD", False, False, 0.0, _mins(10))
    with pytest.raises(ValueError):
        TransitionMemoryRecord("evt-001", "A->B", d, oc)
