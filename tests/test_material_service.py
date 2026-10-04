"""Phase 8 tests — MATERIAL IDENTITY as a decision input (adversarial A–O).

These exercise the thin decision-service layer `resolve_material_window` that
operationalises the EXISTING Phase-4 mapper (`material_identity.map_material`).
They do NOT re-test the kernels/transport maths (Phase 4 owns that); they test
the DECISION semantics: route dominance, mass reconciliation, support, mapping
quality + reason codes, as-of causality, and the eligibility interface.

Everything is SIMULATION/ASSUMPTION — no HMEL validation is implied.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift.material_identity import MaterialMapParams, RESIDENCE_MODEL_VERSION
from gradeshift.schemas import RoutingInterval, PredictionBundle
from gradeshift.material_service import (
    resolve_material_window, DecisionContext, MappingQuality,
    MaterialResolution, MaterialEligibilityResult, MaterialQualityLineage,
    MR_OK, MR_PARTIAL, MR_INSUFFICIENT, MR_ROUTE_UNKNOWN, MR_ROUTE_AMBIGUOUS,
    MR_MASS_UNRECONCILED, MR_ZERO_FLOW, MR_VERSION_MISMATCH, BLOCKING_CODES,
    MATERIAL_SERVICE_VERSION,
)

BASE = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


def _ev(routing, eid="EP-MS"):
    """A valid episode with its routing swapped for a controlled one."""
    ev = S.generate_episode(eid, "A", "B", seed=5, start_time=BASE)
    return replace(ev, routing=tuple(routing), ended_at=max(r.end for r in routing))


# window_min 60, tau 150 -> age_spread 150. A boundary within 150 min of the
# band triggers residence-driven ambiguity, so place single-route boundaries
# far away in the "clean" cases.
_CTX = DecisionContext(target_grade="B", spec_band=(2.0, 4.0))


# ── A. window within one route -> WELL_SUPPORTED, route known ────────────
def test_A_single_route():
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    r = resolve_material_window(ev, _CTX, _mins(600))
    assert r.mapping_quality is MappingQuality.WELL_SUPPORTED
    assert r.route_known and r.primary_destination == "DOWNGRADE"
    assert r.reason_codes == (MR_OK,)
    assert r.route_ambiguity == 0.0
    assert r.mass_reconciliation.reconciled


# ── B. window crosses a routing boundary -> both destinations retained ───
def test_B_route_boundary_split():
    # boundary at 600; band [540,600] touches it. Give PRIME a sliver so the
    # band is dominated by DOWNGRADE but the switch is adjacent.
    ev = _ev([RoutingInterval(_mins(0), _mins(600), "DOWNGRADE", 12.0),
              RoutingInterval(_mins(600), _mins(1200), "PRIME", 12.0)])
    r = resolve_material_window(ev, _CTX, _mins(630))  # band [570,630] straddles 600
    assert set(r.route_shares) == {"DOWNGRADE", "PRIME"}
    # mass is NOT collapsed onto one route
    assert len(r.material_window.destinations) == 2


# ── C. destination changes during the window -> ambiguous, no silent pick ─
def test_C_destination_change_ambiguous():
    # near-equal split across the boundary -> dominant share below threshold
    ev = _ev([RoutingInterval(_mins(0), _mins(600), "DOWNGRADE", 12.0),
              RoutingInterval(_mins(600), _mins(1200), "PRIME", 12.0)])
    r = resolve_material_window(ev, _CTX, _mins(630))  # ~30/30 min split
    assert r.mapping_quality is MappingQuality.AMBIGUOUS
    assert MR_ROUTE_AMBIGUOUS in r.reason_codes
    # the wrong destination is NEVER silently chosen
    assert r.route_known is False
    assert r.primary_destination is None


# ── D. only part of the window is mapped -> partial / unreconciled ───────
def test_D_incomplete_mapping():
    # routing covers only the first half of the band -> a routing gap inside it
    ev = _ev([RoutingInterval(_mins(0), _mins(570), "DOWNGRADE", 12.0)])
    r = resolve_material_window(ev, _CTX, _mins(600))  # band [540,600]; gap 570-600
    assert r.support_fraction < 1.0
    assert MR_PARTIAL in r.reason_codes or MR_INSUFFICIENT in r.reason_codes
    # unexplained (unrouted) mass inside the band is surfaced, not hidden
    assert r.mass_reconciliation.unexplained_mass_tonnes > 0 or \
        r.mapping_quality is MappingQuality.UNAVAILABLE


# ── E. residence-time uncertainty causes route ambiguity ─────────────────
def test_E_residence_spread_ambiguity():
    # single dominant destination in the band, but a real upstream switch sits
    # within age_spread (150 min) of the band -> flagged AMBIGUOUS via residence.
    ev = _ev([RoutingInterval(_mins(0), _mins(500), "PRIME", 12.0),
              RoutingInterval(_mins(500), _mins(1200), "DOWNGRADE", 12.0)])
    r = resolve_material_window(ev, _CTX, _mins(620))  # band [560,620]; switch @500 within 150
    assert r.boundary_within_residence_spread is True
    assert r.mapping_quality is MappingQuality.AMBIGUOUS
    assert MR_ROUTE_AMBIGUOUS in r.reason_codes
    assert r.route_known is False and r.primary_destination is None


# ── F. production rate changes across the window (same destination) ──────
def test_F_rate_change_same_dest():
    ev = _ev([RoutingInterval(_mins(0), _mins(585), "DOWNGRADE", 10.0),
              RoutingInterval(_mins(585), _mins(1200), "DOWNGRADE", 20.0)])
    r = resolve_material_window(ev, _CTX, _mins(600))  # band [540,600]
    assert set(r.route_shares) == {"DOWNGRADE"}
    assert r.route_known and r.primary_destination == "DOWNGRADE"


# ── G. decision before enough material support -> UNAVAILABLE (blocking) ─
def test_G_insufficient_support_unavailable():
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    r = resolve_material_window(ev, _CTX, _mins(10))  # band clipped to [0,10] of 60
    assert r.mapping_quality is MappingQuality.UNAVAILABLE
    assert MR_INSUFFICIENT in r.reason_codes
    assert r.to_eligibility().is_blocking


# ── H. single-route eligibility is non-blocking ──────────────────────────
def test_H_eligibility_non_blocking():
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    elig = resolve_material_window(ev, _CTX, _mins(600)).to_eligibility()
    assert isinstance(elig, MaterialEligibilityResult)
    assert elig.material_window_available and not elig.is_blocking


# ── I. future ROUTING cannot change the as-of material map ───────────────
def test_I_future_routing_invariance():
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    t = _mins(600)
    base = resolve_material_window(ev, _CTX, t).to_dict()
    # append a PRIME switch entirely AFTER t
    fut = replace(ev, routing=ev.routing + (RoutingInterval(_mins(900), _mins(1500), "PRIME", 99.0),),
                  ended_at=_mins(1500))
    after = resolve_material_window(fut, _CTX, t).to_dict()
    assert after["material_window"]["destinations"] == base["material_window"]["destinations"]
    assert after["mapping_quality"] == base["mapping_quality"]
    assert after["route_shares"] == base["route_shares"]


# ── J. future THROUGHPUT (rate change after t) cannot change the map ─────
def test_J_future_throughput_invariance():
    ev = _ev([RoutingInterval(_mins(0), _mins(700), "DOWNGRADE", 12.0),
              RoutingInterval(_mins(700), _mins(1200), "DOWNGRADE", 50.0)])
    t = _mins(600)
    base = resolve_material_window(ev, _CTX, t)
    # the post-t rate jump must not alter mapped mass as-of t
    assert base.mass_reconciliation.mapped_mass_tonnes == pytest.approx(12.0)


# ── K. deterministic replay ──────────────────────────────────────────────
def test_K_deterministic_replay():
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    t = _mins(600)
    a = resolve_material_window(ev, _CTX, t).to_dict()
    b = resolve_material_window(ev, _CTX, t).to_dict()
    assert a == b


# ── L. serialization round-trip is stable ────────────────────────────────
def test_L_serialization_roundtrip():
    import json
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    r = resolve_material_window(ev, _CTX, _mins(600))
    s = json.dumps(r.to_dict(), default=str)
    assert json.loads(s)["mapping_quality"] == r.mapping_quality.value
    # eligibility and context also serialize
    json.dumps(r.to_eligibility().to_dict())
    json.dumps(_CTX.to_dict())


# ── M. mass conservation: mapped == sum of destination components ────────
def test_M_mass_conservation():
    ev = _ev([RoutingInterval(_mins(0), _mins(600), "DOWNGRADE", 12.0),
              RoutingInterval(_mins(600), _mins(1200), "PRIME", 8.0)])
    r = resolve_material_window(ev, _CTX, _mins(630))
    comp = sum(m for _, m in r.material_window.destinations)
    assert comp == pytest.approx(r.mass_reconciliation.mapped_mass_tonnes)


# ── N. invalid / negative parameters are rejected ────────────────────────
def test_N_invalid_parameters():
    with pytest.raises(ValueError):
        DecisionContext(min_support_fraction=0.0)
    with pytest.raises(ValueError):
        DecisionContext(route_dominance_threshold=1.5)
    with pytest.raises(ValueError):
        DecisionContext(mass_tol_frac=-0.1)
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    with pytest.raises(ValueError):
        resolve_material_window(ev, _CTX, None)  # decision_time required


# ── zero-flow: no routing visible as-of t -> UNAVAILABLE (blocking) ──────
def test_zero_flow_unavailable():
    ev = _ev([RoutingInterval(_mins(900), _mins(1200), "PRIME", 12.0)])  # starts after t
    r = resolve_material_window(ev, _CTX, _mins(600))
    assert r.mapping_quality is MappingQuality.UNAVAILABLE
    assert MR_ZERO_FLOW in r.reason_codes and MR_ROUTE_UNKNOWN in r.reason_codes
    assert r.to_eligibility().is_blocking


# ── uncertainty is exposed, never collapsed to a probability ─────────────
def test_uncertainty_exposed_not_probability():
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    d = resolve_material_window(ev, _CTX, _mins(600)).to_dict()
    assert "residence_uncertainty_min" in d
    assert "route_ambiguity" in d
    assert "mapping_quality" in d          # a qualitative state ...
    assert "prob_good" not in d            # ... never a fake probability
    assert d["mapping_quality"] in {q.value for q in MappingQuality}


# ── version mismatch -> UNAVAILABLE (blocking), window kept for audit ─────
def test_version_mismatch_blocking():
    bad = DecisionContext(map_params=MaterialMapParams(version="residence-map-vBAD"))
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    r = resolve_material_window(ev, bad, _mins(600))
    assert r.mapping_quality is MappingQuality.UNAVAILABLE
    assert MR_VERSION_MISMATCH in r.blocking_reason_codes
    assert MR_VERSION_MISMATCH in BLOCKING_CODES
    # the mapped window is still present for transparency
    assert r.material_window is not None


# ── O. full PrimePath lineage: evidence -> material -> route -> spec ─────
def test_O_lineage_bundle_integration():
    import json
    ev = _ev([RoutingInterval(_mins(0), _mins(1200), "DOWNGRADE", 12.0)])
    t = _mins(600)
    r = resolve_material_window(ev, _CTX, t)
    pred = PredictionBundle(event_id=ev.event_id, decision_time=t, point_mfi=3.1,
                            lower_mfi=2.6, upper_mfi=3.6, nominal_coverage=0.9,
                            prob_bad=0.2, model_version="m1", calibration_version="c1")
    lin = MaterialQualityLineage(prediction=pred, resolution=r, context=_CTX)
    d = lin.to_dict()
    # the lineage shows the material production window is NOT the reactor state at t
    assert d["material_production_window"]["production_time_start"] != t.isoformat()
    assert d["downstream_route"]["primary_destination"] == "DOWNGRADE"
    assert d["applicable_commercial_spec"]["target_grade"] == "B"
    assert "residence time" in d["note"]
    json.dumps(d, default=str)  # fully serializable
    assert r.service_version == MATERIAL_SERVICE_VERSION
