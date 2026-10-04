"""Phase 1 tests — config as single source of truth."""
import pytest

from gradeshift import config as C
from gradeshift.provenance import Provenance


def test_grades_present_and_consistent():
    for gid in ("A", "B", "C"):
        g = C.get_grade(gid)
        assert g.grade_id == gid
        assert g.mfi_low < g.target_mfi < g.mfi_high
        assert g.in_spec(g.target_mfi)
        assert not g.in_spec(g.mfi_high * 1.01)
        assert not g.in_spec(g.mfi_low * 0.99)


def test_canonical_direction_is_a_to_b():
    assert C.CANONICAL_GRADE_FROM == "A"
    assert C.CANONICAL_GRADE_TO == "B"
    assert C.CANONICAL_GRADE_FROM != C.CANONICAL_GRADE_TO


def test_unknown_grade_raises():
    with pytest.raises(KeyError):
        C.get_grade("Z")


def test_scenarios_ordered_and_tagged():
    low, base, high = (C.get_scenario(n) for n in ("LOW", "BASE", "HIGH"))
    # Spread and consequence should widen from LOW to HIGH.
    assert low.downgrade_spread < base.downgrade_spread < high.downgrade_spread
    assert low.false_prime_consequence < high.false_prime_consequence
    for s in (low, base, high):
        assert s.provenance is Provenance.ASSUMPTION
        assert s.prime_price > s.downgrade_price > 0


def test_unknown_scenario_raises():
    with pytest.raises(KeyError):
        C.get_scenario("MEDIUM")


def test_policy_thresholds_sane():
    p = C.POLICY
    assert 0.0 < p.nominal_coverage < 1.0
    assert 0.0 <= p.max_bad_prob_for_candidate < 0.5
    assert p.recommendation_expiry_min > 0
    assert p.required_approver
