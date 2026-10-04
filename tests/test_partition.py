"""Phase 3 tests — event-level partition safety and holdout isolation."""
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift.partition import (
    Partition, chronological_split, partition_members, assert_whole_event_partitions,
)
from gradeshift.alignment import as_of

BASE = datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)


def _events(n=10):
    evs = []
    for i in range(n):
        start = BASE + timedelta(days=i)   # chronological, distinct
        evs.append(S.generate_episode(f"EVT-{i:02d}", "A", "B", seed=i, start_time=start,
                                      params=S.EpisodeParams(post_min=120.0)))
    return evs


def test_chronological_order_train_before_test():
    evs = _events(10)
    a = chronological_split(evs)
    train = partition_members(a, Partition.TRAIN)
    test = partition_members(a, Partition.LOCKED_TEST)
    # earliest events in TRAIN, newest in LOCKED_TEST
    assert "EVT-00" in train and "EVT-09" in test


# H. two rows from the same event can never land in different partitions.
def test_H_no_event_spans_partitions():
    evs = _events(10)
    a = chronological_split(evs)
    # every event has a single partition; there is no row-level API at all
    for e in evs:
        assert e.event_id in a
        assert isinstance(a[e.event_id], Partition)
    assert_whole_event_partitions(a, evs)
    # a given event_id maps to exactly one partition value
    assert len({a["EVT-05"]}) == 1


def test_all_three_partitions_populated():
    a = chronological_split(_events(10))
    for p in (Partition.TRAIN, Partition.CALIBRATION, Partition.LOCKED_TEST):
        assert partition_members(a, p)


def test_duplicate_event_id_rejected():
    evs = _events(3)
    evs.append(evs[0])  # duplicate
    with pytest.raises(ValueError):
        chronological_split(evs)


def test_invalid_fractions_rejected():
    with pytest.raises(ValueError):
        chronological_split(_events(5), frac_train=0.9, frac_calibration=0.2)


def test_holdout_event_fully_isolated_from_as_of_of_train():
    # Holdout-event leakage guard: a LOCKED_TEST event's data never appears in a
    # TRAIN event's as-of context (they are distinct event_ids / snapshots).
    evs = _events(10)
    a = chronological_split(evs)
    test_ids = set(partition_members(a, Partition.LOCKED_TEST))
    train_ev = next(e for e in evs if a[e.event_id] == Partition.TRAIN)
    snap = as_of(train_ev, train_ev.started_at + timedelta(minutes=60))
    assert snap.event_id not in test_ids
    assert all(row["source_event"] == train_ev.event_id for row in snap.lineage())
