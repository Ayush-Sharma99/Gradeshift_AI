"""Phase 4 tests — material identity / residence-time mapping (SIMULATED).

Covers RTD kernels, separate transport delay, as-of causal safety, mass
conservation and routing-boundary mass split, uncertainty exposure, determinism
and serialization. The kernels are illustrative assumptions, NOT plant-measured.
"""
import math
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift.schemas import RoutingInterval, TransitionEvent
from gradeshift.provenance import Provenance
from gradeshift.material_identity import (
    CSTRKernel, ErlangKernel, MaterialMapParams, build_kernel,
    map_material, reconcile_episode, MAPPING_PROVENANCE,
)
from gradeshift.schemas import MaterialWindow

BASE = datetime(2026, 7, 1, 0, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


def _routed_event(intervals, ended_min=200):
    """A minimal transition event carrying only routing, for mass tests."""
    routing = tuple(RoutingInterval(_mins(a), _mins(b), dest, rate)
                    for (a, b, dest, rate) in intervals)
    return TransitionEvent("EVT-MAT", "A", "B", BASE, routing=routing,
                           ended_at=_mins(ended_min))


# A. CSTR kernel matches the analytic exponential RTD.
def test_A_cstr_analytic():
    k = CSTRKernel(150.0)
    assert k.mean() == pytest.approx(150.0)
    assert k.var() == pytest.approx(150.0 ** 2)
    assert k.std() == pytest.approx(150.0)
    assert k.cdf(150.0) == pytest.approx(1.0 - 1.0 / math.e, rel=1e-9)
    assert k.quantile(0.5) == pytest.approx(150.0 * math.log(2.0), rel=1e-9)
    assert k.pdf(0.0) == pytest.approx(1.0 / 150.0, rel=1e-9)


# B. RTD normalization / monotonic CDF; Erlang moments match tanks-in-series.
def test_B_mass_normalization_and_erlang_moments():
    k = CSTRKernel(120.0)
    assert k.cdf(0.0) == 0.0
    assert k.cdf(1e7) == pytest.approx(1.0, abs=1e-6)
    assert k.cdf(k.quantile(0.9)) == pytest.approx(0.9, rel=1e-9)
    e = ErlangKernel(120.0, k=4)
    assert e.mean() == pytest.approx(120.0)
    assert e.var() == pytest.approx(120.0 ** 2 / 4)
    # k=1 Erlang collapses to the single CSTR
    assert ErlangKernel(90.0, 1).var() == pytest.approx(CSTRKernel(90.0).var())


# C. Larger residence time shifts production support earlier and raises mean age.
def test_C_residence_shift():
    ev = _routed_event([(0, 200, "DOWNGRADE", 12.0)])
    t = _mins(150)
    w_short = map_material(ev, t, MaterialMapParams(tau_min=100.0))
    w_long = map_material(ev, t, MaterialMapParams(tau_min=300.0))
    assert w_long.mean_age_min > w_short.mean_age_min
    # production of the longer-residence material is pushed further into the past
    assert w_long.production_time_start < w_short.production_time_start
    assert w_long.production_time_end < w_short.production_time_end


# D. Transport delay shifts the mean but adds NO spread; residence drives spread.
def test_D_transport_separate_from_residence():
    ev = _routed_event([(0, 200, "DOWNGRADE", 12.0)])
    t = _mins(150)
    base = map_material(ev, t, MaterialMapParams(tau_min=150.0, transport_delay_min=10.0))
    more_transport = map_material(ev, t, MaterialMapParams(tau_min=150.0, transport_delay_min=40.0))
    more_tau = map_material(ev, t, MaterialMapParams(tau_min=250.0, transport_delay_min=10.0))
    # extra transport: mean age rises by exactly the delta, spread unchanged
    assert more_transport.mean_age_min == pytest.approx(base.mean_age_min + 30.0)
    assert more_transport.age_spread_min == pytest.approx(base.age_spread_min)
    # extra residence: BOTH mean and spread rise
    assert more_tau.mean_age_min > base.mean_age_min
    assert more_tau.age_spread_min > base.age_spread_min


# E. Mass conservation: reconciled episode mass == produced == routed (within tol).
def test_E_mass_conservation():
    ev = _routed_event([(0, 100, "DOWNGRADE", 12.0), (100, 200, "PRIME", 12.0)])
    w = reconcile_episode(ev)
    routed = sum(r.mass_tonnes for r in ev.routing)
    assert w.mapped_mass_tonnes == pytest.approx(routed, rel=1e-9)
    assert sum(w.destination_mass.values()) == pytest.approx(routed, rel=1e-9)
    # 200 min at 12 t/h = 40 t
    assert w.mapped_mass_tonnes == pytest.approx(40.0, rel=1e-9)


# F. A window spanning a routing boundary SPLITS mass across destinations.
def test_F_routing_boundary_split():
    ev = _routed_event([(0, 100, "DOWNGRADE", 12.0), (100, 200, "PRIME", 12.0)])
    # band [50, 150] straddles the boundary at 100
    w = map_material(ev, _mins(150), MaterialMapParams(window_min=100.0),
                     routing=ev.routing)
    dm = w.destination_mass
    assert set(dm) == {"DOWNGRADE", "PRIME"}
    assert dm["DOWNGRADE"] > 0 and dm["PRIME"] > 0
    assert dm["DOWNGRADE"] == pytest.approx(10.0, rel=1e-9)  # 50 min @12
    assert dm["PRIME"] == pytest.approx(10.0, rel=1e-9)
    assert w.mapped_mass_tonnes == pytest.approx(20.0, rel=1e-9)


# G. Partial overlap counts only the overlapping mass, not the whole interval.
def test_G_partial_overlap():
    ev = _routed_event([(0, 100, "DOWNGRADE", 12.0)])
    # band [50, 150] overlaps the interval only on [50, 100] = 50 min
    w = map_material(ev, _mins(150), MaterialMapParams(window_min=100.0),
                     routing=ev.routing)
    assert w.mapped_mass_tonnes == pytest.approx(10.0, rel=1e-9)
    assert w.destination_mass == {"DOWNGRADE": pytest.approx(10.0, rel=1e-9)}


# H. No future routing leak: a future switch is invisible to an as-of decision.
def test_H_no_future_routing_leak():
    ev = _routed_event([(0, 100, "DOWNGRADE", 12.0), (100, 200, "PRIME", 12.0)])
    w = map_material(ev, _mins(80), MaterialMapParams(window_min=60.0))  # as-of visible routing
    assert "PRIME" not in w.destination_mass           # future route hidden
    assert set(w.destination_mass) == {"DOWNGRADE"}
    assert w.material_time_end == _mins(80)            # band never reaches past t


# I. No future production-rate leak: a post-t rate change does not affect the map.
def test_I_no_future_production_leak():
    with_future = _routed_event([(0, 100, "DOWNGRADE", 12.0),
                                 (100, 200, "DOWNGRADE", 999.0)])  # future rate spike
    without_future = _routed_event([(0, 100, "DOWNGRADE", 12.0)])
    t = _mins(80)
    a = map_material(with_future, t, MaterialMapParams(window_min=60.0))
    b = map_material(without_future, t, MaterialMapParams(window_min=60.0))
    assert a.mapped_mass_tonnes == pytest.approx(b.mapped_mass_tonnes, rel=1e-9)
    # 60 min @ 12 t/h = 12 t, NOT inflated by the 999 t/h future interval
    assert a.mapped_mass_tonnes == pytest.approx(12.0, rel=1e-9)


# J. Deterministic — identical inputs give identical snapshots.
def test_J_deterministic():
    ev = _routed_event([(0, 100, "DOWNGRADE", 12.0), (100, 200, "PRIME", 12.0)])
    a = map_material(ev, _mins(120))
    b = map_material(ev, _mins(120))
    assert a.to_dict() == b.to_dict()


# K. Serialization round-trip.
def test_K_round_trip():
    ev = _routed_event([(0, 100, "DOWNGRADE", 12.0), (100, 200, "PRIME", 12.0)])
    w = map_material(ev, _mins(150), MaterialMapParams(kernel="ERLANG", erlang_k=3,
                                                       window_min=120.0))
    assert MaterialWindow.from_dict(w.to_dict()) == w


# L. Invalid kernel / mapping parameters rejected.
def test_L_invalid_params_rejected():
    with pytest.raises(ValueError):
        CSTRKernel(0.0)
    with pytest.raises(ValueError):
        ErlangKernel(150.0, 0)
    with pytest.raises(ValueError):
        MaterialMapParams(tau_min=-1.0)
    with pytest.raises(ValueError):
        MaterialMapParams(coverage=1.0)
    with pytest.raises(ValueError):
        MaterialMapParams(window_min=0.0)
    with pytest.raises(ValueError):
        build_kernel(MaterialMapParams(kernel="MYSTERY"))


# M. Zero / near-zero flow yields zero mass, never negative.
def test_M_zero_flow_no_negative_mass():
    ev = _routed_event([(0, 200, "DOWNGRADE", 0.0)])
    w = map_material(ev, _mins(150), MaterialMapParams(window_min=100.0),
                     routing=ev.routing)
    assert w.mapped_mass_tonnes == 0.0
    assert all(m >= 0 for m in w.destination_mass.values())
    tiny = _routed_event([(0, 200, "DOWNGRADE", 1e-9)])
    wt = map_material(tiny, _mins(150), MaterialMapParams(window_min=100.0),
                      routing=tiny.routing)
    assert wt.mapped_mass_tonnes >= 0.0


# N. Residence-time uncertainty increases with configured dispersion.
def test_N_uncertainty_exposed():
    assert CSTRKernel(200.0).std() > CSTRKernel(100.0).std()
    # fewer tanks in series = wider RTD = more uncertainty
    assert ErlangKernel(150.0, 2).std() > ErlangKernel(150.0, 10).std()
    ev = _routed_event([(0, 200, "DOWNGRADE", 12.0)])
    wide = map_material(ev, _mins(150), MaterialMapParams(kernel="ERLANG", erlang_k=2))
    narrow = map_material(ev, _mins(150), MaterialMapParams(kernel="ERLANG", erlang_k=10))
    assert wide.age_spread_min > narrow.age_spread_min


# O. End-to-end on a real simulated episode: causal, two-axis, provenance-labelled.
def test_O_real_episode_mapping():
    ev = S.generate_episode("EVT-RT", "A", "B", seed=7, start_time=BASE,
                            params=S.EpisodeParams())
    t = ev.started_at + timedelta(minutes=300)
    w = map_material(ev, t)
    assert w.mapping_provenance is MAPPING_PROVENANCE
    assert w.mapping_provenance is Provenance.ASSUMPTION   # NOT measured/validated
    assert w.kernel == "CSTR" and w.version
    # two DISTINCT time axes: production precedes downstream material time
    assert w.production_time_end < w.material_time_end
    assert w.mean_age_min > w.transport_delay_min          # residence adds to transport
    # as-of safe: only routing that has started by t contributes
    for dest, mass in w.destination_mass.items():
        assert mass >= 0
    # mapped mass cannot exceed what was produced over the whole episode
    assert w.mapped_mass_tonnes <= S.produced_mass_tonnes(S.EpisodeParams()) + 1e-6
