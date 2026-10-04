"""Phase 6 tests — split-conformal calibration: reproducibility, quantile
correctness, calibration coverage, locked isolation, version/artifact integrity,
subgroup fallback, and the point-vs-interval evidence distinction.
"""
import json
import math
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import config as C
from gradeshift.calibrator import (
    MIN_EVENTS_FOR_CONDITIONING, METHOD_MARGINAL_SYM, METHOD_PHASE_SYM,
    CALIBRATION_METHOD_VERSION, ResidualRecord, SplitConformalCalibrator,
    coverage_metrics, evidence_state, _abs_quantile,
)
from gradeshift.estimator import QualityEstimate
from gradeshift.features import FEATURE_SCHEMA_VERSION
from gradeshift.pipeline import _calibrate_estimator, run_phase6
from gradeshift.schemas import PredictionBundle

BASE = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
EST_V = "test-est-v1"


def _recs(points_truths, event_id="EV", phase="ACTIVE_TRANSITION", direction="A->B"):
    return [ResidualRecord(event_id, phase, direction, p, y) for p, y in points_truths]


def _multi_event_recs(n_events, per_event=50, spread=0.3, phase="ACTIVE_TRANSITION"):
    """Synthetic calibration records with a KNOWN residual magnitude `spread`."""
    recs = []
    for e in range(n_events):
        for i in range(per_event):
            sign = 1 if i % 2 == 0 else -1
            recs.append(ResidualRecord(f"E{e}", phase, "A->B", 5.0, 5.0 + sign * spread))
    return recs


def _fit(recs, method=METHOD_MARGINAL_SYM, nominal=0.90, **kw):
    return SplitConformalCalibrator.fit(
        recs, method=method, estimator_version=EST_V,
        feature_version=FEATURE_SCHEMA_VERSION, nominal_coverage=nominal, **kw)


# A. Calibration reproducibility: same data -> identical offsets; pipeline stable.
def test_calibration_reproducible():
    recs = _multi_event_recs(4)
    a, b = _fit(recs), _fit(recs)
    assert a.to_dict() == b.to_dict()
    r1 = run_phase6(n_per_dir=2)
    r2 = run_phase6(n_per_dir=2)
    assert (r1["estimators"]["gbm"]["locked_overall"]
            == r2["estimators"]["gbm"]["locked_overall"])
    assert (r1["estimators"]["linear_process"]["calibrator_manifest"]
            == r2["estimators"]["linear_process"]["calibrator_manifest"])


# B. Correct residual quantile (finite-sample conformal rank).
def test_residual_quantile_formula():
    mags = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]  # n=9
    q, exact = _abs_quantile(mags, 0.90)
    k = math.ceil((9 + 1) * 0.90)                          # = 9
    assert exact and q == sorted(mags)[k - 1]
    # level too high for n -> cap at max, not exact
    q2, exact2 = _abs_quantile([0.5, 0.6], 0.90)
    assert q2 == 0.6 and exact2 is False


# C. Interval contains >= nominal proportion on the calibration fixture.
def test_calibration_empirical_coverage():
    recs = _multi_event_recs(4, per_event=50, spread=0.3)
    cal = _fit(recs, nominal=0.90)
    covered = sum(1 for r in recs
                  if (r.point - cal.marginal.lo) <= r.truth <= (r.point + cal.marginal.hi))
    assert covered / len(recs) >= 0.90


# D. No locked-test influence: the calibrator is independent of locked rows.
def test_no_locked_influence(_corpus_cache={}):
    from gradeshift.pipeline import default_corpus
    from gradeshift.partition import Partition, chronological_split, partition_members
    from gradeshift.dataset import build_rows
    from gradeshift.estimator import LinearProcessBaseline
    from gradeshift.dataset import rows_to_xy
    events = default_corpus(n_per_dir=2)
    asg = chronological_split(events)
    rows = {p: [] for p in Partition}
    for e in events:
        for r in build_rows(e):
            if r.has_target:
                rows[asg[e.event_id]].append(r)
    X, y, tr = rows_to_xy(rows[Partition.TRAIN])
    model = LinearProcessBaseline().fit([r.features for r in tr], y)
    full = _calibrate_estimator(model, rows[Partition.CALIBRATION], rows[Partition.LOCKED_TEST], 0.90)
    half = _calibrate_estimator(model, rows[Partition.CALIBRATION], rows[Partition.LOCKED_TEST][:5], 0.90)
    # Calibrator parameters depend ONLY on calibration data, never on locked rows.
    assert full["calibrator_manifest"] == half["calibrator_manifest"]
    assert full["chosen_method"] == half["chosen_method"]


# E. No future-information: interval is a pure function of the point (not of time).
def test_interval_independent_of_time():
    cal = _fit(_multi_event_recs(4))
    e1 = QualityEstimate("EV", BASE, 5.0, True, EST_V)
    e2 = QualityEstimate("EV", BASE + timedelta(minutes=9999), 5.0, True, EST_V)
    b1 = cal.predict_bundle(e1)
    b2 = cal.predict_bundle(e2)
    assert b1.width == b2.width and b1.lower_mfi == b2.lower_mfi


# F/G. Nominal-coverage metadata and interval ordering.
def test_metadata_and_ordering():
    cal = _fit(_multi_event_recs(4), nominal=0.90)
    est = QualityEstimate("EV", BASE, 5.0, True, EST_V)
    b = cal.predict_bundle(est)
    assert b.nominal_coverage == 0.90
    assert b.lower_mfi <= b.point_mfi <= b.upper_mfi
    assert cal.to_dict()["nominal_coverage"] == 0.90


# H. Estimator / feature-version mismatch is rejected (never silently recalibrated).
def test_version_mismatch_rejected():
    cal = _fit(_multi_event_recs(4))
    bad_model = QualityEstimate("EV", BASE, 5.0, True, "OTHER-MODEL")
    with pytest.raises(ValueError):
        cal.predict_bundle(bad_model)
    bad_feat = QualityEstimate("EV", BASE, 5.0, True, EST_V, feature_version="feat-OTHER")
    with pytest.raises(ValueError):
        cal.predict_bundle(bad_feat)
    unavail = QualityEstimate("EV", BASE, None, False, EST_V, reason="no evidence")
    with pytest.raises(ValueError):
        cal.predict_bundle(unavail)


# I. Insufficient calibration data: empty -> error; few events -> selection gated.
def test_insufficient_data_handling():
    with pytest.raises(ValueError):
        _fit([])
    # 3 independent events < MIN_EVENTS_FOR_CONDITIONING -> only marginal is eligible
    r = run_phase6(n_per_dir=3)
    assert r["calibration_events"] < MIN_EVENTS_FOR_CONDITIONING
    for name in ("linear_process", "gbm"):
        e = r["estimators"][name]
        assert e["conditioning_gated"] is True
        assert e["chosen_method"] == METHOD_MARGINAL_SYM


# J. Subgroup fallback: a thin phase bucket borrows the marginal pool transparently.
def test_subgroup_fallback():
    recs = _multi_event_recs(4, per_event=50, phase="ACTIVE_TRANSITION")
    recs += _recs([(5.0, 5.1), (5.0, 4.9)], event_id="E0", phase="PRE_BASELINE")  # tiny
    cal = _fit(recs, method=METHOD_PHASE_SYM)
    assert cal.phase["PRE_BASELINE"].fallback is True
    assert cal.phase["PRE_BASELINE"].source_bucket == "marginal"
    assert cal.phase["ACTIVE_TRANSITION"].fallback is False


# K. Point inside spec but interval crosses the limit -> not interval-eligible.
def test_point_in_spec_interval_crosses():
    spec = C.GRADES["B"]            # 8.00 ± 5% -> [7.6, 8.4]
    b = PredictionBundle("EV", BASE, point_mfi=7.70, lower_mfi=7.40, upper_mfi=8.00,
                         nominal_coverage=0.90, prob_bad=0.0,
                         model_version=EST_V, calibration_version="x")
    ev = evidence_state(b, spec)
    assert ev["point_state"] == "IN_SPEC"
    assert ev["uncertainty_state"] == "CROSSES_LIMIT"
    assert ev["prime_candidacy_eligible_by_interval"] is False
    # a fully-inside interval IS interval-eligible (gates still owed to Phase 7/8)
    b2 = PredictionBundle("EV", BASE, 8.0, 7.9, 8.1, 0.90, 0.0, EST_V, "x")
    assert evidence_state(b2, spec)["prime_candidacy_eligible_by_interval"] is True


# L. Serialized artifact round-trip + bad-version rejection.
def test_artifact_round_trip(tmp_path):
    cal = _fit(_multi_event_recs(4))
    p = tmp_path / "cal.joblib"
    cal.save(str(p))
    loaded = SplitConformalCalibrator.load(str(p))
    assert loaded.to_dict() == cal.to_dict()
    bad = cal.to_dict(); bad["calibration_version"] = "bogus-v9"
    with pytest.raises(ValueError):
        SplitConformalCalibrator.from_dict(bad)
    worse = cal.to_dict(); worse["method"] = "not_a_method"
    with pytest.raises(ValueError):
        SplitConformalCalibrator.from_dict(worse)


# M. Deterministic inference after reload.
def test_deterministic_after_reload(tmp_path):
    cal = _fit(_multi_event_recs(4))
    p = tmp_path / "cal.joblib"
    cal.save(str(p))
    loaded = SplitConformalCalibrator.load(str(p))
    est = QualityEstimate("EV", BASE, 5.0, True, EST_V)
    assert loaded.predict_bundle(est).to_dict() == cal.predict_bundle(est).to_dict()


# coverage_metrics behaves (empty + simple).
def test_coverage_metrics_helper():
    assert coverage_metrics([], [])["n_rows"] == 0
    b = [PredictionBundle("E", BASE, 5.0, 4.5, 5.5, 0.90, 0.0, EST_V, "x")]
    m = coverage_metrics(b, [5.0])
    assert m["coverage"] == 1.0 and m["mean_width"] == pytest.approx(1.0)
    m2 = coverage_metrics(b, [9.0])
    assert m2["coverage"] == 0.0 and m2["under_coverage"] == 1.0
