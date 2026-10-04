"""Phase 12 tests — COUNTERFACTUAL REPLAY (leakage firewall A-J + determinism).

These prove the causal firewall (future labs/routing/outcome cannot affect a
decision), that no policy bypasses the Phase-9 hard gates, that the Oracle
cannot contaminate PrimePath, that replay never mutates frozen artifacts, that
economics stay strictly downstream, and that replay is deterministic.
Everything is SIMULATION/ASSUMPTION — the Oracle is DIAGNOSTIC ONLY.
"""
from dataclasses import replace

import pytest

from gradeshift import simulate as S, config as C
from gradeshift import replay as R
from gradeshift.provenance import Provenance
from gradeshift.schemas import RoutingInterval, LabSample
from gradeshift.health import SensorHealthReport, HealthState
from gradeshift.applicability import ApplicabilityDetector
from gradeshift.features import MaterialMapParams
from gradeshift.estimator import GBMQualityEstimator
from gradeshift.partition import Partition
from gradeshift.pipeline import (default_corpus, chronological_split,
                                 partition_members, build_rows, rows_to_xy,
                                 _calibrate_estimator, RANDOM_SEED)


@pytest.fixture(scope="module")
def fitted():
    mp = MaterialMapParams()
    events = default_corpus(n_per_dir=3)
    asg = chronological_split(events)
    by_id = {e.event_id: e for e in events}
    train_events = [by_id[i] for i in partition_members(asg, Partition.TRAIN)]
    allrows = {p: [] for p in Partition}
    for e in events:
        for r in build_rows(e, map_params=mp):
            allrows[asg[e.event_id]].append(r)
    tr = [r for r in allrows[Partition.TRAIN] if r.has_target]
    ca = [r for r in allrows[Partition.CALIBRATION] if r.has_target]
    lk = [r for r in allrows[Partition.LOCKED_TEST] if r.has_target]
    X, y, tr = rows_to_xy(tr)
    gbm = GBMQualityEstimator(random_state=RANDOM_SEED).fit(X, y)
    calib = _calibrate_estimator(gbm, ca, lk, 0.9)["_calibrator"]
    det = ApplicabilityDetector.fit(train_events)
    eng = R.ReplayEngine(gbm, calib, det, mp, C.ECON_SCENARIOS["BASE"])
    lk_ids = partition_members(asg, Partition.LOCKED_TEST)
    ev = by_id[lk_ids[0]]
    spec = C.GRADES[ev.grade_to]
    ts = sorted({r.decision_time for r in allrows[Partition.LOCKED_TEST]
                 if r.event_id == ev.event_id})[:5]
    return {"engine": eng, "event": ev, "spec": spec, "timestamps": ts,
            "gbm": gbm, "calib": calib}


def _future_t(ev, ts):
    return max(ts) + (ev.ended_at - max(ts)) if ev.ended_at else max(ts)


# ── A. a future lab result cannot affect the decision ────────────────────────
def test_A_future_lab_no_effect(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    t = ts[0]
    base = eng.build_context(ev, t, spec)
    base_dec = R.PrimePathPolicy().decide(base)
    future_lab = LabSample("INJECT", spec.grade_id, 999.0, t, max(ts),
                           Provenance.SIMULATED)   # resulted far in the future
    ev2 = replace(ev, labs=ev.labs + (future_lab,))
    dec2 = R.PrimePathPolicy().decide(eng.build_context(ev2, t, spec))
    assert dec2.action == base_dec.action
    assert dec2.reason_codes == base_dec.reason_codes


# ── B. a future routing switch cannot affect the decision ────────────────────
def test_B_future_route_no_effect(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    t = ts[0]
    base = R.PrimePathPolicy().decide(eng.build_context(ev, t, spec))
    future_route = RoutingInterval(max(ts), max(ts), "PRIME", 99.0)
    ev2 = replace(ev, routing=ev.routing + (future_route,))
    after = R.PrimePathPolicy().decide(eng.build_context(ev2, t, spec))
    assert after.action == base.action


# ── C. a future outcome (post-t observations) cannot affect the decision ─────
def test_C_future_outcome_no_effect(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    t = ts[0]
    ctx = eng.build_context(ev, t, spec)
    # the truncated as-of event exposes nothing after t
    assert all(o.timestamp <= t for o in ctx.as_of_event.series)
    assert all(l.result_at <= t for l in ctx.as_of_event.labs)
    assert all(r.start <= t for r in ctx.as_of_event.routing)


# ── D. no policy can bypass a Phase-9 hard gate ──────────────────────────────
def test_D_hard_gate_not_bypassed(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    ctx = eng.build_context(ev, ts[0], spec)
    # force an in-spec prediction but an ABNORMAL sensor -> PrimePath must ABSTAIN
    in_spec_pred = replace(ctx.prediction, point_mfi=(spec.mfi_low + spec.mfi_high) / 2,
                           lower_mfi=spec.mfi_low, upper_mfi=spec.mfi_high)
    abnormal = SensorHealthReport(ctx.decision_time, HealthState.ABNORMAL, True, {}, (),
                                  "h", Provenance.SIMULATED)
    ctx2 = replace(ctx, prediction=in_spec_pred, health_report=abnormal,
                   point_estimate=(spec.mfi_low + spec.mfi_high) / 2)
    dec = R.PrimePathPolicy().decide(ctx2)
    assert dec.action == R.ABSTAIN                       # gate dominates
    # the point-threshold baseline, lacking the gate, would NOT abstain here
    assert R.PointThresholdPolicy().decide(ctx2).action == R.PRIME_RELEASE_CANDIDATE


# ── E. the Oracle cannot contaminate PrimePath ───────────────────────────────
def test_E_oracle_no_contamination(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    ctx = eng.build_context(ev, ts[0], spec)
    without = R.PrimePathPolicy().decide(ctx)
    with_truth = R.PrimePathPolicy().decide(
        replace(ctx, oracle_truth={"was_in_spec": True, "revealed_mfi": 8.0}))
    assert without.action == with_truth.action
    assert without.reason_codes == with_truth.reason_codes


# ── F. a locked replay never mutates the frozen artifacts ────────────────────
def test_F_artifacts_frozen(fitted):
    eng, ev, spec, ts, gbm, calib = (fitted["engine"], fitted["event"], fitted["spec"],
                                     fitted["timestamps"], fitted["gbm"], fitted["calib"])
    mv0, cv0 = gbm.model_version, calib.calibration_version
    probe = gbm.predict_one(eng.build_context(ev, ts[0], spec).features)
    eng.replay_episode(ev, ts, spec, "LOCKED_TEST")
    assert gbm.model_version == mv0 and calib.calibration_version == cv0
    assert gbm.predict_one(eng.build_context(ev, ts[0], spec).features) == probe


# ── G. replay is deterministic (semantically identical output) ───────────────
def test_G_deterministic_replay(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    a = eng.replay_episode(ev, ts, spec, "LOCKED_TEST").to_dict()
    b = eng.replay_episode(ev, ts, spec, "LOCKED_TEST").to_dict()
    assert a == b


# ── H. material mapping stays causal under future routing ────────────────────
def test_H_material_mapping_causal(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    t = ts[0]
    base = eng.build_context(ev, t, spec).material_window_summary
    ev2 = replace(ev, routing=ev.routing + (RoutingInterval(max(ts), max(ts), "PRIME", 99.0),))
    after = eng.build_context(ev2, t, spec).material_window_summary
    assert after["mapped_mass_tonnes"] == base["mapped_mass_tonnes"]
    assert after["mapping_quality"] == base["mapping_quality"]


# ── I. economics are strictly downstream of the decision ─────────────────────
def test_I_economics_downstream(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    # changing the economic scenario must NOT change any policy's action
    actions_base = [d.action for d in eng.replay_episode(ev, ts, spec).decisions[R.PRIMEPATH]]
    eng_high = R.ReplayEngine(fitted["gbm"], fitted["calib"], eng.detector, eng.mp,
                              C.ECON_SCENARIOS["HIGH"])
    actions_high = [d.action for d in eng_high.replay_episode(ev, ts, spec).decisions[R.PRIMEPATH]]
    assert actions_base == actions_high


# ── canonical ILLUSTRATIVE demo T1..T5 (never in validation) ────────────────
def test_demo_fixture_sequence():
    d = R.demo_fixture()
    by_t = {s["t"]: s for s in d["steps"]}
    assert by_t["T1"]["action"] == R.HOLD
    assert by_t["T2"]["action"] == R.SAMPLE_NOW
    assert by_t["T3"]["action"] == R.PRIME_RELEASE_CANDIDATE
    assert "was_in_spec" in by_t["T4"]
    assert "ledger" in by_t["T5"]
    assert "ILLUSTRATIVE DEMO FIXTURE" in d["label"]


# ── comparison table carries no overall score/ranking ───────────────────────
def test_comparison_table_no_winner(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    tbl = R.build_comparison_table(eng.replay_episode(ev, ts, spec))
    assert "ORACLE" in tbl["oracle_label"] and "DIAGNOSTIC" in tbl["oracle_label"]
    # no overall score / ranking FIELD is produced (component metrics only)
    for row in tbl["rows"]:
        assert not any(k in row for k in ("overall_score", "score", "rank", "winner"))
    assert {r["policy"] for r in tbl["rows"]} == {R.SOP, R.POINT_THRESHOLD,
                                                  R.PRIMEPATH, R.ORACLE}


# ── one full machine-readable event trace exists ─────────────────────────────
def test_event_trace_complete(fitted):
    eng, ev, spec, ts = fitted["engine"], fitted["event"], fitted["spec"], fitted["timestamps"]
    tr = R.event_trace(eng.replay_episode(ev, ts, spec), R.PRIMEPATH, 0)
    for key in ("as_of_context", "decision", "later_truth", "outcome"):
        assert key in tr
    assert tr["as_of_context"]["interval"] is not None
