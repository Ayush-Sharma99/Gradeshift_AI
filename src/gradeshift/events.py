"""Canonical TransitionEvent builder + deterministic transition-boundary rules.

The builder turns Phase-2 generated (or ingested) data into the canonical
immutable TransitionEvent, stamping unit, end time, intervention records, and
source/model/config versions. Boundary detection is deterministic and derived
only from observed signals — never from the generator's internal parameters.

ALL boundary rules here are SIMULATION ASSUMPTIONS, labelled as such. They are
not plant-certified operating procedures.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from . import config as C
from .provenance import Provenance
from .schemas import (
    ProvenancedObservation, LabSample, RoutingInterval, Intervention, TransitionEvent,
)

# Marks every rule in this module as a declared simulation assumption.
BOUNDARY_RULES_PROVENANCE = Provenance.ASSUMPTION
BOUNDARY_RULES_VERSION = "boundary-rules-v1"


@dataclass(frozen=True)
class TransitionBoundaries:
    """Deterministic time partition of an episode (SIMULATION ASSUMPTION rules):
      pre-baseline      [started_at, transition_start)
      active transition [transition_start, transition_end)
      post stabilization[transition_end, ended_at]
    transition_end is None if the online signal never stabilizes in grade_to spec.
    """
    event_id: str
    started_at: datetime
    transition_start: datetime
    transition_end: Optional[datetime]
    ended_at: datetime
    rule_version: str = BOUNDARY_RULES_VERSION
    provenance: Provenance = BOUNDARY_RULES_PROVENANCE

    def phase_at(self, t: datetime) -> str:
        if t < self.transition_start:
            return "PRE_BASELINE"
        if self.transition_end is None or t < self.transition_end:
            return "ACTIVE_TRANSITION"
        return "POST_STABILIZATION"

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "started_at": self.started_at.isoformat(),
                "transition_start": self.transition_start.isoformat(),
                "transition_end": self.transition_end.isoformat() if self.transition_end else None,
                "ended_at": self.ended_at.isoformat(), "rule_version": self.rule_version,
                "provenance": self.provenance.value}


def _series_tag(event: TransitionEvent, tag: str) -> list[ProvenancedObservation]:
    return sorted((o for o in event.series if o.tag == tag), key=lambda o: o.timestamp)


def compute_boundaries(event: TransitionEvent) -> TransitionBoundaries:
    """Detect boundaries from observed signals only (deterministic).

    transition_start := first time the H2_ratio setpoint departs from its initial
      value (the commanded grade switch).
    transition_end   := first time the online MFI has stayed continuously inside
      the grade_to spec band for the grade's configured dwell.
    """
    h2 = _series_tag(event, "H2_ratio")
    mfi = _series_tag(event, "MFI_online")
    if not h2 or not mfi:
        raise ValueError("event lacks H2_ratio/MFI_online series required for boundaries")

    started = event.started_at
    ended = event.ended_at or max(o.timestamp for o in event.series)

    # transition_start: first setpoint change
    h0 = h2[0].value
    transition_start = started
    for o in h2:
        if abs(o.value - h0) > 1e-9:
            transition_start = o.timestamp
            break

    # transition_end: dwell-satisfied in grade_to spec on the online signal
    spec = C.get_grade(event.grade_to)
    dwell = spec.dwell_min
    transition_end: Optional[datetime] = None
    run_start: Optional[datetime] = None
    for o in mfi:
        if spec.in_spec(o.value):
            run_start = run_start or o.timestamp
            if (o.timestamp - run_start).total_seconds() / 60.0 >= dwell:
                transition_end = o.timestamp
                break
        else:
            run_start = None

    return TransitionBoundaries(event.event_id, started, transition_start, transition_end, ended)


def build_event(raw: TransitionEvent, *, unit: str = "SIM-UNIT-1",
                interventions: tuple[Intervention, ...] = (),
                versions: Optional[dict[str, str]] = None) -> TransitionEvent:
    """Assemble the canonical immutable TransitionEvent from Phase-2 data,
    stamping unit, computed end time, interventions, and artifact versions.
    All source records (series/labs/routing/provenance) are preserved verbatim."""
    ended = raw.ended_at or (max(o.timestamp for o in raw.series) if raw.series else raw.started_at)
    vers = {
        "data": raw.versions.get("data", "sim-gen-v1"),
        "boundary_rules": BOUNDARY_RULES_VERSION,
        "config_grades": "spec-v1",
        "config_policy": C.POLICY.version,
    }
    if versions:
        vers.update(versions)
    return TransitionEvent(
        event_id=raw.event_id, grade_from=raw.grade_from, grade_to=raw.grade_to,
        started_at=raw.started_at, series=raw.series, labs=raw.labs, routing=raw.routing,
        interventions=tuple(sorted(interventions, key=lambda iv: iv.timestamp)),
        ended_at=ended, unit=unit, versions=vers, provenance=raw.provenance,
    )
