"""Phase 7A tests — deterministic SENSOR / DATA HEALTH layer.

Covers tests A–G and the sensor-fault fixtures A–H of the Phase 7 objective:
fresh/stale/missing/frozen (incl. a genuinely stable-but-noisy signal NOT
falsely flagged)/range/spike/timestamp-disorder/time-gap/multi-fault, plus the
ADVERSARIAL as-of causality (no-future) invariance. Health is logically
separate from applicability (Phase 7B) and prediction uncertainty (Phase 6).
"""
from datetime import datetime, timedelta, timezone

import pytest

from gradeshift import simulate as S
from gradeshift import faults as F
from gradeshift.health import (
    HealthState, HealthThresholds, DEFAULT_THRESHOLDS, assess_sensor_health,
    worst_state, R_MISSING, R_MALFORMED, R_STALE, R_GAP, R_FROZEN,
    R_RANGE_LOW, R_RANGE_HIGH, R_SPIKE, R_DISORDER, R_DUPLICATE, R_OK,
    HEALTH_RULES_VERSION,
)

BASE = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


def _mins(n: float) -> datetime:
    return BASE + timedelta(minutes=n)


def _episode(eid="EP-H", gf="A", gt="B", seed=5):
    return S.generate_episode(eid, gf, gt, seed=seed, start_time=BASE)


# ── worst_state helper ───────────────────────────────────────────────────

def test_worst_state_ranking_and_empty():
    assert worst_state([]) is HealthState.NORMAL
    assert worst_state([HealthState.NORMAL, HealthState.DEGRADED]) is HealthState.DEGRADED
    assert worst_state([HealthState.DEGRADED, HealthState.UNAVAILABLE,
                        HealthState.ABNORMAL]) is HealthState.UNAVAILABLE


# ── A. fresh signal is NORMAL ────────────────────────────────────────────

def test_A_fresh_signal_normal():
    ev = _episode()
    hr = assess_sensor_health(ev, _mins(400))
    assert hr.overall_state is HealthState.NORMAL
    assert hr.required_available is True
    assert not hr.is_blocking
    assert hr.reason_codes() == []
    assert hr.rule_version == HEALTH_RULES_VERSION


# ── B. stale signal is DEGRADED then ABNORMAL (never silently healthy) ───

def test_B_stale_degraded_then_abnormal():
    ev = _episode()
    # latest obs at t-12 (>max_age 10, <max_stale 20) -> DEGRADED
    stale = F.stale_signal(ev, "MFI_online", since=_mins(400 - 12))
    hr = assess_sensor_health(stale, _mins(400))
    assert hr.overall_state is HealthState.DEGRADED
    assert R_STALE in hr.reason_codes()
    # latest obs at t-30 (>max_stale 20) -> ABNORMAL
    stale2 = F.stale_signal(ev, "MFI_online", since=_mins(400 - 30))
    hr2 = assess_sensor_health(stale2, _mins(400))
    assert hr2.overall_state is HealthState.ABNORMAL
    assert hr2.is_blocking
    assert R_STALE in hr2.reason_codes()


# ── C. missing REQUIRED signal is UNAVAILABLE (ABSTAIN-path) ─────────────

def test_C_missing_required_unavailable():
    ev = _episode()
    missing = F.drop_signal(ev, "MFI_online")
    hr = assess_sensor_health(missing, _mins(400))
    assert hr.overall_state is HealthState.UNAVAILABLE
    assert hr.required_available is False
    assert hr.is_blocking
    assert R_MISSING in hr.reason_codes()


def test_C_missing_nonrequired_only_degrades():
    ev = _episode()
    # bed_temp is monitored but NOT required -> capped at DEGRADED, not blocking
    missing = F.drop_signal(ev, "bed_temp")
    hr = assess_sensor_health(missing, _mins(400))
    assert hr.required_available is True
    assert hr.overall_state is HealthState.DEGRADED
    assert not hr.is_blocking


# ── D. frozen MEASURED signal flagged; stable-noisy NOT falsely flagged ──

def test_D_frozen_measured_abnormal():
    ev = _episode()
    frozen = F.freeze_signal(ev, "MFI_online", _mins(400 - 20), _mins(400))
    hr = assess_sensor_health(frozen, _mins(400))
    assert hr.overall_state is HealthState.ABNORMAL
    assert R_FROZEN in hr.reason_codes()


def test_D_noisy_signal_not_frozen():
    ev = _episode()
    hr = assess_sensor_health(ev, _mins(400))
    assert R_FROZEN not in hr.reason_codes()


def test_D_setpoint_not_flagged_frozen_or_spike():
    # H2_ratio is a piecewise-constant SETPOINT: a flat run is expected, never
    # a frozen/spike fault. It is excluded from variation_expected_signals.
    ev = _episode()
    hr = assess_sensor_health(ev, _mins(400))
    h2_codes = [f.reason_code for f in hr.findings if f.signal == "H2_ratio"]
    assert R_FROZEN not in h2_codes
    assert R_SPIKE not in h2_codes


# ── E. engineering-range violation ───────────────────────────────────────

def test_E_range_high_abnormal():
    ev = _episode()
    # bias far above the MFI plausibility band (hi=100) -> RANGE_HIGH
    biased = F.bias_signal(ev, "MFI_online", _mins(0), _mins(400), 500.0)
    hr = assess_sensor_health(biased, _mins(400))
    assert hr.overall_state is HealthState.ABNORMAL
    assert R_RANGE_HIGH in hr.reason_codes()


def test_E_range_low_abnormal():
    ev = _episode()
    biased = F.bias_signal(ev, "MFI_online", _mins(0), _mins(400), -1000.0)
    hr = assess_sensor_health(biased, _mins(400))
    assert hr.overall_state is HealthState.ABNORMAL
    assert R_RANGE_LOW in hr.reason_codes()


# ── F. rate-of-change spike ──────────────────────────────────────────────

def test_F_spike_abnormal():
    ev = _episode()
    spiked = F.spike_signal(ev, "MFI_online", _mins(300), multiplier=5.0)
    hr = assess_sensor_health(spiked, _mins(400))
    assert hr.overall_state is HealthState.ABNORMAL
    assert R_SPIKE in hr.reason_codes()


# ── G. timestamp disorder / duplicate / gap ──────────────────────────────

def test_G_disorder_abnormal():
    ev = _episode()
    # disorder must land inside the as-of window of t to be visible
    dis = F.disorder_signal(ev, "MFI_online", at=_mins(300))
    hr = assess_sensor_health(dis, _mins(400))
    assert hr.overall_state is HealthState.ABNORMAL
    assert R_DISORDER in hr.reason_codes()


def test_G_disorder_after_t_not_visible():
    # a swap AFTER the decision time must NOT affect the as-of result
    ev = _episode()
    dis = F.disorder_signal(ev, "MFI_online", at=_mins(500))
    hr = assess_sensor_health(dis, _mins(400))
    assert R_DISORDER not in hr.reason_codes()


def test_G_time_gap_degraded():
    ev = _episode()
    gap = F.gap_signal(ev, "MFI_online", _mins(300), _mins(340))
    hr = assess_sensor_health(gap, _mins(400))
    assert R_GAP in hr.reason_codes()
    assert hr.overall_state is HealthState.DEGRADED


# ── malformed (non-finite) value ─────────────────────────────────────────

def test_malformed_value_abnormal():
    from dataclasses import replace
    ev = _episode()
    obs = [o for o in ev.series if o.tag == "MFI_online"]
    tgt = next(o for o in obs if o.timestamp == _mins(300))
    others = [o for o in ev.series if o is not tgt]
    bad = replace(ev, series=tuple(others + [replace(tgt, value=float("nan"))]))
    hr = assess_sensor_health(bad, _mins(400))
    assert hr.overall_state is HealthState.ABNORMAL
    assert R_MALFORMED in hr.reason_codes()


# ── H. multiple simultaneous faults ──────────────────────────────────────

def test_H_multi_fault_abnormal():
    ev = _episode()
    multi = F.multi_fault(ev, [
        lambda e: F.freeze_signal(e, "MFI_online", _mins(380), _mins(400)),
        lambda e: F.spike_signal(e, "bed_temp", _mins(300), 4.0),
    ])
    hr = assess_sensor_health(multi, _mins(400))
    assert hr.overall_state is HealthState.ABNORMAL
    assert R_FROZEN in hr.reason_codes()


# ── ADVERSARIAL: as-of causality (future data cannot change earlier t) ───

def test_future_invariance_health():
    ev = _episode()
    t = _mins(400)
    base = assess_sensor_health(ev, t)
    # inject a severe fault entirely AFTER t; the result at t must not change
    future_fault = F.freeze_signal(ev, "MFI_online", _mins(500), _mins(600))
    after = assess_sensor_health(future_fault, t)
    assert after.overall_state is base.overall_state
    assert after.reason_codes() == base.reason_codes()


# ── deterministic replay ─────────────────────────────────────────────────

def test_deterministic_replay():
    ev = _episode()
    t = _mins(400)
    a = assess_sensor_health(ev, t).to_dict()
    b = assess_sensor_health(ev, t).to_dict()
    assert a == b
