"""Quality estimators for the material window (Phase 5).

Transparent baselines FIRST, then a CPU-friendly histogram gradient-boosting
estimator. Every estimator is time-causal: it consumes only an as-of feature
vector. No conformal interval, no OOD, no disposition logic yet (later phases).

PRODUCT INTEGRITY: an estimator returns either a valid point estimate or an
explicit UNAVAILABLE state — never a random/mock fallback, never a certification.
"""
from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Sequence

import numpy as np

from . import config as C
from .features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, build_features
from .material_identity import MaterialMapParams
from .provenance import Provenance
from .schemas import PredictionBundle, TransitionEvent

GBM_MODEL_VERSION = "gbm-mfi-v1"
LINREG_MODEL_VERSION = "linreg-mfi-v1"
LASTLAB_MODEL_VERSION = "lastlab-v1"
DETERMINISTIC_MODEL_VERSION = "online-proxy-v1"
RANDOM_SEED = 42

# Process-only subset for the simple linear baseline.
_LINREG_FEATURES = [
    "MFI_online_last", "MFI_online_mean_30", "MFI_online_slope_60",
    "H2_ratio_last", "time_since_transition_min",
]


@dataclass(frozen=True)
class QualityEstimate:
    """Phase-5 output: a point MFI estimate for the associated material window,
    or an explicit unavailable state. Interval/p(bad) are intentionally absent —
    they are filled by the Phase-6 calibrator."""
    event_id: str
    decision_time: datetime
    point_mfi: Optional[float]
    available: bool
    model_version: str
    feature_version: str = FEATURE_SCHEMA_VERSION
    reason: str = ""
    provenance: Provenance = Provenance.SIMULATED

    def as_prediction_bundle(self, nominal_coverage: float = C.POLICY.nominal_coverage
                             ) -> PredictionBundle:
        """Provisional, UNCALIBRATED bundle (degenerate interval). Must NOT be used
        for disposition — Phase 6 replaces the interval and p(bad)."""
        if not self.available or self.point_mfi is None:
            raise ValueError("cannot build a prediction bundle from an unavailable estimate")
        return PredictionBundle(
            event_id=self.event_id, decision_time=self.decision_time,
            point_mfi=self.point_mfi, lower_mfi=self.point_mfi, upper_mfi=self.point_mfi,
            nominal_coverage=nominal_coverage, prob_bad=0.0,
            model_version=self.model_version, calibration_version="UNCALIBRATED-ph5",
            provenance=Provenance.SIMULATED)


def _ok(x: Optional[float]) -> bool:
    return x is not None and not (isinstance(x, float) and np.isnan(x))


# ── Transparent baselines ──────────────────────────────────────────────────


class LastLabBaseline:
    """Carry forward the last valid laboratory result."""
    model_version = LASTLAB_MODEL_VERSION

    def predict_one(self, feats: dict[str, float]) -> Optional[float]:
        v = feats.get("lab_last_mfi")
        return float(v) if _ok(v) else None


class DeterministicProcessBaseline:
    """Use the online analyzer reading at t as a direct quality proxy (no fit)."""
    model_version = DETERMINISTIC_MODEL_VERSION

    def predict_one(self, feats: dict[str, float]) -> Optional[float]:
        v = feats.get("MFI_online_last")
        return float(v) if _ok(v) else None


class LinearProcessBaseline:
    """Ordinary least squares on a small, interpretable process-feature subset.
    Mean-imputes missing values (parameters learned on TRAIN only)."""
    model_version = LINREG_MODEL_VERSION

    def __init__(self) -> None:
        from sklearn.linear_model import LinearRegression
        self._lr = LinearRegression()
        self._means: Optional[np.ndarray] = None
        self._fitted = False

    def _matrix(self, rows_feats: Sequence[dict[str, float]]) -> np.ndarray:
        return np.array([[f.get(n, np.nan) for n in _LINREG_FEATURES] for f in rows_feats],
                        dtype=float)

    def fit(self, feats: Sequence[dict[str, float]], y: np.ndarray) -> "LinearProcessBaseline":
        X = self._matrix(feats)
        self._means = np.nanmean(X, axis=0)
        self._means = np.where(np.isnan(self._means), 0.0, self._means)
        Xi = np.where(np.isnan(X), self._means, X)
        self._lr.fit(Xi, y)
        self._fitted = True
        return self

    def predict_one(self, feats: dict[str, float]) -> Optional[float]:
        if not self._fitted:
            return None
        X = self._matrix([feats])
        Xi = np.where(np.isnan(X), self._means, X)
        return float(self._lr.predict(Xi)[0])


# ── Primary model: histogram gradient boosting ─────────────────────────────


class GBMQualityEstimator:
    """CPU-friendly HistGradientBoostingRegressor. Handles NaN natively, fixed
    seed, explicit feature schema. Reproducible given corpus + seed + code."""
    model_version = GBM_MODEL_VERSION

    def __init__(self, random_state: int = RANDOM_SEED) -> None:
        from sklearn.ensemble import HistGradientBoostingRegressor
        self.random_state = random_state
        self._gbm = HistGradientBoostingRegressor(
            random_state=random_state, max_iter=300, learning_rate=0.05,
            max_depth=3, min_samples_leaf=10, l2_regularization=1.0)
        self.feature_names = list(FEATURE_NAMES)
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "GBMQualityEstimator":
        self._gbm.fit(X, y)
        self._fitted = True
        return self

    def _vec(self, feats: dict[str, float]) -> np.ndarray:
        return np.array([[feats[n] for n in self.feature_names]], dtype=float)

    def predict_one(self, feats: dict[str, float]) -> Optional[float]:
        if not self._fitted:
            return None
        return float(self._gbm.predict(self._vec(feats))[0])

    def estimate(self, event: TransitionEvent, t: datetime,
                 map_params: Optional[MaterialMapParams] = None) -> QualityEstimate:
        """End-to-end: build as-of features, return a QualityEstimate or an
        explicit unavailable state (no required process evidence at t)."""
        from .alignment import as_of
        # Guard first: if no process observation exists as-of t (e.g. t precedes
        # the episode), return unavailable WITHOUT attempting a material mapping.
        snap = as_of(event, t)
        if not any(o.tag == "MFI_online" for o in snap.observations):
            return QualityEstimate(event.event_id, t, None, False, self.model_version,
                                   reason="no process evidence available at decision time")
        feats = build_features(event, t, map_params)
        if not _ok(feats.get("MFI_online_last")):
            return QualityEstimate(event.event_id, t, None, False, self.model_version,
                                   reason="no process evidence available at decision time")
        if not self._fitted:
            return QualityEstimate(event.event_id, t, None, False, self.model_version,
                                   reason="model not fitted")
        return QualityEstimate(event.event_id, t, self.predict_one(feats), True,
                               self.model_version)

    # Persistence --------------------------------------------------------
    def save(self, path: str) -> None:
        import joblib
        joblib.dump({"gbm": self._gbm, "feature_names": self.feature_names,
                     "model_version": self.model_version, "random_state": self.random_state,
                     "feature_version": FEATURE_SCHEMA_VERSION}, path)

    @classmethod
    def load(cls, path: str) -> "GBMQualityEstimator":
        import joblib
        blob = joblib.load(path)
        obj = cls(random_state=blob["random_state"])
        obj._gbm = blob["gbm"]
        obj.feature_names = blob["feature_names"]
        obj._fitted = True
        return obj


# ── Metrics ────────────────────────────────────────────────────────────────


def regression_metrics(pred: Sequence[Optional[float]], truth: Sequence[float]
                       ) -> dict[str, float]:
    """MAE / RMSE / bias over pairs where a prediction is available."""
    e = [(float(p) - float(y)) for p, y in zip(pred, truth) if _ok(p)]
    n = len(e)
    if n == 0:
        return {"n": 0, "coverage": 0.0, "mae": float("nan"),
                "rmse": float("nan"), "bias": float("nan")}
    arr = np.array(e)
    return {"n": n, "coverage": n / len(truth) if truth else 0.0,
            "mae": float(np.mean(np.abs(arr))),
            "rmse": float(np.sqrt(np.mean(arr ** 2))),
            "bias": float(np.mean(arr))}


def runtime_versions() -> dict[str, str]:
    import sklearn
    return {"python": platform.python_version(), "numpy": np.__version__,
            "sklearn": sklearn.__version__}
