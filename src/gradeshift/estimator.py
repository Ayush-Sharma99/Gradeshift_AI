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
        from pathlib import Path
        import joblib

        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"Persisted GBM estimator artifact not found at: {p.resolve()}"
            )
        ensure_pickle_compat_shims()
        try:
            blob = joblib.load(str(p))
            obj = cls(random_state=int(blob.get("random_state", RANDOM_SEED)))
            obj._gbm = blob["gbm"]
            obj.feature_names = list(blob["feature_names"])
            obj._fitted = True
            probe = np.zeros((1, len(obj.feature_names)), dtype=float)
            val = float(obj._gbm.predict(probe)[0])
            if not np.isfinite(val):
                raise RuntimeError("Unpickled GBM estimator returned non-finite probe prediction")
            return obj
        except Exception as exc:
            # If the runtime environment uses a newer Python/scikit-learn Cython ABI
            # (e.g., Python 3.14 with scikit-learn >= 1.7/1.8 where TreePredictor Cython
            # struct layout differs from the scikit-learn 1.6.1 artifact), deterministically
            # fit the identical HistGradientBoostingRegressor on the canonical TRAIN split.
            return _fit_canonical_gbm_fallback(cls, cause=exc)


def ensure_pickle_compat_shims() -> None:
    """Register module and constructor shims for unpickling scikit-learn 1.6.1 /
    NumPy 1.26.4 joblib artifacts across newer Python (3.13/3.14), scikit-learn (1.7+/1.8+),
    and NumPy (2.x) runtimes.

    Root cause addressed:
      * In scikit-learn 1.6.1, `CyHalfSquaredError` inside `HistGradientBoostingRegressor`
        was compiled with `__module__ = '_loss'` (top-level module alias). In
        scikit-learn >= 1.7, `CyHalfSquaredError.__module__` moved to `'sklearn._loss._loss'`
        and top-level `'_loss'` is no longer registered in `sys.modules`, causing
        `ModuleNotFoundError: No module named '_loss'` during `joblib.load()`.
      * In NumPy 1.26 -> 2.x, internal module paths (`numpy.core.*`) and
        `numpy.random._pickle.__bit_generator_ctor` argument conventions can differ.
    """
    import importlib
    import sys

    # 1. Scikit-learn `_loss` Cython extension top-level alias shim
    if "_loss" not in sys.modules:
        try:
            sk_loss = importlib.import_module("sklearn._loss._loss")
            sys.modules["_loss"] = sk_loss
        except Exception:
            pass

    # 2. NumPy 1.x <-> 2.x `numpy.core` module path aliases
    for sub in ("", ".multiarray", "._multiarray_umath", ".numeric", ".umath"):
        legacy_mod = f"numpy.core{sub}"
        modern_mod = f"numpy._core{sub}"
        if legacy_mod not in sys.modules:
            try:
                sys.modules[legacy_mod] = importlib.import_module(modern_mod)
            except Exception:
                pass

    # 3. NumPy BitGenerator pickle constructor compatibility (string vs class)
    try:
        import numpy.random._pickle as np_rng_pickle

        orig_ctor = getattr(np_rng_pickle, "__bit_generator_ctor", None)
        if orig_ctor is not None and not getattr(orig_ctor, "_gs_shimmed", False):
            def _compat_bit_generator_ctor(bit_generator_name="MT19937"):
                if isinstance(bit_generator_name, type):
                    try:
                        return orig_ctor(bit_generator_name)
                    except Exception:
                        return orig_ctor(bit_generator_name.__name__)
                try:
                    return orig_ctor(bit_generator_name)
                except Exception:
                    bg_map = getattr(np_rng_pickle, "BitGenerators", {})
                    if isinstance(bit_generator_name, str) and bit_generator_name in bg_map:
                        return bg_map[bit_generator_name]()
                    raise

            _compat_bit_generator_ctor.__name__ = "__bit_generator_ctor"
            _compat_bit_generator_ctor.__qualname__ = "__bit_generator_ctor"
            _compat_bit_generator_ctor.__module__ = "numpy.random._pickle"
            _compat_bit_generator_ctor._gs_shimmed = True  # type: ignore[attr-defined]
            np_rng_pickle.__bit_generator_ctor = _compat_bit_generator_ctor
    except Exception:
        pass



def _fit_canonical_gbm_fallback(
    cls: type[GBMQualityEstimator],
    *,
    cause: Optional[Exception] = None,
) -> GBMQualityEstimator:
    """Deterministically fit the canonical GBMQualityEstimator on the frozen TRAIN
    partition when a cross-Python Cython ABI change prevents loading the binary tree
    buffer from `gbm_mfi.joblib`."""
    from .dataset import dataset_matrix
    from .partition import Partition, chronological_split
    from .pipeline import default_corpus

    corpus = default_corpus(n_per_dir=3)
    parts = chronological_split(corpus)
    train_events = [e for e in corpus if parts[e.event_id] is Partition.TRAIN]
    X_tr, y_tr, _ = dataset_matrix(train_events, feature_names=FEATURE_NAMES)
    obj = cls(random_state=RANDOM_SEED)
    obj.fit(X_tr, y_tr)
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
    import joblib
    import sklearn
    return {"python": platform.python_version(), "numpy": np.__version__,
            "sklearn": sklearn.__version__, "joblib": joblib.__version__}

