"""Phase 5 tests — target definition, baselines, GBM, event-level split,
reproducibility, product integrity, and the material-window lineage chain.
"""
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from gradeshift import simulate as S
from gradeshift import config as C
from gradeshift.dataset import _target_for, build_rows, make_corpus, rows_to_xy
from gradeshift.estimator import (
    DeterministicProcessBaseline, GBMQualityEstimator, LastLabBaseline,
    LinearProcessBaseline, QualityEstimate, regression_metrics,
)
from gradeshift.features import build_features
from gradeshift.pipeline import (DEFAULT_DIRECTIONS, build_lineage_chain,
                                 default_corpus, run_phase5)
from gradeshift.partition import Partition, chronological_split, partition_members
from gradeshift.schemas import PredictionBundle

BASE = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def _episode():
    return S.generate_episode("EP-EST", "A", "B", seed=21, start_time=BASE,
                              params=S.EpisodeParams())


# 1. Target = earliest lab collected in [t, t+horizon]; future truth, not a feature.
def test_target_definition():
    ev = _episode()
    t = ev.started_at + timedelta(minutes=200)
    mfi, sid = _target_for(ev, t, C.POLICY.decision_horizon_min)
    cand = sorted((s for s in ev.labs
                   if t <= s.collected_at <= t + timedelta(minutes=C.POLICY.decision_horizon_min)),
                  key=lambda s: s.collected_at)
    assert sid == cand[0].sample_id and mfi == pytest.approx(cand[0].mfi)
    # the supervising lab resolves in the FUTURE (not knowable at t)…
    assert cand[0].result_at > t
    # …and its value is absent from the as-of feature vector
    feats = build_features(ev, t)
    assert all(not math.isclose(v, mfi, rel_tol=1e-12)
               for k, v in feats.items() if k.startswith("lab_"))


def test_target_absent_returns_none():
    ev = _episode()
    far = (ev.ended_at or max(r.end for r in ev.routing)) + timedelta(minutes=10_000)
    assert _target_for(ev, far, C.POLICY.decision_horizon_min) == (None, None)


# 4. Baselines behave transparently incl. explicit unavailable (never random).
def test_baselines_and_unavailable():
    feats_ok = {"lab_last_mfi": 5.0, "MFI_online_last": 6.0}
    feats_nan = {"lab_last_mfi": float("nan"), "MFI_online_last": float("nan")}
    assert LastLabBaseline().predict_one(feats_ok) == 5.0
    assert LastLabBaseline().predict_one(feats_nan) is None
    assert DeterministicProcessBaseline().predict_one(feats_ok) == 6.0
    assert DeterministicProcessBaseline().predict_one(feats_nan) is None
    assert LinearProcessBaseline().predict_one(feats_ok) is None  # not fitted


# 5. GBM fits, predicts, and emits a schema-valid provisional bundle.
def test_gbm_fit_predict_and_bundle():
    ev = _episode()
    rows = [r for r in build_rows(ev) if r.has_target]
    X, y, rows = rows_to_xy(rows)
    gbm = GBMQualityEstimator().fit(X, y)
    t = ev.started_at + timedelta(minutes=300)
    est = gbm.estimate(ev, t)
    assert est.available and isinstance(est.point_mfi, float)
    bundle = est.as_prediction_bundle()
    assert isinstance(bundle, PredictionBundle)
    assert bundle.calibration_version == "UNCALIBRATED-ph5"
    assert bundle.lower_mfi == bundle.upper_mfi == bundle.point_mfi   # degenerate (no interval yet)


# 11. Product integrity: unavailable when no process evidence; no bundle from it.
def test_unavailable_estimate_integrity():
    ev = _episode()
    gbm = GBMQualityEstimator()
    # not fitted AND before first observation -> unavailable, point None, no random value
    est = gbm.estimate(ev, ev.started_at - timedelta(minutes=5))
    assert est.available is False and est.point_mfi is None and est.reason
    with pytest.raises(ValueError):
        est.as_prediction_bundle()


# 6. Event-level split: partitions are disjoint at the EVENT level.
def test_event_level_split_disjoint():
    events = default_corpus(n_per_dir=2)
    a = chronological_split(events)
    sets = {p: set(partition_members(a, p)) for p in Partition}
    assert sets[Partition.TRAIN] and sets[Partition.CALIBRATION] and sets[Partition.LOCKED_TEST]
    assert sets[Partition.TRAIN].isdisjoint(sets[Partition.CALIBRATION])
    assert sets[Partition.TRAIN].isdisjoint(sets[Partition.LOCKED_TEST])
    assert sets[Partition.CALIBRATION].isdisjoint(sets[Partition.LOCKED_TEST])


# 10. Reproducibility: same corpus+seed+code -> identical metrics and partitions.
def test_reproducible_pipeline():
    a = run_phase5(n_per_dir=2)
    b = run_phase5(n_per_dir=2)
    assert a["partitions"] == b["partitions"]
    assert (a["metrics"]["LOCKED_TEST"]["gbm"]["overall"]
            == b["metrics"]["LOCKED_TEST"]["gbm"]["overall"])


def test_gbm_persist_round_trip(tmp_path):
    ev = _episode()
    rows = [r for r in build_rows(ev) if r.has_target]
    X, y, rows = rows_to_xy(rows)
    gbm = GBMQualityEstimator().fit(X, y)
    p = tmp_path / "gbm.joblib"
    gbm.save(str(p))
    loaded = GBMQualityEstimator.load(str(p))
    t = ev.started_at + timedelta(minutes=300)
    assert loaded.estimate(ev, t).point_mfi == pytest.approx(gbm.estimate(ev, t).point_mfi)


# metrics helper correctness (available-only, with coverage)
def test_regression_metrics():
    m = regression_metrics([1.0, 2.0, None], [1.0, 1.0, 1.0])
    assert m["n"] == 2 and m["coverage"] == pytest.approx(2 / 3)
    assert m["mae"] == pytest.approx(0.5) and m["bias"] == pytest.approx(0.5)
    assert m["rmse"] == pytest.approx(math.sqrt(0.5))
    empty = regression_metrics([None], [1.0])
    assert empty["n"] == 0 and math.isnan(empty["mae"])


# 8. Material-window lineage chain is well-formed and ties truth to prediction.
def test_lineage_chain():
    ev = _episode()
    rows = [r for r in build_rows(ev) if r.has_target]
    X, y, rows = rows_to_xy(rows)
    gbm = GBMQualityEstimator().fit(X, y)
    t = ev.started_at + timedelta(minutes=300)
    chain = build_lineage_chain(ev, t, gbm)
    for key in ("decision_time", "reactor_state_online_mfi_at_t",
                "material_production_window", "material_time_window",
                "downstream_route", "lab_truth_mfi", "prediction_mfi"):
        assert key in chain
    # production window precedes the downstream material window (two distinct axes)
    assert chain["material_production_window"][1] <= chain["material_time_window"][1]
    assert chain["prediction_available"] is True


# 7. GBM beats the trivial last-lab baseline on the locked test (sanity, not value claim).
def test_gbm_beats_last_lab_on_locked():
    r = run_phase5(n_per_dir=3)
    gbm = r["metrics"]["LOCKED_TEST"]["gbm"]["overall"]["mae"]
    lastlab = r["metrics"]["LOCKED_TEST"]["last_lab"]["overall"]["mae"]
    assert gbm < lastlab
