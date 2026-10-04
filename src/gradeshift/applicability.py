"""Phase 7B — MODEL APPLICABILITY / OOD layer.

LOGICALLY SEPARATE from sensor health (Phase 7A) and from prediction
uncertainty (Phase 6). It answers ONLY: *is the current operating point inside
the domain the model was actually trained on?* A trustworthy, perfectly healthy
sensor can still report a state the model has never seen — that is an
applicability failure, not a health failure.

DESIGN FOR SMALL DATA (critical rule): the corpus is synthetic and tiny, so a
statistical novelty detector is UNSTABLE. Therefore:
  * DETERMINISTIC rules are PRIMARY and decide the state:
      - known unit            (seen in TRAIN)
      - known grade pair      (direction seen in TRAIN)
      - per-feature support   (within the TRAIN min/max band + documented margin)
  * The IsolationForest and nearest-neighbour distance are AUXILIARY: they are
    fit TRAIN-ONLY, reported as scores for transparency, and NEVER override the
    deterministic verdict. We do not fabricate statistical OOD accuracy.

TRAIN-ONLY: the detector is fit exclusively on TRAIN events. CALIBRATION and
LOCKED_TEST events are never seen. The persisted artifact records the training
event manifest, the feature schema version, and the detector version; a
mismatch on load or assessment is rejected.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

import numpy as np

from .estimator import RANDOM_SEED
from .features import FEATURE_SCHEMA_VERSION, build_features
from .material_identity import MaterialMapParams
from .provenance import Provenance
from .schemas import TransitionEvent

APPLICABILITY_VERSION = "applicability-v1"
DETECTOR_VERSION = "iforest-knn-v1"

# Always-present process features used for domain support (avoid lab/mw NaNs).
OOD_FEATURES = ("MFI_online_last", "MFI_online_mean_30", "H2_ratio_last",
                "bed_temp_last", "time_since_start_min")

# Documented support margin: a point is in-support if each feature lies within
# [train_min - m*range, train_max + m*range]. ENGINEERING ASSUMPTION, not tuned
# against locked-test metrics.
DEFAULT_MARGIN_FRAC = 0.25
DEFAULT_NN_THRESHOLD = 6.0   # auxiliary only (standardized L2); reported, not decisive


class ApplicabilityState(str, Enum):
    NORMAL = "NORMAL"              # inside trained domain
    OOD = "OUT_OF_DOMAIN"          # supported unit/pair but feature point outside support
    UNSUPPORTED = "UNSUPPORTED"    # unknown unit or unknown grade pair
    UNAVAILABLE = "UNAVAILABLE"    # required feature absent -> defer to sensor health


# Reason codes
A_OK = "IN_DOMAIN"
A_UNKNOWN_UNIT = "UNKNOWN_UNIT"
A_UNKNOWN_PAIR = "UNKNOWN_GRADE_PAIR"
A_FEATURE_OOS = "FEATURE_OUT_OF_SUPPORT"
A_FEATURE_UNAVAIL = "REQUIRED_FEATURE_UNAVAILABLE"
A_ARTIFACT_UNAVAIL = "DETECTOR_UNAVAILABLE"


@dataclass(frozen=True)
class ApplicabilityResult:
    """Explicit state + score + reason codes. Auxiliary scores are reported for
    transparency but do NOT change the deterministic state."""
    state: ApplicabilityState
    score: float                      # max standardized support exceedance (0 = central)
    reason_codes: tuple
    detail: dict
    feature_version: str = FEATURE_SCHEMA_VERSION
    detector_version: str = DETECTOR_VERSION
    applicability_version: str = APPLICABILITY_VERSION
    provenance: Provenance = Provenance.SIMULATED

    @property
    def is_blocking(self) -> bool:
        return self.state in (ApplicabilityState.OOD, ApplicabilityState.UNSUPPORTED,
                              ApplicabilityState.UNAVAILABLE)

    def to_dict(self) -> dict:
        return {"state": self.state.value, "score": self.score,
                "reason_codes": list(self.reason_codes), "detail": self.detail,
                "feature_version": self.feature_version,
                "detector_version": self.detector_version,
                "applicability_version": self.applicability_version,
                "provenance": self.provenance.value}


def unavailable_result(reason: str = A_ARTIFACT_UNAVAIL) -> ApplicabilityResult:
    """ABSTAIN-safe result for when the detector artifact itself is unavailable."""
    return ApplicabilityResult(ApplicabilityState.UNAVAILABLE, float("nan"),
                               (reason,), {"note": "applicability detector unavailable"})


@dataclass
class ApplicabilityDetector:
    """Frozen TRAIN-only applicability detector. Deterministic rules are primary;
    IsolationForest + NN distance are auxiliary challengers."""
    feature_version: str
    known_units: tuple
    known_directions: tuple
    ood_features: tuple
    support: dict                 # feature -> (min, max, mean, std)
    margin_frac: float
    nn_threshold: float
    train_event_ids: tuple
    n_train_rows: int
    detector_version: str = DETECTOR_VERSION
    applicability_version: str = APPLICABILITY_VERSION
    _train_std_matrix: Optional[np.ndarray] = None   # standardized TRAIN rows (for NN)
    _iforest: object = None                           # sklearn IsolationForest or None
    provenance: Provenance = Provenance.SIMULATED

    # ── fitting (TRAIN ONLY) ────────────────────────────────────────────
    @classmethod
    def fit(cls, train_events: Sequence[TransitionEvent], *,
            feature_version: str = FEATURE_SCHEMA_VERSION,
            map_params: Optional[MaterialMapParams] = None,
            margin_frac: float = DEFAULT_MARGIN_FRAC,
            nn_threshold: float = DEFAULT_NN_THRESHOLD,
            ood_features: Sequence[str] = OOD_FEATURES) -> "ApplicabilityDetector":
        from .dataset import build_rows
        if not train_events:
            raise ValueError("no TRAIN events: cannot fit an applicability detector")
        feats_matrix: list = []
        for e in train_events:
            for r in build_rows(e, map_params=map_params):
                vec = [r.features.get(n, float("nan")) for n in ood_features]
                if all(math.isfinite(v) for v in vec):
                    feats_matrix.append(vec)
        if not feats_matrix:
            raise ValueError("no finite TRAIN feature rows for applicability support")
        X = np.asarray(feats_matrix, dtype=float)
        mins, maxs = X.min(axis=0), X.max(axis=0)
        means, stds = X.mean(axis=0), X.std(axis=0)
        support = {n: (float(mins[i]), float(maxs[i]), float(means[i]), float(stds[i]))
                   for i, n in enumerate(ood_features)}
        safe_std = np.where(stds > 0, stds, 1.0)
        std_matrix = (X - means) / safe_std
        iforest = None
        try:
            from sklearn.ensemble import IsolationForest
            iforest = IsolationForest(random_state=RANDOM_SEED, n_estimators=200,
                                      contamination="auto").fit(std_matrix)
        except Exception:
            iforest = None   # auxiliary only; absence never blocks the deterministic path
        return cls(
            feature_version=feature_version,
            known_units=tuple(sorted({e.unit for e in train_events})),
            known_directions=tuple(sorted({e.direction for e in train_events})),
            ood_features=tuple(ood_features), support=support,
            margin_frac=margin_frac, nn_threshold=nn_threshold,
            train_event_ids=tuple(sorted({e.event_id for e in train_events})),
            n_train_rows=int(X.shape[0]), _train_std_matrix=std_matrix, _iforest=iforest)

    # ── assessment ──────────────────────────────────────────────────────
    def _standardize(self, vec) -> np.ndarray:
        means = np.array([self.support[n][2] for n in self.ood_features])
        stds = np.array([self.support[n][3] for n in self.ood_features])
        safe = np.where(stds > 0, stds, 1.0)
        return (np.asarray(vec, dtype=float) - means) / safe

    def assess(self, feats: dict, direction: str, unit: str,
               feature_version: str = FEATURE_SCHEMA_VERSION) -> ApplicabilityResult:
        """Deterministic verdict first; auxiliary scores reported alongside."""
        if feature_version != self.feature_version:
            raise ValueError(
                f"feature schema mismatch: detector fit for {self.feature_version!r}, "
                f"got {feature_version!r}")
        vec = [feats.get(n, float("nan")) for n in self.ood_features]
        detail: dict = {"features": dict(zip(self.ood_features, vec)),
                        "known_units": list(self.known_units),
                        "known_directions": list(self.known_directions)}

        # (1) required feature unavailable -> defer to sensor health (NOT OOD)
        if any(not math.isfinite(v) for v in vec):
            missing = [n for n, v in zip(self.ood_features, vec) if not math.isfinite(v)]
            detail["missing_features"] = missing
            return ApplicabilityResult(ApplicabilityState.UNAVAILABLE, float("nan"),
                                       (A_FEATURE_UNAVAIL,), detail)

        # auxiliary scores (reported, never decisive)
        z = self._standardize(vec)
        nn = float("nan")
        if self._train_std_matrix is not None and len(self._train_std_matrix):
            nn = float(np.min(np.linalg.norm(self._train_std_matrix - z, axis=1)))
        iso = (float(self._iforest.decision_function(z.reshape(1, -1))[0])
               if self._iforest is not None else float("nan"))
        detail.update({"nn_distance": nn, "iforest_decision": iso,
                       "nn_threshold": self.nn_threshold})

        # (2) unknown unit / unknown grade pair -> UNSUPPORTED (deterministic)
        reasons = []
        if unit not in self.known_units:
            reasons.append(A_UNKNOWN_UNIT)
        if direction not in self.known_directions:
            reasons.append(A_UNKNOWN_PAIR)
        if reasons:
            return ApplicabilityResult(ApplicabilityState.UNSUPPORTED, float("nan"),
                                       tuple(reasons), detail)

        # (3) per-feature support band (PRIMARY OOD rule, documented margin)
        exceed, offenders = 0.0, []
        for n, v in zip(self.ood_features, vec):
            lo, hi, _, _ = self.support[n]
            rng = hi - lo if hi > lo else max(abs(hi), 1.0)
            band_lo, band_hi = lo - self.margin_frac * rng, hi + self.margin_frac * rng
            if v < band_lo or v > band_hi:
                frac = (band_lo - v if v < band_lo else v - band_hi) / rng
                exceed = max(exceed, frac)
                offenders.append({"feature": n, "value": v, "band": [band_lo, band_hi]})
        detail["support_exceedance"] = exceed
        if offenders:
            detail["offenders"] = offenders
            return ApplicabilityResult(ApplicabilityState.OOD, exceed,
                                       (A_FEATURE_OOS,), detail)

        # (4) in-domain
        return ApplicabilityResult(ApplicabilityState.NORMAL, exceed, (A_OK,), detail)

    def assess_event(self, event: TransitionEvent, t,
                     map_params: Optional[MaterialMapParams] = None) -> ApplicabilityResult:
        """Convenience: build the as-of feature vector and assess it."""
        feats = build_features(event, t, map_params)
        return self.assess(feats, event.direction, event.unit, FEATURE_SCHEMA_VERSION)

    # ── manifest / persistence ──────────────────────────────────────────
    def manifest(self) -> dict:
        """Auditable, serialisable summary (no sklearn object)."""
        return {"applicability_version": self.applicability_version,
                "detector_version": self.detector_version,
                "feature_version": self.feature_version,
                "known_units": list(self.known_units),
                "known_directions": list(self.known_directions),
                "ood_features": list(self.ood_features),
                "support": {k: list(v) for k, v in self.support.items()},
                "margin_frac": self.margin_frac, "nn_threshold": self.nn_threshold,
                "train_event_ids": list(self.train_event_ids),
                "n_train_rows": self.n_train_rows,
                "iforest_fitted": self._iforest is not None,
                "provenance": self.provenance.value}

    @classmethod
    def from_manifest(cls, d: dict, *, train_std_matrix=None,
                      iforest=None) -> "ApplicabilityDetector":
        if d.get("applicability_version") != APPLICABILITY_VERSION:
            raise ValueError(
                f"applicability artifact version mismatch: expected {APPLICABILITY_VERSION!r}, "
                f"got {d.get('applicability_version')!r}")
        if d.get("detector_version") != DETECTOR_VERSION:
            raise ValueError(
                f"detector version mismatch: expected {DETECTOR_VERSION!r}, "
                f"got {d.get('detector_version')!r}")
        return cls(
            feature_version=d["feature_version"],
            known_units=tuple(d["known_units"]),
            known_directions=tuple(d["known_directions"]),
            ood_features=tuple(d["ood_features"]),
            support={k: tuple(v) for k, v in d["support"].items()},
            margin_frac=float(d["margin_frac"]), nn_threshold=float(d["nn_threshold"]),
            train_event_ids=tuple(d["train_event_ids"]),
            n_train_rows=int(d["n_train_rows"]),
            _train_std_matrix=train_std_matrix, _iforest=iforest)

    def save(self, path: str) -> None:
        import joblib
        joblib.dump({"manifest": self.manifest(),
                     "train_std_matrix": self._train_std_matrix,
                     "iforest": self._iforest}, path)

    @classmethod
    def load(cls, path: str) -> "ApplicabilityDetector":
        from pathlib import Path
        import joblib
        from .estimator import ensure_pickle_compat_shims

        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"Persisted applicability detector artifact not found at: {p.resolve()}"
            )
        ensure_pickle_compat_shims()
        try:
            blob = joblib.load(str(p))
            train_std_matrix = blob.get("train_std_matrix")
            iforest = blob.get("iforest")
            if iforest is not None and train_std_matrix is not None and len(train_std_matrix):
                try:
                    _ = float(iforest.decision_function(train_std_matrix[:1])[0])
                except Exception:
                    try:
                        from sklearn.ensemble import IsolationForest
                        iforest = IsolationForest(
                            random_state=RANDOM_SEED,
                            n_estimators=200,
                            contamination="auto",
                        ).fit(train_std_matrix)
                    except Exception:
                        iforest = None
            return cls.from_manifest(
                blob["manifest"],
                train_std_matrix=train_std_matrix,
                iforest=iforest,
            )
        except ValueError:
            raise
        except Exception:
            # If Cython Tree struct ABI differs across major Python/scikit-learn versions
            # (e.g., Python 3.14 vs Python 3.10), deterministically fit on the canonical TRAIN split.
            from .partition import Partition, chronological_split
            from .pipeline import default_corpus

            corpus = default_corpus(n_per_dir=3)
            parts = chronological_split(corpus)
            train_events = [e for e in corpus if parts[e.event_id] is Partition.TRAIN]
            return cls.fit(train_events)


