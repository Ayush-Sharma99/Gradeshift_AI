"""Ingestion — provenance tagging and UTC time normalization at the boundary.

Any series/sample entering the pipeline passes through here so that (a) every
record is provenance-labelled and (b) every timestamp is timezone-aware UTC.
Naive timestamps are rejected unless an explicit assume_tz is supplied — we never
silently guess a timezone.
"""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from typing import Iterable, Sequence

from .provenance import Provenance
from .schemas import ProvenancedObservation, LabSample


def to_utc(ts: datetime, assume_tz: tzinfo | None = None) -> datetime:
    """Normalize a datetime to UTC. Naive input is rejected unless assume_tz is
    given (then it is interpreted in that zone, never silently assumed UTC)."""
    if not isinstance(ts, datetime):
        raise ValueError(f"expected datetime, got {type(ts).__name__}")
    if ts.tzinfo is None:
        if assume_tz is None:
            raise ValueError("naive timestamp rejected; pass assume_tz to localize it")
        ts = ts.replace(tzinfo=assume_tz)
    return ts.astimezone(timezone.utc)


def tag_observation(tag: str, value: float, unit: str, ts: datetime,
                    provenance: Provenance = Provenance.SIMULATED,
                    assume_tz: tzinfo | None = None) -> ProvenancedObservation:
    """Build a provenance-tagged, UTC-normalized observation."""
    return ProvenancedObservation(tag, value, unit, to_utc(ts, assume_tz), provenance)


def tag_series(tag: str, unit: str, points: Iterable[tuple[datetime, float]],
               provenance: Provenance = Provenance.SIMULATED,
               assume_tz: tzinfo | None = None) -> tuple[ProvenancedObservation, ...]:
    """Tag a (timestamp, value) stream into provenanced observations."""
    return tuple(tag_observation(tag, v, unit, ts, provenance, assume_tz) for ts, v in points)


def normalize_lab(sample: LabSample, assume_tz: tzinfo | None = None) -> LabSample:
    """Return a copy of a lab sample with both timestamps normalized to UTC."""
    return LabSample(sample.sample_id, sample.grade_id, sample.mfi,
                     to_utc(sample.collected_at, assume_tz),
                     to_utc(sample.result_at, assume_tz), sample.provenance)


def summarize_provenance(obs: Sequence[ProvenancedObservation]) -> dict[str, int]:
    """Count observations by provenance label (for display/audit)."""
    counts: dict[str, int] = {}
    for o in obs:
        counts[o.provenance.value] = counts.get(o.provenance.value, 0) + 1
    return counts
