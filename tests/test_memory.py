"""Phase 11 tests — TRANSITION MEMORY (immutability, isolation, retrieval A-R).

These exercise the auditable evidence-memory layer: immutable versioned records,
reconciliation status, explicit eligibility, DIRECTIONAL + scope-isolated
retrieval (no holdout contamination, no self-retrieval, causal future-outcome
isolation), stable fingerprints, and transparent statistics. Everything is
SIMULATION/ASSUMPTION; analogs are historical EVIDENCE, never causal prediction.
"""
import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift.partition import Partition
from gradeshift.provenance import Provenance
from gradeshift import memory as M
from gradeshift.memory import (
    MemoryRecord, ReconciliationStatus, UnitPolicy, MemoryScope, RetrievalContext,
    TransitionMemoryStore, retrieve_transition_memory, evaluate_eligibility,
    compute_similarity, fingerprint, MEMORY_SCHEMA_VERSION,
)

BASE = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


def _rec(event_id="E1", direction="A->B", unit="U1", partition=Partition.TRAIN,
         status=ReconciliationStatus.RECONCILED, decision_min=100.0,
         reconciled_min=200.0, duration=120.0, initial=5.0, final=8.0,
         mass=50.0, phase="SETTLING", feat=None, schema=MEMORY_SCHEMA_VERSION,
         reconciled=True):
    gf, gt = direction.split("->")
    feat = feat or {"mfi_slope": 0.1, "temp": 220.0, "rate": 12.0}
    rec = MemoryRecord(
        event_id=event_id, direction=direction, grade_from=gf, grade_to=gt,
        unit=unit, partition=partition, decision_time=_mins(decision_min),
        prediction_snapshot={"point_mfi": (initial + final) / 2, "lower_mfi": 7.5,
                             "upper_mfi": 8.3, "nominal_coverage": 0.9,
                             "prob_bad_PROVISIONAL": 0.2},
        model_version="gbm-v1", calibration_version="cal-v1", policy_version="policy-v1",
        economics_version="economics-v1",
        material_window_summary={"mapped_mass_tonnes": mass, "mean_age_min": 60.0,
                                 "mapping_quality": "WELL_SUPPORTED", "route_known": True},
        health_state="NORMAL", applicability_state="NORMAL",
        disposition_action="PRIME_RELEASE_CANDIDATE", reason_codes=("X",),
        approval_state={"required_role": "QC", "authorized_by": None, "authorized_at": None},
        process_context={"phase": phase, "duration_min": duration,
                         "initial_mfi": initial, "final_mfi": final},
        feature_summary=feat, reconciliation_status=status, schema_version=schema)
    if reconciled and status == ReconciliationStatus.RECONCILED:
        rec = rec.reconcile(
            lab_outcome={"revealed_mfi": final, "was_in_spec": True},
            actual_route="PRIME", economic_ledger={"expected_loss_chosen_currency": 8000.0},
            realized_value=100000.0, counterfactual_value=200000.0,
            reconciled_at=_mins(reconciled_min), status=status)
    return rec


def _ctx(event_id="CUR", direction="A->B", unit="U1", decision_min=300.0,
         duration=120.0, initial=5.0, final=8.0, mass=50.0, phase="SETTLING", feat=None):
    gf, gt = direction.split("->")
    feat = feat or {"mfi_slope": 0.1, "temp": 220.0, "rate": 12.0}
    return RetrievalContext(
        event_id=event_id, direction=direction, grade_from=gf, grade_to=gt, unit=unit,
        phase=phase, process_context={"phase": phase, "duration_min": duration,
                                      "initial_mfi": initial, "final_mfi": final},
        material_window_summary={"mapped_mass_tonnes": mass, "mean_age_min": 60.0},
        feature_summary=feat, decision_time=_mins(decision_min))


def _store(*recs):
    s = TransitionMemoryStore()
    for r in recs:
        s.add(r)
    return s


# ── A. immutable record (no in-place mutation of historical evidence) ────────
def test_A_immutable_record():
    r = _rec()
    with pytest.raises(FrozenInstanceError):
        r.event_id = "other"
    # reconcile/update produce a NEW version; original is preserved
    r0 = _rec(status=ReconciliationStatus.PENDING, reconciled=False)
    assert r0.record_version == 1 and r0.lab_outcome is None
    r1 = r0.reconcile(lab_outcome={"was_in_spec": True}, actual_route="PRIME",
                      reconciled_at=_mins(400))
    assert r1.record_version == 2 and r0.lab_outcome is None  # original untouched
    assert r1.reconciliation_status == ReconciliationStatus.RECONCILED


# ── B. serialization round-trip ──────────────────────────────────────────────
def test_B_serialization_roundtrip():
    r = _rec()
    d = r.to_dict()
    s = json.dumps(d, default=str)
    back = MemoryRecord.from_dict(json.loads(s))
    assert back.event_id == r.event_id
    assert back.reconciliation_status == r.reconciliation_status
    assert back.to_dict()["identity_fingerprint"] == d["identity_fingerprint"]


# ── C. reconciliation status transitions ─────────────────────────────────────
def test_C_reconciliation_status():
    pend = _rec(status=ReconciliationStatus.PENDING, reconciled=False)
    assert pend.reconciliation_status == ReconciliationStatus.PENDING
    part = pend.with_update(reconciliation_status=ReconciliationStatus.PARTIALLY_RECONCILED)
    assert part.reconciliation_status == ReconciliationStatus.PARTIALLY_RECONCILED
    done = part.reconcile(lab_outcome={"was_in_spec": True}, actual_route="PRIME",
                          reconciled_at=_mins(400))
    assert done.reconciliation_status == ReconciliationStatus.RECONCILED
    # reconciled_at cannot precede decision_time
    with pytest.raises(ValueError):
        pend.reconcile(lab_outcome={}, actual_route="PRIME", reconciled_at=_mins(1))


# ── D. eligibility rules ─────────────────────────────────────────────────────
def test_D_eligibility_rules():
    assert evaluate_eligibility(_rec()).eligible is True
    pend = _rec(status=ReconciliationStatus.PENDING, reconciled=False)
    assert evaluate_eligibility(pend).eligible is False       # insufficient outcome
    bad_schema = _rec(schema="memory-vOLD")
    assert evaluate_eligibility(bad_schema).eligible is False  # schema mismatch
    # version mismatch is explicit
    r = _rec()
    assert evaluate_eligibility(r, expected_versions={"model": "gbm-vX"}).eligible is False


# ── E. directional retrieval (A->B != B->A) ──────────────────────────────────
def test_E_directional_retrieval():
    ab = _rec(event_id="AB", direction="A->B")
    ba = _rec(event_id="BA", direction="B->A")
    store = _store(ab, ba)
    scope = MemoryScope(direction="A->B", allowed_partition=Partition.TRAIN)
    got = retrieve_transition_memory(_ctx(direction="A->B"), scope, 5, store)
    ids = {e.event_id for e in got}
    assert "AB" in ids and "BA" not in ids


# ── F. unit filtering follows explicit policy ────────────────────────────────
def test_F_unit_filtering_policy():
    u1 = _rec(event_id="U1E", unit="U1")
    u2 = _rec(event_id="U2E", unit="U2")
    store = _store(u1, u2)
    ctx = _ctx(unit="U1")
    strict = MemoryScope(direction="A->B", unit="U1", unit_policy=UnitPolicy.SAME_UNIT_ONLY)
    assert {e.event_id for e in store.retrieve(ctx, strict, 5)} == {"U1E"}
    anyu = MemoryScope(direction="A->B", unit="U1", unit_policy=UnitPolicy.ANY_UNIT)
    assert {e.event_id for e in store.retrieve(ctx, anyu, 5)} == {"U1E", "U2E"}
    # PREFER_SAME_UNIT allows cross-unit but penalizes its score
    pref = MemoryScope(direction="A->B", unit="U1", unit_policy=UnitPolicy.PREFER_SAME_UNIT)
    res = store.retrieve(ctx, pref, 5)
    assert {e.event_id for e in res} == {"U1E", "U2E"}
    assert res[0].event_id == "U1E"   # same-unit ranks first


# ── G. deterministic similarity scoring ──────────────────────────────────────
def test_G_deterministic_similarity():
    r = _rec()
    ctx = _ctx()
    a = compute_similarity(ctx, r)
    b = compute_similarity(ctx, r)
    assert a.to_dict() == b.to_dict()
    assert 0.0 <= a.score <= 1.0
    # an identical-context analog scores higher than a divergent one
    far = _rec(initial=50.0, final=99.0, duration=999.0, phase="OTHER",
               feat={"mfi_slope": 9.9, "temp": 10.0, "rate": 99.0})
    assert compute_similarity(ctx, r).score > compute_similarity(ctx, far).score


# ── H. current event never retrieves itself ──────────────────────────────────
def test_H_self_exclusion():
    me = _rec(event_id="CUR")
    other = _rec(event_id="OTHER")
    store = _store(me, other)
    got = retrieve_transition_memory(_ctx(event_id="CUR"),
                                     MemoryScope(direction="A->B"), 5, store)
    assert "CUR" not in {e.event_id for e in got}
    assert "OTHER" in {e.event_id for e in got}


# ── I. locked-test events are never retrieved as analogs ─────────────────────
def test_I_locked_test_exclusion():
    tr = _rec(event_id="TR", partition=Partition.TRAIN)
    lk = _rec(event_id="LK", partition=Partition.LOCKED_TEST)
    store = _store(tr, lk)
    scope = MemoryScope(direction="A->B", allowed_partition=Partition.TRAIN)
    ids = {e.event_id for e in store.retrieve(_ctx(), scope, 5)}
    assert "LK" not in ids and "TR" in ids


# ── J. calibration/train isolation ───────────────────────────────────────────
def test_J_calibration_train_isolation():
    tr = _rec(event_id="TR", partition=Partition.TRAIN)
    ca = _rec(event_id="CA", partition=Partition.CALIBRATION)
    store = _store(tr, ca)
    # only TRAIN may support model/recommendation evidence
    scope = MemoryScope(direction="A->B", allowed_partition=Partition.TRAIN)
    assert {e.event_id for e in store.retrieve(_ctx(), scope, 5)} == {"TR"}
    # a CALIBRATION query cannot pull LOCKED_TEST either
    lk = _rec(event_id="LK", partition=Partition.LOCKED_TEST)
    store2 = _store(ca, lk)
    cal_scope = MemoryScope(direction="A->B", allowed_partition=Partition.CALIBRATION)
    assert {e.event_id for e in store2.retrieve(_ctx(), cal_scope, 5)} == {"CA"}


# ── K. unreconciled records can be stored but excluded when required ─────────
def test_K_unreconciled_exclusion():
    done = _rec(event_id="DONE")
    pend = _rec(event_id="PEND", status=ReconciliationStatus.PENDING, reconciled=False)
    store = _store(done, pend)
    assert store.statistics()["total_episodes"] == 2        # both STORED
    scope = MemoryScope(direction="A->B", require_reconciled=True)
    ids = {e.event_id for e in store.retrieve(_ctx(), scope, 5)}
    assert ids == {"DONE"}                                  # pending excluded


# ── L. provenance retention through storage + retrieval ──────────────────────
def test_L_provenance_retained():
    r = _rec()
    store = _store(r)
    ev = store.retrieve(_ctx(), MemoryScope(direction="A->B"), 5)[0]
    assert ev.provenance == Provenance.SIMULATED.value
    assert MemoryRecord.from_dict(r.to_dict()).provenance == Provenance.SIMULATED


# ── M. fingerprint stability (never Python object hash) ──────────────────────
def test_M_fingerprint_stability():
    r1 = _rec()
    r2 = _rec()
    assert r1.identity_fingerprint == r2.identity_fingerprint   # same content
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    # changing the feature representation changes the fingerprint
    r3 = _rec(feat={"mfi_slope": 9.9})
    assert r3.feature_fingerprint != r1.feature_fingerprint


# ── N. version mismatch handling ─────────────────────────────────────────────
def test_N_version_mismatch():
    r = _rec()
    store = _store(r)
    scope = MemoryScope(direction="A->B", expected_versions={"model": "gbm-vFUTURE"})
    assert store.retrieve(_ctx(), scope, 5) == []   # excluded on version mismatch
    ok = MemoryScope(direction="A->B", expected_versions={"model": "gbm-v1"})
    assert len(store.retrieve(_ctx(), ok, 5)) == 1


# ── O. future-outcome isolation in replay (causal) ───────────────────────────
def test_O_future_outcome_isolation():
    # analog reconciled at t=500, current decision at t=300 -> truth not yet known
    future = _rec(event_id="FUT", decision_min=100.0, reconciled_min=500.0)
    store = _store(future)
    scope = MemoryScope(direction="A->B", require_reconciled=True)
    early = store.retrieve(_ctx(event_id="CUR", decision_min=300.0), scope, 5)
    assert early == []                               # not reconciled as-of t=300
    late = store.retrieve(_ctx(event_id="CUR", decision_min=600.0), scope, 5)
    assert len(late) == 1 and late[0].laboratory_truth is not None


# ── P. deterministic retrieval ordering ──────────────────────────────────────
def test_P_deterministic_retrieval():
    recs = [_rec(event_id=f"E{i}", initial=5.0 + i * 0.1) for i in range(5)]
    store = _store(*recs)
    ctx = _ctx()
    scope = MemoryScope(direction="A->B")
    a = [e.event_id for e in store.retrieve(ctx, scope, 3)]
    b = [e.event_id for e in store.retrieve(ctx, scope, 3)]
    assert a == b and len(a) == 3


# ── Q. empty retrieval handling ──────────────────────────────────────────────
def test_Q_empty_retrieval():
    store = TransitionMemoryStore()
    assert retrieve_transition_memory(_ctx(), MemoryScope(direction="A->B"), 3, store) == []
    # no eligible analog -> empty, no raise
    only_pending = _store(_rec(status=ReconciliationStatus.PENDING, reconciled=False))
    assert only_pending.retrieve(_ctx(), MemoryScope(direction="A->B"), 3) == []


# ── R. no silent retraining contract + statistics ────────────────────────────
def test_R_no_online_learning_and_stats():
    c = M.assert_no_online_learning()
    assert c["performs_online_learning"] is False
    store = _store(_rec(event_id="A", direction="A->B", unit="U1"),
                   _rec(event_id="B", direction="B->A", unit="U2",
                        partition=Partition.CALIBRATION))
    st = store.statistics()
    assert st["total_episodes"] == 2
    assert st["by_direction"]["A->B"] == 1 and st["by_direction"]["B->A"] == 1
    assert set(st["by_unit"]) == {"U1", "U2"}
    # no fabricated "learning improvement" metric key is invented
    assert not any("improvement" in k.lower() or "accuracy_gain" in k.lower()
                   for k in st)


# ── canonical 3-analog retrieval example (A->B) with explicit exclusions ─────
def test_canonical_three_analog_example():
    analogs = [_rec(event_id=f"AB{i}", direction="A->B", unit="U1",
                    initial=5.0 + i * 0.05, final=8.0) for i in range(4)]
    ba = _rec(event_id="BA1", direction="B->A", unit="U1")
    locked = _rec(event_id="LK1", direction="A->B", partition=Partition.LOCKED_TEST)
    current = _rec(event_id="CUR", direction="A->B", unit="U1")
    store = _store(*analogs, ba, locked, current)
    scope = MemoryScope(direction="A->B", allowed_partition=Partition.TRAIN,
                        excluded_event_ids=frozenset({"CUR"}))
    ev = retrieve_transition_memory(_ctx(event_id="CUR", direction="A->B", unit="U1"),
                                    scope, 3, store)
    ids = [e.event_id for e in ev]
    assert len(ev) == 3
    assert "BA1" not in ids           # opposite direction excluded
    assert "LK1" not in ids           # locked-test excluded
    assert "CUR" not in ids           # current event excluded
    for e in ev:
        assert e.similarity.score >= 0.0
        assert e.what_was_predicted and e.laboratory_truth is not None
        assert "causal" in e.note.lower()
