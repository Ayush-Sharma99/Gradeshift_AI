"""As-of information-availability layer — the leakage firewall.

`as_of(event, t)` returns a DecisionContext/AsOfSnapshot containing ONLY what was
legitimately knowable at decision time t:

  * process observations with source timestamp <= t
  * lab RESULTS only if result_at <= t  (value exposed)
  * lab samples collected (collected_at <= t) but not yet resulted (result_at > t)
    appear as PENDING — the sample's existence is known, its MFI is NOT. The
    pending object has no field capable of carrying the result, so a future lab
    value cannot leak structurally.
  * routing intervals that have started (start <= t); an interval straddling t is
    clipped to t and flagged ongoing, so the FUTURE switch time is never revealed
  * interventions with timestamp <= t

The eventual transition OUTCOME is never part of a decision context — it belongs
to post-hoc reconciliation. Reactor-state time (observations) and commercial-
material time (routing) are kept as distinct fields; this layer does not map one
to the other (that is the Phase-8 material engine).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .provenance import Provenance
from .schemas import ProvenancedObservation, LabSample, Intervention, TransitionEvent


def _require_utc(t: datetime) -> datetime:
    if not isinstance(t, datetime) or t.tzinfo is None:
        raise ValueError("as-of time t must be timezone-aware (UTC)")
    return t.astimezone(timezone.utc)


@dataclass(frozen=True)
class PendingLab:
    """A collected-but-unresulted sample. Deliberately has NO mfi field."""
    sample_id: str
    grade_id: str
    collected_at: datetime
    provenance: Provenance = Provenance.SIMULATED

    def to_dict(self) -> dict[str, Any]:
        return {"sample_id": self.sample_id, "grade_id": self.grade_id,
                "collected_at": self.collected_at.isoformat(), "provenance": self.provenance.value}


@dataclass(frozen=True)
class VisibleRouting:
    """A routing interval as known at t, clipped so no future switch leaks."""
    start: datetime
    end_as_of: datetime
    destination: str
    rate_tph: float
    ongoing: bool

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.isoformat(), "end_as_of": self.end_as_of.isoformat(),
                "destination": self.destination, "rate_tph": self.rate_tph, "ongoing": self.ongoing}


@dataclass(frozen=True)
class AsOfSnapshot:
    """Deterministic, serializable view of an event as known at decision time t.
    Also aliased as DecisionContext."""
    event_id: str
    unit: str
    grade_from: str
    grade_to: str
    as_of: datetime
    observations: tuple[ProvenancedObservation, ...]
    lab_results: tuple[LabSample, ...]           # result_at <= t
    pending_labs: tuple[PendingLab, ...]         # collected <= t < result_at
    routing_visible: tuple[VisibleRouting, ...]
    interventions: tuple[Intervention, ...]
    versions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "unit": self.unit, "grade_from": self.grade_from,
                "grade_to": self.grade_to, "as_of": self.as_of.isoformat(),
                "observations": [o.to_dict() for o in self.observations],
                "lab_results": [s.to_dict() for s in self.lab_results],
                "pending_labs": [p.to_dict() for p in self.pending_labs],
                "routing_visible": [r.to_dict() for r in self.routing_visible],
                "interventions": [iv.to_dict() for iv in self.interventions],
                "versions": dict(self.versions)}

    def lineage(self) -> list[dict[str, Any]]:
        """Per-value provenance lineage for audit: source event, original
        timestamp, provenance label, and the as-of transformation applied."""
        rows: list[dict[str, Any]] = []
        for o in self.observations:
            rows.append({"source_event": self.event_id, "kind": "observation", "ref": o.tag,
                         "original_timestamp": o.timestamp.isoformat(),
                         "provenance": o.provenance.value, "transform": f"as_of<={self.as_of.isoformat()}"})
        for s in self.lab_results:
            rows.append({"source_event": self.event_id, "kind": "lab_result", "ref": s.sample_id,
                         "original_timestamp": s.result_at.isoformat(),
                         "provenance": s.provenance.value, "transform": "result_at<=t (value visible)"})
        for p in self.pending_labs:
            rows.append({"source_event": self.event_id, "kind": "lab_pending", "ref": p.sample_id,
                         "original_timestamp": p.collected_at.isoformat(),
                         "provenance": p.provenance.value, "transform": "collected<=t<result_at (value hidden)"})
        for r in self.routing_visible:
            rows.append({"source_event": self.event_id, "kind": "routing", "ref": r.destination,
                         "original_timestamp": r.start.isoformat(), "provenance": Provenance.SIMULATED.value,
                         "transform": f"clipped end<={self.as_of.isoformat()}" if r.ongoing else "complete"})
        return rows


# DecisionContext is a semantic alias for the same immutable snapshot.
DecisionContext = AsOfSnapshot


def as_of(event: TransitionEvent, t: datetime,
          versions: Optional[dict[str, str]] = None) -> AsOfSnapshot:
    """Build the leakage-safe decision context for `event` at time `t`.
    Deterministic: identical (event, t) -> identical snapshot."""
    t = _require_utc(t)

    observations = tuple(sorted((o for o in event.series if o.timestamp <= t),
                                key=lambda o: (o.timestamp, o.tag)))

    results, pending = [], []
    for s in sorted(event.labs, key=lambda s: s.collected_at):
        if s.result_at <= t:
            results.append(s)                                   # value legitimately available
        elif s.collected_at <= t:
            pending.append(PendingLab(s.sample_id, s.grade_id, s.collected_at, s.provenance))
        # else: not yet collected -> entirely invisible

    routing_visible = []
    for r in sorted(event.routing, key=lambda r: r.start):
        if r.start <= t:
            routing_visible.append(VisibleRouting(
                start=r.start, end_as_of=min(r.end, t), destination=r.destination,
                rate_tph=r.rate_tph, ongoing=r.end > t))
        # routing that has not started yet -> invisible (no future switch leak)

    interventions = tuple(sorted((iv for iv in event.interventions if iv.timestamp <= t),
                                 key=lambda iv: iv.timestamp))

    return AsOfSnapshot(
        event_id=event.event_id, unit=event.unit, grade_from=event.grade_from,
        grade_to=event.grade_to, as_of=t, observations=observations,
        lab_results=tuple(results), pending_labs=tuple(pending),
        routing_visible=tuple(routing_visible), interventions=interventions,
        versions=dict(versions or event.versions))
