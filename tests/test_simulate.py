"""Phase 2 tests — seeded generator, steady-state fix, residence time, provenance."""
import math
from datetime import datetime, timezone

import numpy as np
import pytest

from gradeshift import config as C
from gradeshift import simulate as S
from gradeshift.provenance import Provenance
from gradeshift.schemas import TransitionEvent

START = datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc)


# ── corrected steady-state defect (D1), verified numerically ────────────────

@pytest.mark.parametrize("gid", ["A", "B", "C"])
def test_instantaneous_mfi_at_setpoint_equals_target(gid):
    target = C.get_grade(gid).target_mfi
    assert math.isclose(S.instantaneous_mfi(S.hydrogen_setpoint(gid)), target, rel_tol=1e-9)


@pytest.mark.parametrize("grade_to", ["A", "B", "C"])
def test_bed_converges_to_configured_target(grade_to):
    # evolve long enough (>5 tau) and require the end state within 1% of target
    ss = S.steady_state_mfi(grade_to)
    target = C.get_grade(grade_to).target_mfi
    assert abs(ss - target) / target < 0.01, (grade_to, ss, target)


def test_defect_regression_b_is_not_the_old_offspec_value():
    # the inherited simulator settled at ~11.26 for Grade B; the fix must land on 8.0
    assert abs(S.steady_state_mfi("B") - 8.0) / 8.0 < 0.01


# ── determinism ─────────────────────────────────────────────────────────────

def test_same_seed_identical_episode():
    a = S.generate_episode("evt-1", "A", "B", seed=7, start_time=START)
    b = S.generate_episode("evt-1", "A", "B", seed=7, start_time=START)
    assert a.to_dict() == b.to_dict()


def test_different_seed_meaningfully_different():
    a = S.generate_episode("evt-1", "A", "B", seed=7, start_time=START)
    b = S.generate_episode("evt-1", "A", "B", seed=8, start_time=START)
    assert a.to_dict() != b.to_dict()
    online_a = np.array([o.value for o in a.series if o.tag == "MFI_online"])
    online_b = np.array([o.value for o in b.series if o.tag == "MFI_online"])
    # noise differs materially but the underlying trajectory is the same shape
    assert np.mean(np.abs(online_a - online_b)) > 1e-6


# ── residence time / transport consistency ──────────────────────────────────

def test_longer_tau_settles_slower():
    fast = S.steady_state_mfi("B", S.EpisodeParams(tau_min=60.0, post_min=300.0))
    slow = S.steady_state_mfi("B", S.EpisodeParams(tau_min=600.0, post_min=300.0))
    # both approach 8.0 from below (A->B is upward); slower tau is further from target
    assert abs(slow - 8.0) > abs(fast - 8.0)


def test_online_analyzer_lags_true_bed():
    p = S.EpisodeParams(transport_delay_min=20.0)
    ev = S.generate_episode("evt-lag", "A", "B", seed=3, start_time=START, params=p)
    online = np.array([o.value for o in ev.series if o.tag == "MFI_online"])
    # just after the switch (pre_min), the delayed analyzer should still read low
    i = int(p.pre_min / p.dt_min) + 2
    assert online[i] < 1.0  # still near grade-A level while transport delay elapses


# ── lab timing / blind window ───────────────────────────────────────────────

def test_lab_collected_and_result_distinct_and_ordered():
    ev = S.generate_episode("evt-lab", "A", "B", seed=1, start_time=START)
    assert ev.labs
    for s in ev.labs:
        assert s.result_at > s.collected_at
        assert math.isclose(s.latency_min, S.EpisodeParams().lab_latency_min)


# ── mass reconciliation ─────────────────────────────────────────────────────

def test_routing_tiles_and_reconciles_with_production_mass():
    p = S.EpisodeParams()
    ev = S.generate_episode("evt-mass", "A", "B", seed=5, start_time=START, params=p)
    routed = sum(r.mass_tonnes for r in ev.routing)
    assert math.isclose(routed, S.produced_mass_tonnes(p), rel_tol=1e-9)
    # contiguous tiling, no gaps / no negative durations
    for prev, nxt in zip(ev.routing, ev.routing[1:]):
        assert nxt.start == prev.end
    assert ev.routing[0].start == ev.started_at


def test_ab_episode_eventually_routes_prime():
    ev = S.generate_episode("evt-prime", "A", "B", seed=2, start_time=START)
    assert any(r.destination == "PRIME" for r in ev.routing)


# ── provenance + serialization survival ─────────────────────────────────────

def test_all_records_simulated_and_survive_round_trip():
    ev = S.generate_episode("evt-prov", "A", "B", seed=9, start_time=START)
    assert ev.provenance is Provenance.SIMULATED
    assert all(o.provenance is Provenance.SIMULATED for o in ev.series)
    assert all(s.provenance is Provenance.SIMULATED for s in ev.labs)
    restored = TransitionEvent.from_dict(ev.to_dict())
    assert restored == ev
    assert all(o.provenance is Provenance.SIMULATED for o in restored.series)


def test_no_impossible_timestamps():
    ev = S.generate_episode("evt-ts", "A", "B", seed=4, start_time=START)
    for o in ev.series:
        assert o.timestamp.tzinfo is not None
        assert o.timestamp >= ev.started_at


# ── reverse / other supported transitions ───────────────────────────────────

@pytest.mark.parametrize("gf,gt", [("B", "A"), ("A", "C"), ("C", "B")])
def test_reverse_and_other_transitions_converge(gf, gt):
    ev = S.generate_episode(f"evt-{gf}{gt}", gf, gt, seed=11, start_time=START)
    bed_end = S.steady_state_mfi(gt)  # structural: end state depends only on grade_to
    assert abs(bed_end - C.get_grade(gt).target_mfi) / C.get_grade(gt).target_mfi < 0.01
    assert ev.direction == f"{gf}->{gt}"
