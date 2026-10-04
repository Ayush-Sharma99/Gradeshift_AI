"""Phase 7A — deterministic SENSOR / DATA HEALTH layer.

This layer is LOGICALLY SEPARATE from the OOD/applicability layer (Phase 7B)
and from calibrated prediction uncertainty (Phase 6). It answers ONLY one
question: *are the raw observations themselves trustworthy and available at
decision time t?* It never asks whether the operating point is inside the
model's trained domain (that is applicability), nor how wide the prediction
interval is (that is calibration).

Every check is a PURE function of the as-of observation slice: observations
with timestamp <= t, kept in their original acquisition order so that
timestamp disorder is still detectable (the alignment firewall sorts; here we
deliberately preserve arrival order for the integrity checks). Appending any
future observation (ts > t) cannot change a result at an earlier t — this is
asserted by the adversarial no-future tests.

THRESHOLD PROVENANCE (anti-overclaim): every number below is an ENGINEERING
ASSUMPTION, a SIMULATED-generator constraint, or a POLICY choice. NONE of them
are HMEL operating limits. They are documented, versioned, and configurable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Sequence

from .provenance import Provenance
from .schemas import TransitionEvent

HEALTH_RULES_VERSION = "health-rules-v1"


class HealthState(str, Enum):
    """Do NOT collapse failures into one generic state."""
    NORMAL = "NORMAL"
    DEGRADED = "DEGRADED"        # LOW_CONFIDENCE: usable but flagged
    ABNORMAL = "ABNORMAL"        # untrustworthy -> hard-gate can force ABSTAIN
    UNAVAILABLE = "UNAVAILABLE"  # a required signal is absent entirely


_RANK = {HealthState.NORMAL: 0, HealthState.DEGRADED: 1,
         HealthState.ABNORMAL: 2, HealthState.UNAVAILABLE: 3}


def worst_state(states: Sequence[HealthState]) -> HealthState:
    s = list(states)
    return max(s, key=lambda x: _RANK[x]) if s else HealthState.NORMAL


# ── Machine-readable reason codes (one per distinct failure mode) ───────────
R_OK = "OK"
R_MISSING = "MISSING_SIGNAL"
R_MALFORMED = "MALFORMED_VALUE"
R_STALE = "STALE"
R_GAP = "TIME_GAP"
R_FROZEN = "FROZEN_VALUE"
R_RANGE_LOW = "RANGE_LOW"
R_RANGE_HIGH = "RANGE_HIGH"
R_SPIKE = "RATE_SPIKE"
R_DISORDER = "TIMESTAMP_DISORDER"
R_DUPLICATE = "TIMESTAMP_DUPLICATE"

# Where each rule's authority comes from — NEVER an HMEL operating limit.
HEALTH_RULE_PROVENANCE = {
    R_RANGE_LOW: "ENGINEERING ASSUMPTION (physical plausibility band)",
    R_RANGE_HIGH: "ENGINEERING ASSUMPTION (physical plausibility band)",
    R_STALE: "POLICY (freshness horizon relative to 1-min SIMULATED cadence)",
    R_GAP: "SIMULATED-generator cadence constraint",
    R_FROZEN: "ENGINEERING ASSUMPTION (a noisy analyzer is never truly constant)",
    R_SPIKE: "ENGINEERING ASSUMPTION (max plausible per-sample fractional move)",
    R_DISORDER: "DATA-INTEGRITY rule (acquisition timestamps must be monotone)",
    R_DUPLICATE: "DATA-INTEGRITY rule (no duplicate acquisition timestamps)",
    R_MISSING: "POLICY (required-signal availability at decision time)",
    R_MALFORMED: "DATA-INTEGRITY rule (values must be finite numerics)",
}


@dataclass(frozen=True)
class HealthThresholds:
    """All values are ASSUMPTIONS/POLICY, documented and versioned."""
    max_age_min: float = 10.0        # POLICY: latest obs older than this -> DEGRADED
    max_stale_min: float = 20.0      # POLICY: older than this -> ABNORMAL (stale)
    max_gap_min: float = 15.0        # cadence: intra-series gap over this -> DEGRADED
    freeze_window_min: float = 20.0  # trailing window inspected for a frozen sensor
    freeze_min_samples: int = 8      # need this many samples before judging frozen
    freeze_abs_tol: float = 1e-6     # abs range over window below this -> FROZEN
    freeze_rel_tol: float = 1e-4     # OR relative range below this -> FROZEN
    spike_rel_jump: float = 0.5      # |Δ|/max(|prev|,eps) over this -> RATE_SPIKE
    ranges: dict = field(default_factory=lambda: {
        "MFI_online": (0.01, 100.0),   # g/10min; ASSUMPTION spanning grades A..B
        "H2_ratio": (0.0, 1.0),        # SIMULATED hydrogen setpoint-fraction axis
        "bed_temp": (40.0, 130.0),     # degC; ENGINEERING ASSUMPTION
    })
    required_signals: tuple = ("MFI_online",)   # POLICY: critical for the estimator
    monitored_signals: tuple = ("MFI_online", "H2_ratio", "bed_temp")
    # Frozen/spike checks apply ONLY to MEASURED, noisy signals. H2_ratio is a
    # SETPOINT (piecewise-constant by design): a flat run or a setpoint step is
    # expected behaviour, not a fault — so it is excluded here. ASSUMPTION.
    variation_expected_signals: tuple = ("MFI_online", "bed_temp")
    version: str = HEALTH_RULES_VERSION


DEFAULT_THRESHOLDS = HealthThresholds()


@dataclass(frozen=True)
class HealthFinding:
    """One triggered check: carries state, severity, reason, signal, window."""
    signal: str
    state: HealthState
    severity: int
    reason_code: str
    detail: str
    window: Optional[tuple]      # (iso_start, iso_end) of inspected obs, or None
    n_obs: int
    rule_version: str = HEALTH_RULES_VERSION
    provenance: Provenance = Provenance.SIMULATED

    def to_dict(self) -> dict:
        return {"signal": self.signal, "state": self.state.value,
                "severity": self.severity, "reason_code": self.reason_code,
                "detail": self.detail, "window": list(self.window) if self.window else None,
                "n_obs": self.n_obs, "rule_version": self.rule_version,
                "rule_provenance": HEALTH_RULE_PROVENANCE.get(self.reason_code, ""),
                "provenance": self.provenance.value}


@dataclass(frozen=True)
class SensorHealthReport:
    """Aggregate per-signal + overall state. Individual states are preserved;
    they are NEVER collapsed into a single scalar confidence."""
    as_of: datetime
    overall_state: HealthState
    required_available: bool
    signal_states: dict
    findings: tuple
    rule_version: str = HEALTH_RULES_VERSION
    provenance: Provenance = Provenance.SIMULATED

    @property
    def is_blocking(self) -> bool:
        """A critical health failure that a hard gate may turn into ABSTAIN."""
        return self.overall_state in (HealthState.ABNORMAL, HealthState.UNAVAILABLE)

    def reason_codes(self) -> list:
        return sorted({f.reason_code for f in self.findings if f.reason_code != R_OK})

    def to_dict(self) -> dict:
        return {"as_of": self.as_of.isoformat(), "overall_state": self.overall_state.value,
                "required_available": self.required_available,
                "signal_states": {k: v.value for k, v in self.signal_states.items()},
                "reason_codes": self.reason_codes(),
                "findings": [f.to_dict() for f in self.findings],
                "rule_version": self.rule_version, "provenance": self.provenance.value}


# ── as-of observation slice (original order preserved for integrity checks) ──

def _asof_obs(event: TransitionEvent, tag: str, t: datetime) -> list:
    """Observations for `tag` with timestamp <= t, in ORIGINAL acquisition
    order (NOT re-sorted) so timestamp disorder remains visible. Pure as-of."""
    return [(o.timestamp, float(o.value)) for o in event.series
            if o.tag == tag and o.timestamp <= t]


def _mk(signal, state, reason, detail, window, n):
    return HealthFinding(signal, state, _RANK[state], reason, detail, window, n)


def _check_signal(pairs, tag, t, thr) -> list:
    """Run every deterministic check for one signal; return all triggered
    findings (plus a NORMAL finding if the signal is clean)."""
    if not pairs:
        return [_mk(tag, HealthState.UNAVAILABLE, R_MISSING,
                    "no observations as-of t", None, 0)]
    ts = [p[0] for p in pairs]
    vals = [p[1] for p in pairs]
    n = len(pairs)
    window = (ts[0].isoformat(), ts[-1].isoformat())
    findings: list = []

    # 1. malformed (non-finite) values
    if any(not math.isfinite(v) for v in vals):
        findings.append(_mk(tag, HealthState.ABNORMAL, R_MALFORMED,
                            "non-finite value present", window, n))
    finite = [(tt, v) for tt, v in pairs if math.isfinite(v)]

    # 2. timestamp disorder / duplicates (needs ORIGINAL arrival order)
    if any(b < a for a, b in zip(ts, ts[1:])):
        findings.append(_mk(tag, HealthState.ABNORMAL, R_DISORDER,
                            "acquisition timestamps not monotincreasing", window, n))
    if any(b == a for a, b in zip(ts, ts[1:])):
        findings.append(_mk(tag, HealthState.DEGRADED, R_DUPLICATE,
                            "duplicate acquisition timestamps", window, n))

    # 3. engineering-range violations
    lo, hi = thr.ranges.get(tag, (float("-inf"), float("inf")))
    below = [(tt, v) for tt, v in finite if v < lo]
    above = [(tt, v) for tt, v in finite if v > hi]
    if below:
        tt, v = min(below, key=lambda p: p[1])
        findings.append(_mk(tag, HealthState.ABNORMAL, R_RANGE_LOW,
                            f"value {v:.4g} < {lo:g} at {tt.isoformat()}", window, n))
    if above:
        tt, v = max(above, key=lambda p: p[1])
        findings.append(_mk(tag, HealthState.ABNORMAL, R_RANGE_HIGH,
                            f"value {v:.4g} > {hi:g} at {tt.isoformat()}", window, n))

    # 4. freshness / staleness (relative to decision time t)
    age = (t - ts[-1]).total_seconds() / 60.0
    if age > thr.max_stale_min:
        findings.append(_mk(tag, HealthState.ABNORMAL, R_STALE,
                            f"latest obs {age:.1f} min old (> {thr.max_stale_min})", window, n))
    elif age > thr.max_age_min:
        findings.append(_mk(tag, HealthState.DEGRADED, R_STALE,
                            f"latest obs {age:.1f} min old (> {thr.max_age_min})", window, n))

    # 5. excessive intra-series gap
    gaps = [(b - a).total_seconds() / 60.0 for a, b in zip(ts, ts[1:])]
    if gaps and max(gaps) > thr.max_gap_min:
        findings.append(_mk(tag, HealthState.DEGRADED, R_GAP,
                            f"max gap {max(gaps):.1f} min (> {thr.max_gap_min})", window, n))

    # 6. frozen value over a trailing window that SHOULD contain noise
    #    (only for MEASURED signals; setpoints are legitimately constant)
    if tag in thr.variation_expected_signals:
        lo_t = t - timedelta(minutes=thr.freeze_window_min)
        wv = [v for tt, v in finite if tt >= lo_t]
        if len(wv) >= thr.freeze_min_samples:
            rng = max(wv) - min(wv)
            # ABSOLUTE tolerance only: a frozen sensor repeats a value exactly
            # (range ~0); any genuine analyzer noise gives range >> tol. A pure
            # relative tolerance would falsely flag a large-magnitude noisy
            # signal, so we deliberately do NOT use one. (freeze_rel_tol kept for
            # documentation / future per-signal tuning.)
            tol = thr.freeze_abs_tol
            if rng <= tol:
                findings.append(_mk(tag, HealthState.ABNORMAL, R_FROZEN,
                                   f"range {rng:.3g} <= tol {tol:.3g} over {len(wv)} samples",
                                   window, n))

    # 7. rate-of-change spike between consecutive samples (measured signals only)
    if tag in thr.variation_expected_signals:
        max_j, j_at = 0.0, None
        for (ta, va), (tb, vb) in zip(finite, finite[1:]):
            j = abs(vb - va) / max(abs(va), 1e-9)
            if j > max_j:
                max_j, j_at = j, tb
        if max_j > thr.spike_rel_jump:
            findings.append(_mk(tag, HealthState.ABNORMAL, R_SPIKE,
                               f"fractional jump {max_j:.2f} (> {thr.spike_rel_jump}) at "
                               f"{j_at.isoformat()}", window, n))

    if not findings:
        findings.append(_mk(tag, HealthState.NORMAL, R_OK, "all checks pass", window, n))
    return findings


def assess_sensor_health(event: TransitionEvent, t: datetime,
                         thresholds: Optional[HealthThresholds] = None
                         ) -> SensorHealthReport:
    """Deterministic sensor/data-health assessment at decision time t.

    Overall state is driven by the REQUIRED signals; a problem on a monitored
    but non-required signal degrades confidence (at most DEGRADED) rather than
    blocking, so health failures are never collapsed indiscriminately."""
    thr = thresholds or DEFAULT_THRESHOLDS
    all_findings: list = []
    signal_states: dict = {}
    for tag in thr.monitored_signals:
        fs = _check_signal(_asof_obs(event, tag, t), tag, t, thr)
        all_findings.extend(fs)
        signal_states[tag] = worst_state([f.state for f in fs])

    required_available = all(
        signal_states.get(s) != HealthState.UNAVAILABLE for s in thr.required_signals)
    overall = worst_state([signal_states[s] for s in thr.required_signals])
    nonreq = [signal_states[s] for s in thr.monitored_signals
              if s not in thr.required_signals]
    if nonreq:
        nw = worst_state(nonreq)
        capped = nw if _RANK[nw] <= _RANK[HealthState.DEGRADED] else HealthState.DEGRADED
        overall = worst_state([overall, capped])
    return SensorHealthReport(as_of=t, overall_state=overall,
                              required_available=required_available,
                              signal_states=signal_states, findings=tuple(all_findings))
