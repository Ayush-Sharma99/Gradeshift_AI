"""Event-level partition helpers (TRAIN / CALIBRATION / LOCKED_TEST).

Whole-event, chronological splitting only. A TransitionEvent belongs ENTIRELY to
one partition — there is no row-level or random splitting API, by design, so a
single transition can never be split across partitions. This prepares the
interfaces the Phase-5+ estimator and Phase-6 calibrator will consume; no model
is trained here.
"""
from __future__ import annotations

from enum import Enum
from typing import Iterable, Sequence

from .schemas import TransitionEvent


class Partition(str, Enum):
    TRAIN = "TRAIN"
    CALIBRATION = "CALIBRATION"
    LOCKED_TEST = "LOCKED_TEST"


def chronological_split(events: Sequence[TransitionEvent],
                        frac_train: float = 0.6,
                        frac_calibration: float = 0.2) -> dict[str, Partition]:
    """Assign each event to exactly one partition by chronological order of
    `started_at` (earliest -> TRAIN, middle -> CALIBRATION, newest -> LOCKED_TEST).
    Returns {event_id: Partition}. Ties broken by event_id for determinism."""
    if frac_train <= 0 or frac_calibration <= 0 or frac_train + frac_calibration >= 1.0:
        raise ValueError("fractions must be positive and leave a non-empty LOCKED_TEST")
    ids = [e.event_id for e in events]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate event_id in partition input")

    ordered = sorted(events, key=lambda e: (e.started_at, e.event_id))
    n = len(ordered)
    n_train = int(n * frac_train)
    n_cal = int(n * frac_calibration)
    # guarantee each non-empty when n allows
    n_train = max(1, n_train) if n >= 3 else n_train
    n_cal = max(1, n_cal) if n >= 3 else n_cal
    assignment: dict[str, Partition] = {}
    for i, e in enumerate(ordered):
        if i < n_train:
            assignment[e.event_id] = Partition.TRAIN
        elif i < n_train + n_cal:
            assignment[e.event_id] = Partition.CALIBRATION
        else:
            assignment[e.event_id] = Partition.LOCKED_TEST
    return assignment


def partition_members(assignment: dict[str, Partition], part: Partition) -> list[str]:
    return [eid for eid, p in assignment.items() if p == part]


def assert_whole_event_partitions(assignment: dict[str, Partition],
                                  events: Iterable[TransitionEvent]) -> None:
    """Guard: every event has exactly one partition and none is unassigned.
    Raises AssertionError (loudly) on any violation — used by leakage tests."""
    for e in events:
        if e.event_id not in assignment:
            raise AssertionError(f"event {e.event_id} not assigned to any partition")
    # By construction each event_id maps to a single Partition value; verify no
    # event_id was duplicated into conflicting partitions upstream.
    seen: dict[str, Partition] = {}
    for eid, p in assignment.items():
        if eid in seen and seen[eid] != p:
            raise AssertionError(f"event {eid} assigned to multiple partitions")
        seen[eid] = p
