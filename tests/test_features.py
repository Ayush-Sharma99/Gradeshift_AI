"""Phase 5 tests — feature pipeline provenance and ADVERSARIAL no-future invariance.

The single most important integrity property: the feature vector at decision time
t is invariant to ALL information strictly after t.
"""
from datetime import datetime, timedelta, timezone

import math
import pytest

from gradeshift import simulate as S
from gradeshift.features import (
    FEATURE_NAMES, FEATURE_SPECS, FEATURE_SCHEMA_VERSION, build_features,
)
from gradeshift.schemas import (
    TransitionEvent, ProvenancedObservation, LabSample, RoutingInterval, Intervention,
)

BASE = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


def _episode():
    return S.generate_episode("EP-FEAT", "A", "B", seed=11, start_time=BASE,
                              params=S.EpisodeParams())


def test_specs_cover_vector_and_versioned():
    spec_names = [s.name for s in FEATURE_SPECS]
    assert spec_names == FEATURE_NAMES                       # one spec per feature, in order
    assert len(set(spec_names)) == len(spec_names)           # unique
    assert all(s.version == FEATURE_SCHEMA_VERSION for s in FEATURE_SPECS)
    feats = build_features(_episode(), _mins(300))
    assert set(feats) == set(FEATURE_NAMES)
    assert all(isinstance(v, float) for v in feats.values())


def test_deterministic():
    ev = _episode()
    assert build_features(ev, _mins(300)) == build_features(ev, _mins(300))


def _with_extra(ev, *, series=(), labs=(), routing=None, interventions=()):
    return TransitionEvent(
        ev.event_id, ev.grade_from, ev.grade_to, ev.started_at,
        series=ev.series + tuple(series), labs=ev.labs + tuple(labs),
        routing=tuple(routing) if routing is not None else ev.routing,
        interventions=ev.interventions + tuple(interventions),
        ended_at=ev.ended_at, unit=ev.unit, versions=ev.versions)


# ── Adversarial no-future tests (features at t must not move) ──────────────

def test_no_future_process_rows():
    ev = _episode()
    t = _mins(300)
    base = build_features(ev, t)
    future = _with_extra(ev, series=[
        ProvenancedObservation("MFI_online", 999.0, "g/10min", _mins(600)),
        ProvenancedObservation("H2_ratio", 999.0, "-", _mins(600)),
        ProvenancedObservation("bed_temp", 999.0, "degC", _mins(600))])
    assert build_features(future, t) == base


def test_no_future_lab_result():
    ev = _episode()
    t = _mins(300)
    base = build_features(ev, t)
    future = _with_extra(ev, labs=[
        LabSample("future-lab", "B", 999.0, _mins(305), _mins(360))])  # collected+result after t
    assert build_features(future, t) == base


def test_no_future_routing_switch():
    ev = _episode()
    t = _mins(300)
    base = build_features(ev, t)
    # replace routing with an extra future switch; nothing before t changes
    fut_routing = list(ev.routing) + [RoutingInterval(_mins(500), _mins(560), "PRIME", 99.0)]
    future = _with_extra(ev, routing=fut_routing)
    assert build_features(future, t) == base


def test_no_future_intervention():
    ev = _episode()
    t = _mins(300)
    base = build_features(ev, t)
    future = _with_extra(ev, interventions=[
        Intervention(_mins(450), "ROUTING_OVERRIDE", "future")])
    assert build_features(future, t) == base


def test_future_outcome_cannot_enter_features():
    # The target/outcome is never a feature source; adding a late lab (the truth)
    # does not alter the as-of feature vector.
    ev = _episode()
    t = _mins(240)
    base = build_features(ev, t)
    future = _with_extra(ev, labs=[LabSample("truth", "B", 8.0, _mins(260), _mins(350))])
    assert build_features(future, t) == base


def test_window_feature_excludes_future_within_lookback():
    # A 30-min rolling mean at t must not include a value at t + 1 minute.
    ev = _episode()
    t = _mins(300)
    base = build_features(ev, t)["MFI_online_mean_30"]
    future = _with_extra(ev, series=[
        ProvenancedObservation("MFI_online", 999.0, "g/10min", _mins(301))])
    assert build_features(future, t)["MFI_online_mean_30"] == base


def test_missing_evidence_is_nan_not_imputed():
    # Very early t: no lab resulted yet -> lab features are NaN, not a future value.
    ev = _episode()
    feats = build_features(ev, _mins(5))
    assert math.isnan(feats["lab_last_mfi"])
    assert feats["lab_resulted_count"] == 0.0
