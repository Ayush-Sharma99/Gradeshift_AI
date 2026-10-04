"""Phase 2 tests — ingestion provenance tagging and UTC normalization."""
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import ingestion as I
from gradeshift.provenance import Provenance

IST = timezone(timedelta(hours=5, minutes=30))


def test_naive_timestamp_rejected_without_assume_tz():
    with pytest.raises(ValueError):
        I.to_utc(datetime(2026, 1, 1, 12, 0))


def test_naive_timestamp_localized_with_assume_tz():
    out = I.to_utc(datetime(2026, 1, 1, 12, 0), assume_tz=IST)
    assert out.tzinfo == timezone.utc
    assert out.hour == 6 and out.minute == 30  # 12:00 IST -> 06:30 UTC


def test_aware_timestamp_converted_to_utc():
    out = I.to_utc(datetime(2026, 1, 1, 12, 0, tzinfo=IST))
    assert out.utcoffset() == timedelta(0)


def test_tag_observation_sets_provenance_and_utc():
    o = I.tag_observation("MFI_online", 7.9, "g/10min",
                          datetime(2026, 1, 1, 0, 0, tzinfo=IST), Provenance.SIMULATED)
    assert o.provenance is Provenance.SIMULATED
    assert o.timestamp.tzinfo == timezone.utc


def test_summarize_provenance_counts():
    pts = [(datetime(2026, 1, 1, 0, i, tzinfo=timezone.utc), float(i)) for i in range(3)]
    obs = I.tag_series("x", "-", pts, Provenance.ILLUSTRATIVE)
    assert I.summarize_provenance(obs) == {"ILLUSTRATIVE": 3}
