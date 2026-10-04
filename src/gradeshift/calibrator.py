"""Calibrated uncertainty for the material-window quality estimate (Phase 6).

This layer turns a POINT estimate (from the linear baseline or the GBM) into a
calibrated PREDICTION INTERVAL via simple, auditable SPLIT-CONFORMAL calibration.

What this layer IS:
  * a finite-sample split-conformal interval with a stated nominal coverage,
    fit ONLY on the CALIBRATION partition and frozen before any locked-test look.

What this layer is NOT (kept strictly separate for later phases):
  * NOT out-of-distribution / novelty detection (Phase 7);
  * NOT sensor-health assessment (Phase 7);
  * NOT a disposition / decision engine (Phase 8);
  * NOT a product certification, and NOT "P(material is good) = coverage".

Coverage is a predictive property under the stated calibration/evaluation
assumptions on SIMULATED data — nothing more.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .provenance import Provenance
from .schemas import PredictionBundle

CALIBRATION_METHOD_VERSION = "split-conformal-v1"

# Conditioning variants, simplest first.
METHOD_MARGINAL_SYM = "marginal_symmetric"
METHOD_MARGINAL_ASYM = "marginal_asymmetric"
METHOD_PHASE_SYM = "phase_symmetric"
METHOD_PHASE_ASYM = "phase_asymmetric"
_ALL_METHODS = (METHOD_MARGINAL_SYM, METHOD_MARGINAL_ASYM,
                METHOD_PHASE_SYM, METHOD_PHASE_ASYM)

# A subgroup bucket is only trusted with at least this much INDEPENDENT support;
# otherwise it falls back transparently to the marginal (pooled) calibration.
MIN_SUBGROUP_ROWS = 40
MIN_SUBGROUP_EVENTS = 2

# Conditioning (phase buckets) and tail-splitting (asymmetry) both consume
# independent events. Below this many INDEPENDENT calibration events we refuse to
# SELECT anything but the simplest marginal-symmetric interval, no matter how much
# narrower a conditioned variant looks on the calibration set — a narrower interval
# fit on a handful of correlated episodes is not a trustworthy coverage guarantee.
MIN_EVENTS_FOR_CONDITIONING = 8


@dataclass(frozen=True)
class ResidualRecord:
    """One calibration example: the point prediction, the realised lab truth,
    and the conditioning tags. `event_id` lets us count INDEPENDENT support."""
    event_id: str
    phase: str
    direction: str
    point: float
    truth: float

    @property
    def signed(self) -> float:      # truth - point
        return self.truth - self.point

    @property
    def absolute(self) -> float:
        return abs(self.truth - self.point)


# ── Finite-sample conformal quantiles ───────────────────────────────────────

def _abs_quantile(mags: Sequence[float], level: float) -> tuple[float, bool]:
    """Finite-sample conformal quantile of nonneg magnitudes at `level`.
    Returns (q, exact): exact=False means the requested level exceeds what n
    rows can guarantee, so we cap at the max residual (coverage not guaranteed)."""
    n = len(mags)
    if n == 0:
        return 0.0, False
    s = sorted(mags)
    k = math.ceil((n + 1) * level)
    if k > n:
        return s[-1], False
    return s[max(k, 1) - 1], True


def _signed_quantile(vals: Sequence[float], level: float) -> tuple[float, bool]:
    """Finite-sample empirical quantile of SIGNED residuals at `level`."""
    n = len(vals)
    if n == 0:
        return 0.0, False
    s = sorted(vals)
    k = math.ceil((n + 1) * level)
    if k > n:
        return s[-1], False
    return s[max(k, 1) - 1], True


@dataclass(frozen=True)
class ConformalOffsets:
    """Half-widths applied to a point: interval = [point - lo, point + hi]."""
    lo: float
    hi: float
    n_rows: int
    n_events: int
    exact_guarantee: bool   # finite-sample level reachable without capping at max
    fallback: bool          # True => this bucket borrowed the marginal pool
    source_bucket: str      # "marginal" or the actual phase label used

    def to_dict(self) -> dict:
        return {"lo": self.lo, "hi": self.hi, "n_rows": self.n_rows,
                "n_events": self.n_events, "exact_guarantee": self.exact_guarantee,
                "fallback": self.fallback, "source_bucket": self.source_bucket}

    @classmethod
    def from_dict(cls, d: dict) -> "ConformalOffsets":
        return cls(lo=float(d["lo"]), hi=float(d["hi"]), n_rows=int(d["n_rows"]),
                   n_events=int(d["n_events"]), exact_guarantee=bool(d["exact_guarantee"]),
                   fallback=bool(d["fallback"]), source_bucket=str(d["source_bucket"]))


def _offsets_from(records: Sequence[ResidualRecord], method: str, nominal: float,
                  *, source_bucket: str, fallback: bool) -> ConformalOffsets:
    """Compute symmetric or asymmetric conformal offsets from residual records."""
    n_rows = len(records)
    n_events = len({r.event_id for r in records})
    if method in (METHOD_MARGINAL_SYM, METHOD_PHASE_SYM):
        q, exact = _abs_quantile([r.absolute for r in records], nominal)
        return ConformalOffsets(q, q, n_rows, n_events, exact, fallback, source_bucket)
    # asymmetric: split the two tails (alpha/2 each) on SIGNED residuals
    hi_level = (1.0 + nominal) / 2.0
    lo_level = (1.0 - nominal) / 2.0
    signed = [r.signed for r in records]
    qhi, ex_hi = _signed_quantile(signed, hi_level)
    qlo, ex_lo = _signed_quantile(signed, lo_level)
    return ConformalOffsets(max(0.0, -qlo), max(0.0, qhi), n_rows, n_events,
                            ex_hi and ex_lo, fallback, source_bucket)


def _uniform_prob_bad(lo: float, hi: float, spec) -> float:
    """PROVISIONAL uniform-within-interval mass outside the spec band.

    This is an ILLUSTRATIVE proxy only: it assumes the truth is uniform across
    the calibrated interval, which conformal methods do NOT assert. It exists so
    the PredictionBundle carries a bounded p(bad); the Phase-8 decision engine
    replaces it with a defensible quantity. Never a validated failure probability.
    """
    if spec is None:
        return 0.0
    width = hi - lo
    if width <= 0:
        return 0.0 if spec.in_spec(lo) else 1.0
    inside = max(0.0, min(hi, spec.mfi_high) - max(lo, spec.mfi_low))
    return float(min(1.0, max(0.0, 1.0 - inside / width)))


# ── The calibrator ──────────────────────────────────────────────────────────

@dataclass
class SplitConformalCalibrator:
    """Frozen split-conformal calibrator. Carries full provenance so a bundle
    can never be produced from a mismatched estimator or a malformed artifact."""
    method: str
    nominal_coverage: float
    estimator_version: str
    feature_version: str
    event_ids: tuple
    n_rows: int
    n_events: int
    marginal: ConformalOffsets
    phase: dict
    calibration_version: str = CALIBRATION_METHOD_VERSION
    min_subgroup_rows: int = MIN_SUBGROUP_ROWS
    min_subgroup_events: int = MIN_SUBGROUP_EVENTS
    provenance: Provenance = Provenance.SIMULATED

    @classmethod
    def fit(cls, records: Sequence[ResidualRecord], *, method: str,
            estimator_version: str, feature_version: str,
            nominal_coverage: float,
            min_subgroup_rows: int = MIN_SUBGROUP_ROWS,
            min_subgroup_events: int = MIN_SUBGROUP_EVENTS) -> "SplitConformalCalibrator":
        if method not in _ALL_METHODS:
            raise ValueError(f"unknown calibration method: {method}")
        if not records:
            raise ValueError("no calibration data: cannot fit a conformal interval")
        if not (0.0 < nominal_coverage < 1.0):
            raise ValueError("nominal_coverage must be in (0, 1)")
        marginal = _offsets_from(records, method, nominal_coverage,
                                 source_bucket="marginal", fallback=False)
        phase: dict[str, ConformalOffsets] = {}
        if method in (METHOD_PHASE_SYM, METHOD_PHASE_ASYM):
            by: dict[str, list[ResidualRecord]] = {}
            for r in records:
                by.setdefault(r.phase, []).append(r)
            for ph, recs in by.items():
                ne = len({r.event_id for r in recs})
                if len(recs) >= min_subgroup_rows and ne >= min_subgroup_events:
                    phase[ph] = _offsets_from(recs, method, nominal_coverage,
                                              source_bucket=ph, fallback=False)
                else:   # insufficient independent support -> transparent marginal fallback
                    phase[ph] = ConformalOffsets(
                        marginal.lo, marginal.hi, len(recs), ne,
                        marginal.exact_guarantee, True, "marginal")
        return cls(method=method, nominal_coverage=nominal_coverage,
                   estimator_version=estimator_version, feature_version=feature_version,
                   event_ids=tuple(sorted({r.event_id for r in records})),
                   n_rows=len(records), n_events=len({r.event_id for r in records}),
                   marginal=marginal, phase=phase,
                   min_subgroup_rows=min_subgroup_rows,
                   min_subgroup_events=min_subgroup_events)

    def offsets_for(self, phase_label: Optional[str]) -> ConformalOffsets:
        if self.method in (METHOD_PHASE_SYM, METHOD_PHASE_ASYM) and phase_label in self.phase:
            return self.phase[phase_label]
        return self.marginal

    def interval(self, point: float, phase_label: Optional[str] = None
                 ) -> tuple[float, float, ConformalOffsets]:
        off = self.offsets_for(phase_label)
        return point - off.lo, point + off.hi, off

    def predict_bundle(self, estimate, phase_label: Optional[str] = None,
                       spec=None) -> PredictionBundle:
        """Build a calibrated PredictionBundle. Rejects an unavailable estimate
        and any estimator/feature-version mismatch (never silently recalibrates)."""
        if not getattr(estimate, "available", False) or estimate.point_mfi is None:
            raise ValueError("cannot calibrate an unavailable estimate")
        if estimate.model_version != self.estimator_version:
            raise ValueError(
                f"estimator mismatch: calibrator fit for {self.estimator_version!r}, "
                f"got {estimate.model_version!r}")
        if getattr(estimate, "feature_version", None) != self.feature_version:
            raise ValueError("feature schema version mismatch between estimate and calibrator")
        lo, hi, _ = self.interval(estimate.point_mfi, phase_label)
        return PredictionBundle(
            event_id=estimate.event_id, decision_time=estimate.decision_time,
            point_mfi=estimate.point_mfi, lower_mfi=lo, upper_mfi=hi,
            nominal_coverage=self.nominal_coverage,
            prob_bad=_uniform_prob_bad(lo, hi, spec),
            model_version=self.estimator_version,
            calibration_version=f"{self.calibration_version}:{self.method}",
            provenance=Provenance.SIMULATED)

    # Persistence --------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "calibration_version": self.calibration_version, "method": self.method,
            "nominal_coverage": self.nominal_coverage,
            "estimator_version": self.estimator_version,
            "feature_version": self.feature_version,
            "event_ids": list(self.event_ids), "n_rows": self.n_rows,
            "n_events": self.n_events, "min_subgroup_rows": self.min_subgroup_rows,
            "min_subgroup_events": self.min_subgroup_events,
            "marginal": self.marginal.to_dict(),
            "phase": {k: v.to_dict() for k, v in self.phase.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SplitConformalCalibrator":
        if d.get("calibration_version") != CALIBRATION_METHOD_VERSION:
            raise ValueError(
                f"calibration artifact version mismatch: expected {CALIBRATION_METHOD_VERSION!r}, "
                f"got {d.get('calibration_version')!r}")
        if d.get("method") not in _ALL_METHODS:
            raise ValueError(f"malformed calibration artifact: bad method {d.get('method')!r}")
        return cls(
            method=d["method"], nominal_coverage=float(d["nominal_coverage"]),
            estimator_version=d["estimator_version"], feature_version=d["feature_version"],
            event_ids=tuple(d["event_ids"]), n_rows=int(d["n_rows"]),
            n_events=int(d["n_events"]),
            marginal=ConformalOffsets.from_dict(d["marginal"]),
            phase={k: ConformalOffsets.from_dict(v) for k, v in d.get("phase", {}).items()},
            calibration_version=d["calibration_version"],
            min_subgroup_rows=int(d.get("min_subgroup_rows", MIN_SUBGROUP_ROWS)),
            min_subgroup_events=int(d.get("min_subgroup_events", MIN_SUBGROUP_EVENTS)))

    def save(self, path: str) -> None:
        import joblib
        joblib.dump(self.to_dict(), path)

    @classmethod
    def load(cls, path: str) -> "SplitConformalCalibrator":
        from pathlib import Path
        import joblib
        from .estimator import ensure_pickle_compat_shims

        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(
                f"Persisted conformal calibrator artifact not found at: {p.resolve()}"
            )
        ensure_pickle_compat_shims()
        return cls.from_dict(joblib.load(str(p)))



# ── Coverage / width evaluation (reporting only; LOCKED after freeze) ────────

def coverage_metrics(bundles: Sequence[PredictionBundle],
                     truths: Sequence[float]) -> dict:
    """Empirical coverage, under-coverage, and width stats over (bundle, truth)."""
    n = len(bundles)
    if n == 0:
        return {"n_rows": 0, "n_events": 0, "coverage": float("nan"),
                "under_coverage": float("nan"), "mean_width": float("nan"),
                "min_width": float("nan"), "median_width": float("nan"),
                "max_width": float("nan")}
    covered = sum(1 for b, y in zip(bundles, truths) if b.lower_mfi <= y <= b.upper_mfi)
    widths = sorted(b.width for b in bundles)
    mid = widths[n // 2] if n % 2 else 0.5 * (widths[n // 2 - 1] + widths[n // 2])
    return {"n_rows": n, "coverage": covered / n, "under_coverage": 1.0 - covered / n,
            "mean_width": sum(widths) / n, "min_width": widths[0],
            "median_width": mid, "max_width": widths[-1]}


def evidence_state(bundle: PredictionBundle, spec) -> dict:
    """Separate 'point looks in spec' from 'the interval is tight enough to say so'.

    This is an EVIDENCE readout, NOT the final disposition (Phase 8 owns HOLD /
    SAMPLE NOW / PRIME-RELEASE CANDIDATE / ABSTAIN). It only demonstrates that
    uncertainty can distinguish 'looks good' from 'evidence is sufficient'.
    """
    point_in = spec.in_spec(bundle.point_mfi)
    interval_inside = spec.mfi_low <= bundle.lower_mfi and bundle.upper_mfi <= spec.mfi_high
    crosses = not interval_inside
    if point_in and crosses:
        prime_eligible = False
        note = "point looks in spec but interval crosses a limit -> evidence insufficient"
    elif point_in and interval_inside:
        prime_eligible = True
        note = "point and whole interval within spec (candidacy still needs Phase 7/8 gates)"
    else:
        prime_eligible = False
        note = "point estimate outside spec"
    return {
        "point_mfi": bundle.point_mfi,
        "interval": [bundle.lower_mfi, bundle.upper_mfi],
        "spec_band": [spec.mfi_low, spec.mfi_high],
        "point_state": "IN_SPEC" if point_in else "OUT_OF_SPEC",
        "uncertainty_state": "CROSSES_LIMIT" if crosses else "WITHIN_LIMIT",
        "prime_candidacy_eligible_by_interval": prime_eligible,
        "note": note,
    }

