"""Phase 7B tests — MODEL APPLICABILITY / OOD layer.

Covers OOD fixtures A–G and tests H–N of the Phase 7 objective: known/unknown
unit and grade pair, in-domain mild shift (NOT OOD), true feature OOD, missing
required feature deferring to data-health (NOT OOD), TRAIN-only fitting +
isolation proof, and artifact/schema-version mismatch rejection. Deterministic
rules are PRIMARY; IsolationForest + NN distance are AUXILIARY (reported only).
"""
from datetime import datetime, timedelta, timezone

import math
import pytest

from gradeshift import simulate as S
from gradeshift import faults as F
from gradeshift.pipeline import default_corpus
from gradeshift.partition import chronological_split, Partition
from gradeshift.features import build_features, FEATURE_SCHEMA_VERSION
from gradeshift.applicability import (
    ApplicabilityDetector, ApplicabilityState, unavailable_result,
    OOD_FEATURES, APPLICABILITY_VERSION, DETECTOR_VERSION,
    A_UNKNOWN_UNIT, A_UNKNOWN_PAIR, A_FEATURE_OOS, A_FEATURE_UNAVAIL,
    A_ARTIFACT_UNAVAIL, A_OK,
)

BASE = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


def _split_corpus():
    corpus = default_corpus()
    split = chronological_split(corpus)
    by_id = {e.event_id: e for e in corpus}
    train = [by_id[i] for i, p in split.items() if p is Partition.TRAIN]
    cal = [by_id[i] for i, p in split.items() if p is Partition.CALIBRATION]
    locked = [by_id[i] for i, p in split.items() if p is Partition.LOCKED_TEST]
    return corpus, split, train, cal, locked


@pytest.fixture(scope="module")
def fitted():
    corpus, split, train, cal, locked = _split_corpus()
    det = ApplicabilityDetector.fit(train)
    return det, train, cal, locked


def _in_domain_event(det):
    """Return a TRAIN event whose direction/unit the detector knows."""
    # rebuild a fresh clean episode in a known direction
    gf, gt = det.known_directions[0].split("->")
    return S.generate_episode("EP-IND", gf, gt, seed=99, start_time=BASE)


# ── TRAIN-only fitting + isolation proof (tests K, L) ────────────────────

def test_K_train_only_fit_isolation(fitted):
    det, train, cal, locked = fitted
    train_ids = {e.event_id for e in train}
    cal_ids = {e.event_id for e in cal}
    locked_ids = {e.event_id for e in locked}
    manifest_ids = set(det.train_event_ids)
    assert manifest_ids == train_ids
    assert manifest_ids.isdisjoint(cal_ids)
    assert manifest_ids.isdisjoint(locked_ids)


def test_K_manifest_versions(fitted):
    det, *_ = fitted
    m = det.manifest()
    assert m["applicability_version"] == APPLICABILITY_VERSION
    assert m["detector_version"] == DETECTOR_VERSION
    assert m["feature_version"] == FEATURE_SCHEMA_VERSION
    assert m["ood_features"] == list(OOD_FEATURES)


# ── A. in-domain -> NORMAL ───────────────────────────────────────────────

def test_A_in_domain_normal(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    res = det.assess_event(ev, _mins(400))
    assert res.state is ApplicabilityState.NORMAL
    assert res.reason_codes == (A_OK,)


# ── B/C. unknown unit / unknown grade pair -> UNSUPPORTED ────────────────

def test_B_unknown_grade_pair_unsupported(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    feats = build_features(ev, _mins(400))
    res = det.assess(feats, "Z->Q", ev.unit)
    assert res.state is ApplicabilityState.UNSUPPORTED
    assert A_UNKNOWN_PAIR in res.reason_codes


def test_C_unknown_unit_unsupported(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    feats = build_features(ev, _mins(400))
    res = det.assess(feats, ev.direction, "UNKNOWN-UNIT-99")
    assert res.state is ApplicabilityState.UNSUPPORTED
    assert A_UNKNOWN_UNIT in res.reason_codes


# ── D. feature shifted beyond support -> OOD ─────────────────────────────

def test_D_feature_shift_ood(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    feats = dict(build_features(ev, _mins(400)))
    hi = det.support["MFI_online_last"][1]
    feats["MFI_online_last"] = hi * 10.0        # far outside support band
    res = det.assess(feats, ev.direction, ev.unit)
    assert res.state is ApplicabilityState.OOD
    assert A_FEATURE_OOS in res.reason_codes
    assert res.score > 0


# ── E. mildly unusual but supported -> NOT OOD ───────────────────────────

def test_E_mild_shift_not_ood(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    feats = dict(build_features(ev, _mins(400)))
    lo, hi = det.support["MFI_online_last"][0], det.support["MFI_online_last"][1]
    # nudge just inside the margin band (margin_frac of the range)
    feats["MFI_online_last"] = hi + 0.1 * det.margin_frac * (hi - lo)
    res = det.assess(feats, ev.direction, ev.unit)
    assert res.state is ApplicabilityState.NORMAL


# ── F. missing required feature -> UNAVAILABLE (defer to health, NOT OOD) ─

def test_F_missing_feature_unavailable_not_ood(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    feats = dict(build_features(ev, _mins(400)))
    feats["MFI_online_last"] = float("nan")
    res = det.assess(feats, ev.direction, ev.unit)
    assert res.state is ApplicabilityState.UNAVAILABLE
    assert A_FEATURE_UNAVAIL in res.reason_codes
    # explicitly NOT an OOD verdict
    assert res.state is not ApplicabilityState.OOD


# ── G. detector artifact unavailable -> ABSTAIN-safe UNAVAILABLE ─────────

def test_G_artifact_unavailable():
    res = unavailable_result()
    assert res.state is ApplicabilityState.UNAVAILABLE
    assert A_ARTIFACT_UNAVAIL in res.reason_codes
    assert res.is_blocking


# ── schema / version mismatch rejection ──────────────────────────────────

def test_feature_version_mismatch_rejected(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    feats = build_features(ev, _mins(400))
    with pytest.raises(ValueError):
        det.assess(feats, ev.direction, ev.unit, feature_version="WRONG-VERSION")


def test_manifest_roundtrip_rejects_version(fitted):
    det, *_ = fitted
    m = dict(det.manifest())
    m["applicability_version"] = "applicability-vBAD"
    with pytest.raises(ValueError):
        ApplicabilityDetector.from_manifest(m)
    m2 = dict(det.manifest())
    m2["detector_version"] = "iforest-knn-vBAD"
    with pytest.raises(ValueError):
        ApplicabilityDetector.from_manifest(m2)


# ── auxiliary scores reported but never decisive ─────────────────────────

def test_auxiliary_scores_reported_not_decisive(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    feats = build_features(ev, _mins(400))
    res = det.assess(feats, ev.direction, ev.unit)
    # NN distance / iforest decision are present for transparency ...
    assert "nn_distance" in res.detail
    assert "iforest_decision" in res.detail
    # ... but the deterministic verdict stands (in-domain -> NORMAL)
    assert res.state is ApplicabilityState.NORMAL


# ── fit refuses empty TRAIN ──────────────────────────────────────────────

def test_fit_requires_train_events():
    with pytest.raises(ValueError):
        ApplicabilityDetector.fit([])


# ── deterministic replay ─────────────────────────────────────────────────

def test_deterministic_replay(fitted):
    det, *_ = fitted
    ev = _in_domain_event(det)
    feats = build_features(ev, _mins(400))
    a = det.assess(feats, ev.direction, ev.unit).to_dict()
    b = det.assess(feats, ev.direction, ev.unit).to_dict()
    assert a == b
