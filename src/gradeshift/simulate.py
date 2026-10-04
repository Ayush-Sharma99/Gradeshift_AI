"""Seeded synthetic transition-episode generator  (fixes defect D1).

Everything here is SIMULATED/ILLUSTRATIVE — never presented as HMEL data.

Design (intentionally minimal, internally consistent physics):
  * A single analyte of record, MFI (g/10min).
  * A monotonic kinetic law maps a hydrogen-ratio setpoint h to an INSTANTANEOUS
    MFI:  ln(MFI_inst) = a + b·h.  The constants (a, b) are solved from two
    anchor grades so that EACH grade's derived hydrogen setpoint reproduces its
    configured target MFI EXACTLY. Steady state == target holds by construction,
    for any target in config — this is the structural fix for the inherited
    off-spec simulator.
  * The reactor bed mixes first-order (CSTR washout) in ln(MFI) space toward the
    instantaneous setpoint:  d/dt lnMFI_bed = (lnMFI_inst − lnMFI_bed)/tau.
    Hence at steady state lnMFI_bed → lnMFI_inst(h) → ln(target).
  * The online analyzer sees the bed value delayed by a transport/plug-flow
    delay theta, plus multiplicative measurement noise.
  * Lab samples measure the TRUE bed material at collected_at; the result is only
    knowable at result_at = collected_at + lab latency (the blind window).

The episode is the atomic unit (one TransitionEvent) and is deterministic under
a fixed seed.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

from . import config as C
from .provenance import Provenance
from .schemas import (
    ProvenancedObservation, LabSample, RoutingInterval, TransitionEvent,
)

# ── Kinetic calibration ─────────────────────────────────────────────────────
# Anchor two grades to nominal (plausible) hydrogen ratios; solve (a, b) so both
# reproduce their configured targets, then derive every other grade's setpoint.
# ASSUMPTION: hydrogen-ratio axis is illustrative; only the target mapping matters.
_ANCHORS = {"A": 0.05, "B": 0.35}


def _calibrate_law() -> tuple[float, float]:
    (g1, h1), (g2, h2) = _ANCHORS.items()
    t1, t2 = C.get_grade(g1).target_mfi, C.get_grade(g2).target_mfi
    b = (math.log(t2) - math.log(t1)) / (h2 - h1)
    a = math.log(t1) - b * h1
    return a, b


_A, _B = _calibrate_law()


def instantaneous_mfi(h: float) -> float:
    """Instantaneous MFI produced at hydrogen-ratio setpoint h."""
    return math.exp(_A + _B * h)


def hydrogen_setpoint(grade_id: str) -> float:
    """Hydrogen ratio that yields a grade's configured target MFI exactly."""
    return (math.log(C.get_grade(grade_id).target_mfi) - _A) / _B


# ── Episode parameters ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class EpisodeParams:
    dt_min: float = 1.0                 # integration/sampling step
    tau_min: float = 150.0              # CSTR bed washout time constant
    transport_delay_min: float = 12.0   # analyzer transport/plug-flow delay
    pre_min: float = 60.0               # hold at grade_from before switch
    post_min: float = 900.0             # evolve after switch (>5·tau to settle)
    lab_interval_min: float = 60.0      # time between lab collections
    lab_latency_min: float = 90.0       # collected_at -> result_at gap
    rate_tph: float = 12.0              # production rate (tonnes/hour)
    analyzer_noise_frac: float = 0.02   # multiplicative analyzer noise (1-sigma)
    lab_noise_frac: float = 0.01        # multiplicative lab measurement noise
    bed_temp_c: float = 85.0            # context-only process signal
    bed_temp_noise_c: float = 0.5

    @property
    def total_min(self) -> float:
        return self.pre_min + self.post_min


def _seed_int(event_id: str, seed: int) -> int:
    """Stable per-event seed: identical (event_id, seed) -> identical stream."""
    h = hashlib.sha256(f"{event_id}:{seed}".encode()).hexdigest()
    return int(h[:8], 16)


# ── True-material trajectory (deterministic ODE) ────────────────────────────


def _bed_trajectory(grade_from: str, grade_to: str, p: EpisodeParams) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (t_min, h_setpoint, true_bed_mfi) on the dt grid. Deterministic:
    no randomness — the physics is exact; noise is added only to observations."""
    n = int(round(p.total_min / p.dt_min)) + 1
    t = np.arange(n, dtype=float) * p.dt_min
    h_from, h_to = hydrogen_setpoint(grade_from), hydrogen_setpoint(grade_to)
    h = np.where(t < p.pre_min, h_from, h_to)
    ln_inst = _A + _B * h
    ln_bed = np.empty(n, dtype=float)
    ln_bed[0] = math.log(C.get_grade(grade_from).target_mfi)  # steady at grade_from
    k = p.dt_min / p.tau_min
    for i in range(n - 1):
        ln_bed[i + 1] = ln_bed[i] + k * (ln_inst[i] - ln_bed[i])
    return t, h, np.exp(ln_bed)


def steady_state_mfi(grade_to: str, p: EpisodeParams | None = None) -> float:
    """Numerically evolved bed MFI at the end of the episode (for verification)."""
    p = p or EpisodeParams()
    _, _, bed = _bed_trajectory("A" if grade_to != "A" else "B", grade_to, p)
    return float(bed[-1])


# ── Episode assembly ────────────────────────────────────────────────────────


def generate_episode(event_id: str, grade_from: str, grade_to: str, seed: int,
                     start_time: datetime | None = None,
                     params: EpisodeParams | None = None) -> TransitionEvent:
    """Produce one immutable, SIMULATED TransitionEvent. Deterministic given
    (event_id, seed, params). Delegates all validation to the Phase-1 schemas."""
    p = params or EpisodeParams()
    start = start_time or datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    if start.tzinfo is None:
        raise ValueError("start_time must be timezone-aware (UTC)")
    rng = np.random.default_rng(_seed_int(event_id, seed))

    t, h, bed = _bed_trajectory(grade_from, grade_to, p)
    n = len(t)
    delay_steps = int(round(p.transport_delay_min / p.dt_min))
    spec_to = C.get_grade(grade_to)

    def ts(minute: float) -> datetime:
        return start + timedelta(minutes=float(minute))

    # Process series: hydrogen setpoint, delayed+noisy online MFI, bed temperature.
    series: list[ProvenancedObservation] = []
    online_mfi = np.empty(n, dtype=float)
    for i in range(n):
        src = bed[max(0, i - delay_steps)]                       # transport delay
        online_mfi[i] = src * (1.0 + p.analyzer_noise_frac * rng.standard_normal())
        series.append(ProvenancedObservation("H2_ratio", float(h[i]), "-", ts(t[i]), Provenance.SIMULATED))
        series.append(ProvenancedObservation("MFI_online", float(online_mfi[i]), "g/10min", ts(t[i]), Provenance.SIMULATED))
        bt = p.bed_temp_c + p.bed_temp_noise_c * rng.standard_normal()
        series.append(ProvenancedObservation("bed_temp", float(bt), "degC", ts(t[i]), Provenance.SIMULATED))

    # Lab samples: measure TRUE bed material at collection; result delayed.
    labs: list[LabSample] = []
    coll = 0.0
    k = 0
    while coll <= p.total_min:
        idx = min(n - 1, int(round(coll / p.dt_min)))
        measured = float(bed[idx] * (1.0 + p.lab_noise_frac * rng.standard_normal()))
        labs.append(LabSample(f"{event_id}-lab{k:03d}", grade_to, measured,
                              ts(coll), ts(coll + p.lab_latency_min), Provenance.SIMULATED))
        coll += p.lab_interval_min
        k += 1

    routing = _build_routing(online_mfi, t, spec_to, p, start)
    return TransitionEvent(event_id, grade_from, grade_to, start,
                           series=tuple(series), labs=tuple(labs),
                           routing=tuple(routing), provenance=Provenance.SIMULATED)


def _build_routing(online_mfi: np.ndarray, t: np.ndarray, spec_to, p: EpisodeParams,
                   start: datetime) -> list[RoutingInterval]:
    """Recorded HISTORICAL (SOP-style) routing: material is sent to DOWNGRADE
    until the online analyzer has read in-spec continuously for the grade dwell,
    then PRIME for the remainder. This is a data attribute of the episode, NOT a
    PrimePath decision. Intervals tile [0, total] exactly so routed mass equals
    produced mass (rate × duration)."""
    dwell_steps = int(round(spec_to.dwell_min / p.dt_min))
    in_spec = (online_mfi >= spec_to.mfi_low) & (online_mfi <= spec_to.mfi_high)
    prime_start_idx: int | None = None
    run = 0
    for i, ok in enumerate(in_spec):
        run = run + 1 if ok else 0
        if run >= dwell_steps:
            prime_start_idx = i
            break

    def ts(minute: float) -> datetime:
        return start + timedelta(minutes=float(minute))

    total = p.total_min
    if prime_start_idx is None:
        return [RoutingInterval(ts(0.0), ts(total), "DOWNGRADE", p.rate_tph)]
    switch = float(t[prime_start_idx])
    intervals = []
    if switch > 0:
        intervals.append(RoutingInterval(ts(0.0), ts(switch), "DOWNGRADE", p.rate_tph))
    intervals.append(RoutingInterval(ts(switch), ts(total), "PRIME", p.rate_tph))
    return intervals


def produced_mass_tonnes(p: EpisodeParams | None = None) -> float:
    p = p or EpisodeParams()
    return p.rate_tph * p.total_min / 60.0
