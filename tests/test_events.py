"""Phase 3 tests — canonical event builder, boundary rules, UTC determinism."""
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift import ingestion as I
from gradeshift.events import build_event, compute_boundaries, BOUNDARY_RULES_PROVENANCE
from gradeshift.schemas import TransitionEvent, Intervention
from gradeshift.provenance import Provenance

START = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)


def _raw():
    return S.generate_episode("EVT-BLD", "A", "B", seed=3, start_time=START)


def test_builder_preserves_and_stamps():
    raw = _raw()
    iv = (Intervention(START + timedelta(minutes=30), "SENSOR_FLAG", "test"),)
    ev = build_event(raw, unit="GAIL-PE-1", interventions=iv,
                     versions={"data": "sim-gen-v1"})
    assert ev.unit == "GAIL-PE-1"
    assert ev.ended_at is not None and ev.ended_at >= ev.started_at
    assert ev.series == raw.series and ev.labs == raw.labs and ev.routing == raw.routing
    assert ev.interventions == iv
    assert ev.versions["boundary_rules"] == "boundary-rules-v1"
    assert ev.provenance is Provenance.SIMULATED


def test_builder_round_trip():
    ev = build_event(_raw(), unit="U1")
    assert TransitionEvent.from_dict(ev.to_dict()) == ev


def test_boundaries_ordered_and_marked_assumption():
    ev = build_event(_raw())
    b = compute_boundaries(ev)
    assert b.started_at <= b.transition_start
    assert b.transition_end is None or b.transition_end > b.transition_start
    assert b.transition_end is None or b.transition_end <= b.ended_at
    assert b.provenance is BOUNDARY_RULES_PROVENANCE  # declared SIMULATION ASSUMPTION
    assert b.provenance is Provenance.ASSUMPTION


def test_boundary_phase_classification():
    ev = build_event(_raw())
    b = compute_boundaries(ev)
    assert b.phase_at(b.started_at) == "PRE_BASELINE"
    assert b.phase_at(b.transition_start) == "ACTIVE_TRANSITION"
    if b.transition_end is not None:
        assert b.phase_at(b.transition_end) == "POST_STABILIZATION"


def test_transition_start_detects_setpoint_change():
    ev = build_event(_raw())
    b = compute_boundaries(ev)
    # generator switches at pre_min=60; detected start should be at/after that minute
    assert (b.transition_start - ev.started_at).total_seconds() / 60.0 >= 60.0


# L. malformed temporal ordering rejected (schema-level guard)
def test_L_malformed_temporal_ordering_rejected():
    with pytest.raises(ValueError):
        TransitionEvent("E", "A", "B", START, ended_at=START - timedelta(minutes=1))


# I. UTC normalization deterministic
def test_I_utc_normalization_deterministic():
    IST = timezone(timedelta(hours=5, minutes=30))
    naive = datetime(2026, 5, 1, 12, 0)
    a = I.to_utc(naive, assume_tz=IST)
    b = I.to_utc(naive, assume_tz=IST)
    assert a == b and a.tzinfo == timezone.utc and a.hour == 6 and a.minute == 30
