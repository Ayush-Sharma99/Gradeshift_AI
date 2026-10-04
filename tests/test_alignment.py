"""Phase 3 tests — as-of visibility firewall and adversarial leakage checks."""
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift.alignment import as_of, AsOfSnapshot, DecisionContext, PendingLab
from gradeshift.schemas import (
    ProvenancedObservation, LabSample, RoutingInterval, Intervention, TransitionEvent,
)
from gradeshift.provenance import Provenance

T0 = datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return T0 + timedelta(minutes=n)


def _event() -> TransitionEvent:
    series = (
        ProvenancedObservation("MFI_online", 0.30, "g/10min", _mins(0)),
        ProvenancedObservation("MFI_online", 4.00, "g/10min", _mins(100)),
        ProvenancedObservation("MFI_online", 7.95, "g/10min", _mins(300)),   # future obs
    )
    labs = (
        LabSample("L0", "B", 0.31, _mins(0), _mins(90)),      # resulted by t=120
        LabSample("L1", "B", 4.10, _mins(100), _mins(190)),   # collected<=120, result>120 -> pending
        LabSample("L2", "B", 7.90, _mins(250), _mins(340)),   # collected after t=120 -> invisible
    )
    routing = (
        RoutingInterval(_mins(0), _mins(200), "DOWNGRADE", 12.0),   # straddles t=120
        RoutingInterval(_mins(200), _mins(360), "PRIME", 12.0),     # future -> invisible
    )
    interventions = (
        Intervention(_mins(60), "SENSOR_FLAG", "noisy analyzer"),
        Intervention(_mins(240), "ROUTING_OVERRIDE", "future"),     # future -> invisible
    )
    return TransitionEvent("EVT-AO", "A", "B", T0, series=series, labs=labs,
                           routing=routing, interventions=interventions)


T = _mins(120)


# A. lab result with result_at > t invisible (L1 result at 190)
def test_A_future_lab_result_invisible():
    snap = as_of(_event(), T)
    assert all(s.sample_id != "L1" for s in snap.lab_results)


# B. collected <= t but result_at > t: still invisible AS A RESULT (pending, no value)
def test_B_collected_but_unresulted_is_pending_without_value():
    snap = as_of(_event(), T)
    pend_ids = {p.sample_id for p in snap.pending_labs}
    assert "L1" in pend_ids
    # structurally impossible to read a result off a PendingLab
    p = next(p for p in snap.pending_labs if p.sample_id == "L1")
    assert not hasattr(p, "mfi")


# C. result_at <= t becomes visible (L0 resulted at 90)
def test_C_resulted_lab_visible():
    snap = as_of(_event(), T)
    assert any(s.sample_id == "L0" and s.mfi == 0.31 for s in snap.lab_results)


# D. future process observation invisible (obs at 300)
def test_D_future_observation_invisible():
    snap = as_of(_event(), T)
    assert all(o.timestamp <= T for o in snap.observations)
    assert max(o.timestamp for o in snap.observations) == _mins(100)


# E. future routing change invisible; ongoing interval clipped (no future switch leak)
def test_E_future_routing_invisible_and_clipped():
    snap = as_of(_event(), T)
    dests = [r.destination for r in snap.routing_visible]
    assert "PRIME" not in dests                      # the future switch is hidden
    dg = next(r for r in snap.routing_visible if r.destination == "DOWNGRADE")
    assert dg.ongoing is True and dg.end_as_of == T  # clipped to t, true end (200) not revealed


# F. post-decision intervention invisible
def test_F_future_intervention_invisible():
    snap = as_of(_event(), T)
    kinds = [iv.kind for iv in snap.interventions]
    assert "SENSOR_FLAG" in kinds and "ROUTING_OVERRIDE" not in kinds


# G. the eventual transition outcome is never in a decision context
def test_G_outcome_never_present():
    snap = as_of(_event(), T)
    d = snap.to_dict()
    assert "outcome" not in d and "realized_value" not in d
    assert not any("outcome" in k for k in d)


# J. deterministic / reproducible snapshots
def test_J_snapshot_deterministic():
    a = as_of(_event(), T)
    b = as_of(_event(), T)
    assert a.to_dict() == b.to_dict()


# K. provenance survives + lineage traces every value
def test_K_provenance_and_lineage():
    snap = as_of(_event(), T)
    assert all(o.provenance is Provenance.SIMULATED for o in snap.observations)
    lin = snap.lineage()
    kinds = {row["kind"] for row in lin}
    assert {"observation", "lab_result", "lab_pending", "routing"} <= kinds
    assert all("provenance" in row and "original_timestamp" in row for row in lin)


def test_as_of_requires_utc():
    with pytest.raises(ValueError):
        as_of(_event(), datetime(2026, 4, 1, 2, 0))  # naive


def test_monotonic_visibility_on_real_episode():
    # as t advances, the count of visible lab results is non-decreasing
    ev = S.generate_episode("EVT-MONO", "A", "B", seed=5,
                            start_time=T0, params=S.EpisodeParams())
    counts = [len(as_of(ev, T0 + timedelta(minutes=m)).lab_results) for m in range(0, 900, 120)]
    assert all(b >= a for a, b in zip(counts, counts[1:]))
