"""Deterministic, as-of-safe feature pipeline (Phase 5).

Every feature is built from an `AsOfSnapshot` (and the as-of-safe MaterialWindow),
so by construction NO value after decision time t can enter the vector — the
snapshot has already filtered future observations, unresulted labs, future
routing switches and future interventions. The adversarial no-future tests prove
this invariance.

Each feature carries explicit provenance (name, source, timestamp semantics,
transformation, lookback horizon, units) and a schema version. Missing evidence
is encoded as NaN (the primary estimator is a histogram GBM that handles NaN
natively) — never silently imputed with a future value.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from . import config as C
from .alignment import AsOfSnapshot, as_of
from .material_identity import MaterialMapParams, map_material
from .schemas import TransitionEvent

FEATURE_SCHEMA_VERSION = "feat-v1"

# H2 setpoint deviation (fraction) that marks the visible start of a transition.
_H2_CHANGE_FRAC = 0.05
PROCESS_TAGS = ("MFI_online", "H2_ratio", "bed_temp")
_TAG_UNITS = {"MFI_online": "g/10min", "H2_ratio": "-", "bed_temp": "degC"}


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    source: str              # which raw signal / object it derives from
    timestamp_semantics: str # how it relates to decision time t
    transformation: str      # the computation applied
    lookback_min: float      # horizon of history consumed (0 = point-in-time)
    units: str
    version: str = FEATURE_SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {"name": self.name, "source": self.source,
                "timestamp_semantics": self.timestamp_semantics,
                "transformation": self.transformation, "lookback_min": self.lookback_min,
                "units": self.units, "version": self.version}


_ROLL_WINDOWS = (30.0, 60.0)
_LAG_MIN = 30.0
_SLOPE_MIN = 60.0
NAN = float("nan")


def _build_specs() -> list[FeatureSpec]:
    specs: list[FeatureSpec] = []
    for tag in PROCESS_TAGS:
        u = _TAG_UNITS[tag]
        specs.append(FeatureSpec(f"{tag}_last", f"series[{tag}]", "latest obs ts<=t",
                                 "last value", 0.0, u))
        specs.append(FeatureSpec(f"{tag}_lag_{int(_LAG_MIN)}", f"series[{tag}]",
                                 f"obs ts<=t-{int(_LAG_MIN)}m", "value ~lag ago", _LAG_MIN, u))
        for w in _ROLL_WINDOWS:
            specs.append(FeatureSpec(f"{tag}_mean_{int(w)}", f"series[{tag}]",
                                     f"obs in [t-{int(w)}m, t]", "rolling mean", w, u))
            specs.append(FeatureSpec(f"{tag}_std_{int(w)}", f"series[{tag}]",
                                     f"obs in [t-{int(w)}m, t]", "rolling std", w, u))
        specs.append(FeatureSpec(f"{tag}_slope_{int(_SLOPE_MIN)}", f"series[{tag}]",
                                 f"obs in [t-{int(_SLOPE_MIN)}m, t]", "OLS slope per min",
                                 _SLOPE_MIN, f"{u}/min"))
    specs += [
        FeatureSpec("lab_last_mfi", "lab_results", "result_at<=t", "last resulted lab MFI", 0.0, "g/10min"),
        FeatureSpec("lab_time_since_result_min", "lab_results", "result_at<=t",
                    "t - last result_at", 0.0, "min"),
        FeatureSpec("lab_resulted_count", "lab_results", "result_at<=t", "count", 0.0, "count"),
        FeatureSpec("lab_pending_count", "pending_labs", "collected<=t<result_at", "count", 0.0, "count"),
        FeatureSpec("time_since_start_min", "event.started_at", "t - started_at", "elapsed", 0.0, "min"),
        FeatureSpec("time_since_transition_min", "series[H2_ratio]", "t - first H2 change<=t",
                    "elapsed since visible setpoint move", 0.0, "min"),
        FeatureSpec("target_mfi_from", "config.GRADES", "static recipe", "grade_from target", 0.0, "g/10min"),
        FeatureSpec("target_mfi_to", "config.GRADES", "static recipe", "grade_to target", 0.0, "g/10min"),
        FeatureSpec("spec_low_to", "config.GRADES", "static recipe", "grade_to lower spec", 0.0, "g/10min"),
        FeatureSpec("spec_high_to", "config.GRADES", "static recipe", "grade_to upper spec", 0.0, "g/10min"),
        FeatureSpec("direction_sign", "config.GRADES", "static recipe",
                    "sign(target_to - target_from)", 0.0, "-"),
        FeatureSpec("setpoint_h2_to", "config/simulate", "static recipe",
                    "hydrogen setpoint for grade_to", 0.0, "-"),
        FeatureSpec("mw_mean_age_min", "material_identity", "as-of map at t",
                    "material-window mean age", 0.0, "min"),
        FeatureSpec("mw_age_spread_min", "material_identity", "as-of map at t",
                    "residence-time dispersion", 0.0, "min"),
        FeatureSpec("mw_mapped_mass_tonnes", "material_identity", "as-of map at t",
                    "mass of material window", 0.0, "t"),
        FeatureSpec("mw_coverage", "material_identity", "as-of map at t",
                    "production-support coverage", 0.0, "-"),
        FeatureSpec("route_rate_tph", "routing_visible", "start<=t", "current visible rate", 0.0, "t/h"),
        FeatureSpec("route_is_prime", "routing_visible", "start<=t",
                    "1 if current visible route is PRIME", 0.0, "-"),
        FeatureSpec("route_ongoing", "routing_visible", "start<=t",
                    "1 if current interval not yet ended by t", 0.0, "-"),
        FeatureSpec("sensor_flag_count", "interventions", "ts<=t",
                    "visible SENSOR_FLAG count", 0.0, "count"),
    ]
    return specs


FEATURE_SPECS: list[FeatureSpec] = _build_specs()
FEATURE_NAMES: list[str] = [s.name for s in FEATURE_SPECS]


def feature_names() -> list[str]:
    return list(FEATURE_NAMES)


# ── numeric helpers over (timestamp, value) pairs ──────────────────────────

def _obs_pairs(snap: AsOfSnapshot, tag: str) -> list[tuple[datetime, float]]:
    return [(o.timestamp, float(o.value)) for o in snap.observations if o.tag == tag]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else NAN


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return NAN
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _slope_per_min(pairs: list[tuple[datetime, float]], t0: datetime) -> float:
    """OLS slope of value vs minutes-from-t0 over the given pairs."""
    if len(pairs) < 2:
        return NAN
    xs = [(ts - t0).total_seconds() / 60.0 for ts, _ in pairs]
    ys = [v for _, v in pairs]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return NAN
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom


def _window(pairs: list[tuple[datetime, float]], t: datetime, w_min: float) -> list[float]:
    lo = t - timedelta(minutes=w_min)
    return [v for ts, v in pairs if lo <= ts <= t]


def _visible_transition_start(snap: AsOfSnapshot) -> Optional[datetime]:
    h2 = sorted(_obs_pairs(snap, "H2_ratio"), key=lambda p: p[0])
    if not h2:
        return None
    base = h2[0][1]
    ref = abs(base) if abs(base) > 1e-9 else 1.0
    for ts, v in h2:
        if abs(v - base) / ref >= _H2_CHANGE_FRAC:
            return ts
    return None


def build_features(event: TransitionEvent, t: datetime,
                   map_params: Optional[MaterialMapParams] = None,
                   snapshot: Optional[AsOfSnapshot] = None) -> dict[str, float]:
    """As-of-safe numeric feature vector for a decision at time t. Deterministic.
    Consumes only the as-of snapshot and the as-of material map — never raw future
    rows."""
    snap = snapshot if snapshot is not None else as_of(event, t)
    t = snap.as_of
    feats: dict[str, float] = {}

    for tag in PROCESS_TAGS:
        pairs = sorted(_obs_pairs(snap, tag), key=lambda p: p[0])
        feats[f"{tag}_last"] = pairs[-1][1] if pairs else NAN
        lag_cut = t - timedelta(minutes=_LAG_MIN)
        before = [v for ts, v in pairs if ts <= lag_cut]
        feats[f"{tag}_lag_{int(_LAG_MIN)}"] = before[-1] if before else NAN
        for w in _ROLL_WINDOWS:
            win = _window(pairs, t, w)
            feats[f"{tag}_mean_{int(w)}"] = _mean(win)
            feats[f"{tag}_std_{int(w)}"] = _std(win)
        slope_pairs = [(ts, v) for ts, v in pairs if ts >= t - timedelta(minutes=_SLOPE_MIN)]
        feats[f"{tag}_slope_{int(_SLOPE_MIN)}"] = _slope_per_min(slope_pairs, t)

    # Lab features (resulted only; pending counted but never valued).
    results = sorted(snap.lab_results, key=lambda s: s.result_at)
    feats["lab_last_mfi"] = results[-1].mfi if results else NAN
    feats["lab_time_since_result_min"] = (
        (t - results[-1].result_at).total_seconds() / 60.0 if results else NAN)
    feats["lab_resulted_count"] = float(len(results))
    feats["lab_pending_count"] = float(len(snap.pending_labs))

    feats["time_since_start_min"] = (t - event.started_at).total_seconds() / 60.0
    tstart = _visible_transition_start(snap)
    feats["time_since_transition_min"] = (
        (t - tstart).total_seconds() / 60.0 if tstart is not None else NAN)

    g_from = C.get_grade(event.grade_from)
    g_to = C.get_grade(event.grade_to)
    feats["target_mfi_from"] = g_from.target_mfi
    feats["target_mfi_to"] = g_to.target_mfi
    feats["spec_low_to"] = g_to.mfi_low
    feats["spec_high_to"] = g_to.mfi_high
    feats["direction_sign"] = float(
        (g_to.target_mfi > g_from.target_mfi) - (g_to.target_mfi < g_from.target_mfi))
    from .simulate import hydrogen_setpoint
    feats["setpoint_h2_to"] = float(hydrogen_setpoint(event.grade_to))

    mw = map_material(event, t, map_params)
    feats["mw_mean_age_min"] = mw.mean_age_min
    feats["mw_age_spread_min"] = mw.age_spread_min
    feats["mw_mapped_mass_tonnes"] = mw.mapped_mass_tonnes
    feats["mw_coverage"] = mw.coverage

    if snap.routing_visible:
        cur = max(snap.routing_visible, key=lambda r: r.start)
        feats["route_rate_tph"] = cur.rate_tph
        feats["route_is_prime"] = 1.0 if cur.destination == "PRIME" else 0.0
        feats["route_ongoing"] = 1.0 if cur.ongoing else 0.0
    else:
        feats["route_rate_tph"] = NAN
        feats["route_is_prime"] = NAN
        feats["route_ongoing"] = NAN

    feats["sensor_flag_count"] = float(
        sum(1 for iv in snap.interventions if iv.kind == "SENSOR_FLAG"))

    return {name: feats[name] for name in FEATURE_NAMES}
