"""Phase 7 — deterministic SENSOR-FAULT injection fixtures.

Each function returns a NEW TransitionEvent with a specific, reproducible fault
applied to one signal's series. They are pure (no randomness) so the downstream
health/assurance result is deterministic and explainable. These injectors
operate on the *data*, never on the generator's physics — they do not change
how the simulator produces truth, only how the sensor stream is corrupted.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Optional

from .schemas import ProvenancedObservation, TransitionEvent


def _series_for(event: TransitionEvent, tag: str):
    return [o for o in event.series if o.tag == tag]


def _rebuild(event: TransitionEvent, tag: str, new_obs) -> TransitionEvent:
    """Replace all `tag` observations with `new_obs`, keep every other signal."""
    others = [o for o in event.series if o.tag != tag]
    return replace(event, series=tuple(others + list(new_obs)))


def drop_signal(event: TransitionEvent, tag: str) -> TransitionEvent:
    """Fault A — a required signal is entirely MISSING."""
    return _rebuild(event, tag, [])


def freeze_signal(event: TransitionEvent, tag: str, start: datetime, end: datetime,
                  value: Optional[float] = None) -> TransitionEvent:
    """Fault B — the sensor FREEZES at a constant value over [start, end]."""
    obs = _series_for(event, tag)
    if value is None:
        before = [o.value for o in obs if o.timestamp < start]
        inwin = [o.value for o in obs if start <= o.timestamp <= end]
        value = before[-1] if before else (inwin[0] if inwin else 0.0)
    new = [replace(o, value=float(value)) if start <= o.timestamp <= end else o
           for o in obs]
    return _rebuild(event, tag, new)


def bias_signal(event: TransitionEvent, tag: str, start: datetime, end: datetime,
                delta: float) -> TransitionEvent:
    """Fault C — a constant additive BIAS over [start, end]."""
    new = [replace(o, value=float(o.value + delta)) if start <= o.timestamp <= end else o
           for o in _series_for(event, tag)]
    return _rebuild(event, tag, new)


def spike_signal(event: TransitionEvent, tag: str, at: datetime,
                 multiplier: float = 3.0) -> TransitionEvent:
    """Fault D — a single-sample SPIKE/outlier nearest to `at`."""
    obs = _series_for(event, tag)
    if not obs:
        return event
    idx = min(range(len(obs)), key=lambda i: abs((obs[i].timestamp - at).total_seconds()))
    new = list(obs)
    new[idx] = replace(obs[idx], value=float(obs[idx].value * multiplier))
    return _rebuild(event, tag, new)


def gap_signal(event: TransitionEvent, tag: str, start: datetime,
               end: datetime) -> TransitionEvent:
    """Fault E — a TIMESTAMP GAP: observations removed within (start, end)."""
    new = [o for o in _series_for(event, tag) if not (start < o.timestamp < end)]
    return _rebuild(event, tag, new)


def disorder_signal(event: TransitionEvent, tag: str,
                    at: Optional[datetime] = None) -> TransitionEvent:
    """Fault F — TIMESTAMP DISORDER: two adjacent samples swapped in arrival
    order so acquisition timestamps are no longer monotonically increasing.

    `at` chooses WHERE the swap lands so the disordered pair falls inside the
    as-of window of a later decision time t (otherwise an as-of slice at t would
    simply exclude the swap and never see the fault). Defaults to the series
    midpoint when no target time is given."""
    obs = _series_for(event, tag)
    if len(obs) < 3:
        return event
    if at is None:
        idx = len(obs) // 2
    else:
        # swap the adjacent pair straddling `at`; clamp so idx+1 stays in range
        idx = min(range(len(obs) - 1),
                  key=lambda i: abs((obs[i].timestamp - at).total_seconds()))
    idx = max(0, min(idx, len(obs) - 2))
    new = list(obs)
    new[idx], new[idx + 1] = new[idx + 1], new[idx]
    return _rebuild(event, tag, new)


def stale_signal(event: TransitionEvent, tag: str, since: datetime) -> TransitionEvent:
    """Fault G — STALE value: no fresh observations after `since` (sensor stuck
    in the past relative to a later decision time t)."""
    new = [o for o in _series_for(event, tag) if o.timestamp <= since]
    return _rebuild(event, tag, new)


def multi_fault(event: TransitionEvent, faults) -> TransitionEvent:
    """Fault H — compose several injectors (each a callable event -> event)."""
    for fn in faults:
        event = fn(event)
    return event
