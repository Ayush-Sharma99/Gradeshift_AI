"""Phase 8 — MATERIAL IDENTITY as a first-class decision input.

This module does NOT reimplement residence-time mapping. It is a thin,
deterministic SERVICE layer over the existing Phase 4 mapper
(`material_identity.map_material`, the CSTR/Erlang kernels, transport delay,
routing-overlap mass split and as-of safeguards). It operationalises that
mapper into the PrimePath evidence chain and answers, at decision time t:

    which physical production/material window is associated with the available
    quality evidence, how much material it represents, where it is routed, and
    how trustworthy that association is.

It produces:
  * `MaterialResolution`  — the rich, provenance-preserving mapping result;
  * `MaterialEligibilityResult` — the clean interface the upcoming disposition
     engine consumes (NOT itself a HOLD/SAMPLE/PRIME decision);
  * `MaterialQualityLineage` — a serializable link
        process evidence @ t -> predicted material quality -> material
        production window -> downstream route -> applicable commercial spec,
     so a viewer sees why PrimePath refers to THIS material and not merely the
     reactor state at the current timestamp.

ANTI-OVERCLAIM: everything here is SIMULATION / ASSUMPTION based. It is NOT
HMEL-validated, plant-calibrated, a digital twin, or exact material tracking.
Mapping uncertainty is exposed explicitly; it is never reduced to a fake
"probability the material is good".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from .material_identity import (
    MaterialMapParams, RESIDENCE_MODEL_VERSION, map_material,
    _visible_routing,
)
from .provenance import Provenance
from .schemas import MaterialWindow, PredictionBundle, TransitionEvent

MATERIAL_SERVICE_VERSION = "material-service-v1"


class MappingQuality(str, Enum):
    """How trustworthy the material association is. Preserved, never collapsed
    into a single scalar probability."""
    WELL_SUPPORTED = "WELL_SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE = "UNAVAILABLE"


_Q_RANK = {MappingQuality.WELL_SUPPORTED: 0, MappingQuality.PARTIALLY_SUPPORTED: 1,
           MappingQuality.AMBIGUOUS: 2, MappingQuality.UNAVAILABLE: 3}


def _worst_quality(a: MappingQuality, b: MappingQuality) -> MappingQuality:
    return a if _Q_RANK[a] >= _Q_RANK[b] else b


# ── reason codes (one per distinct mapping failure/flag mode) ───────────────
MR_OK = "MATERIAL_WELL_SUPPORTED"
MR_PARTIAL = "PARTIAL_MATERIAL_WINDOW"
MR_INSUFFICIENT = "INSUFFICIENT_MATERIAL_SUPPORT"
MR_ROUTE_UNKNOWN = "ROUTE_UNKNOWN"
MR_ROUTE_AMBIGUOUS = "ROUTE_AMBIGUOUS"
MR_MASS_UNRECONCILED = "MASS_UNRECONCILED"
MR_ZERO_FLOW = "ZERO_FLOW"
MR_VERSION_MISMATCH = "MAPPING_VERSION_MISMATCH"

# Codes an UNAVAILABLE mapping raises — a later hard gate treats these as
# blocking (the material identity is not trustworthy enough to disposition).
BLOCKING_CODES = frozenset({MR_INSUFFICIENT, MR_ROUTE_UNKNOWN, MR_ZERO_FLOW,
                            MR_VERSION_MISMATCH})

# Provenance of each service rule — all ASSUMPTION/POLICY, never HMEL limits.
MATERIAL_RULE_PROVENANCE = {
    MR_INSUFFICIENT: "POLICY (minimum material-support fraction at decision time)",
    MR_ROUTE_AMBIGUOUS: "POLICY (route-dominance threshold + residence-spread proximity)",
    MR_MASS_UNRECONCILED: "POLICY (mass reconciliation tolerance)",
    MR_PARTIAL: "DATA-SUPPORT (window partially backed by known routing / material)",
    MR_ZERO_FLOW: "DATA-INTEGRITY (no throughput available as-of t)",
    MR_ROUTE_UNKNOWN: "DATA-INTEGRITY (no routing destination known as-of t)",
    MR_VERSION_MISMATCH: "DATA-INTEGRITY (mapping artifact/schema version)",
}


@dataclass(frozen=True)
class DecisionContext:
    """Decision-time configuration carried into the material service. Every
    threshold is a documented POLICY/ASSUMPTION, not an HMEL operating limit."""
    map_params: MaterialMapParams = field(default_factory=MaterialMapParams)
    min_support_fraction: float = 0.5     # POLICY: below -> UNAVAILABLE (insufficient)
    route_dominance_threshold: float = 0.85  # POLICY: dominant share to call route known
    mass_tol_frac: float = 0.05           # POLICY: |unexplained|/expected within this -> reconciled
    target_grade: Optional[str] = None    # commercial grade the window is assessed against
    spec_band: Optional[tuple] = None     # (lo, hi) MFI spec, carried for lineage (not evaluated here)
    service_version: str = MATERIAL_SERVICE_VERSION

    def __post_init__(self) -> None:
        if not 0.0 < self.min_support_fraction <= 1.0:
            raise ValueError("min_support_fraction must be in (0, 1]")
        if not 0.0 < self.route_dominance_threshold <= 1.0:
            raise ValueError("route_dominance_threshold must be in (0, 1]")
        if self.mass_tol_frac < 0:
            raise ValueError("mass_tol_frac must be non-negative")

    def to_dict(self) -> dict:
        return {"map_params_version": self.map_params.version,
                "kernel": self.map_params.kernel, "tau_min": self.map_params.tau_min,
                "coverage": self.map_params.coverage, "window_min": self.map_params.window_min,
                "min_support_fraction": self.min_support_fraction,
                "route_dominance_threshold": self.route_dominance_threshold,
                "mass_tol_frac": self.mass_tol_frac, "target_grade": self.target_grade,
                "spec_band": list(self.spec_band) if self.spec_band else None,
                "service_version": self.service_version}


@dataclass(frozen=True)
class MassReconciliation:
    """Explicit mass accounting. Discrepancies are surfaced, never hidden.

    expected_mass = reference throughput over the ACTUAL downstream band;
    mapped_mass   = mass actually assigned to known routing destinations;
    unexplained   = expected - mapped (unrouted material within the band).
    Clipping at the episode start is NOT counted as unexplained — it is a
    support limitation and reported separately via support_fraction."""
    expected_mass_tonnes: float
    mapped_mass_tonnes: float
    unexplained_mass_tonnes: float
    tolerance_frac: float
    reconciled: bool

    def to_dict(self) -> dict:
        return {"expected_mass_tonnes": self.expected_mass_tonnes,
                "mapped_mass_tonnes": self.mapped_mass_tonnes,
                "unexplained_mass_tonnes": self.unexplained_mass_tonnes,
                "tolerance_frac": self.tolerance_frac, "reconciled": self.reconciled}


@dataclass(frozen=True)
class MaterialEligibilityResult:
    """Clean interface for the upcoming disposition engine. It answers only:
    'is the material-identity evidence trustworthy enough for a later
    disposition decision?' — NOT the final HOLD/SAMPLE/PRIME action."""
    material_window_available: bool
    mapping_quality: MappingQuality
    route_known: bool
    mass_reconciled: bool
    residence_uncertainty_min: float
    route_ambiguity: float
    blocking_reason_codes: tuple
    reason_codes: tuple
    provenance: Provenance = Provenance.ASSUMPTION
    service_version: str = MATERIAL_SERVICE_VERSION

    @property
    def is_blocking(self) -> bool:
        """A later hard gate turns this into ABSTAIN / FOLLOW SOP."""
        return bool(self.blocking_reason_codes) or not self.material_window_available

    def to_dict(self) -> dict:
        return {"material_window_available": self.material_window_available,
                "mapping_quality": self.mapping_quality.value,
                "route_known": self.route_known, "mass_reconciled": self.mass_reconciled,
                "residence_uncertainty_min": self.residence_uncertainty_min,
                "route_ambiguity": self.route_ambiguity,
                "blocking_reason_codes": list(self.blocking_reason_codes),
                "reason_codes": list(self.reason_codes),
                "provenance": self.provenance.value, "service_version": self.service_version}


@dataclass(frozen=True)
class MaterialResolution:
    """Rich, provenance-preserving material-identity result at decision time t.
    Every field is traceable to the event and the configuration used."""
    event_id: str
    decision_time: datetime
    material_window: MaterialWindow
    mapping_quality: MappingQuality
    route_known: bool
    primary_destination: Optional[str]
    route_shares: dict                 # destination -> fraction of mapped mass
    route_ambiguity: float             # 1 - dominant share (0 = unambiguous)
    boundary_within_residence_spread: bool
    residence_uncertainty_min: float   # kernel residence dispersion (std)
    support_fraction: float            # covered material-time / intended window
    mass_reconciliation: MassReconciliation
    reason_codes: tuple
    blocking_reason_codes: tuple
    detail: dict
    provenance: Provenance = Provenance.ASSUMPTION
    service_version: str = MATERIAL_SERVICE_VERSION

    def to_eligibility(self) -> MaterialEligibilityResult:
        return MaterialEligibilityResult(
            material_window_available=self.mapping_quality is not MappingQuality.UNAVAILABLE,
            mapping_quality=self.mapping_quality, route_known=self.route_known,
            mass_reconciled=self.mass_reconciliation.reconciled,
            residence_uncertainty_min=self.residence_uncertainty_min,
            route_ambiguity=self.route_ambiguity,
            blocking_reason_codes=self.blocking_reason_codes, reason_codes=self.reason_codes,
            provenance=self.provenance, service_version=self.service_version)

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "decision_time": self.decision_time.isoformat(),
                "material_window": self.material_window.to_dict(),
                "mapping_quality": self.mapping_quality.value,
                "route_known": self.route_known, "primary_destination": self.primary_destination,
                "route_shares": {k: round(v, 6) for k, v in self.route_shares.items()},
                "route_ambiguity": self.route_ambiguity,
                "boundary_within_residence_spread": self.boundary_within_residence_spread,
                "residence_uncertainty_min": self.residence_uncertainty_min,
                "support_fraction": self.support_fraction,
                "mass_reconciliation": self.mass_reconciliation.to_dict(),
                "reason_codes": list(self.reason_codes),
                "blocking_reason_codes": list(self.blocking_reason_codes),
                "rule_provenance": {c: MATERIAL_RULE_PROVENANCE.get(c, "")
                                    for c in self.reason_codes},
                "detail": self.detail, "provenance": self.provenance.value,
                "service_version": self.service_version}


@dataclass(frozen=True)
class MaterialQualityLineage:
    """Serializable link that lets a viewer see WHY PrimePath refers to THIS
    material, not merely the reactor state at the current timestamp:

        process evidence @ t  ->  predicted material quality (+ interval)
        ->  material production window  ->  downstream route
        ->  applicable commercial specification.

    It carries the artifacts, never a collapsed verdict. The prediction speaks
    to the MATERIAL in the production window, which is distinct from the reactor
    reading at t (they are separated by transport delay + residence time)."""
    prediction: PredictionBundle
    resolution: MaterialResolution
    context: DecisionContext
    note: str = ("Prediction describes the material in the mapped PRODUCTION "
                 "window, not the reactor state at the decision timestamp; "
                 "the two differ by transport delay + residence time. "
                 "SIMULATION/ASSUMPTION — not HMEL-validated.")

    def to_dict(self) -> dict:
        return {"process_evidence_at_t": {"decision_time": self.prediction.decision_time.isoformat(),
                                          "point_mfi": self.prediction.point_mfi},
                "predicted_material_quality": self.prediction.to_dict(),
                "prediction_interval": [self.prediction.lower_mfi, self.prediction.upper_mfi],
                "material_production_window": {
                    "production_time_start": self.resolution.material_window.production_time_start.isoformat(),
                    "production_time_end": self.resolution.material_window.production_time_end.isoformat(),
                    "mean_age_min": self.resolution.material_window.mean_age_min,
                    "age_spread_min": self.resolution.material_window.age_spread_min},
                "downstream_route": {"primary_destination": self.resolution.primary_destination,
                                     "route_shares": {k: round(v, 6) for k, v
                                                      in self.resolution.route_shares.items()},
                                     "route_known": self.resolution.route_known},
                "applicable_commercial_spec": {"target_grade": self.context.target_grade,
                                               "spec_band": list(self.context.spec_band)
                                               if self.context.spec_band else None},
                "mapping_support": self.resolution.mapping_quality.value,
                "note": self.note}


# ──────────────────────────────────────────────────────────────────────────
# Decision-time material service (thin layer over the Phase-4 mapper)
# ──────────────────────────────────────────────────────────────────────────


def _overlap_hours(routing, mt_start: datetime, mt_end: datetime) -> float:
    """Total routed hours of the band [mt_start, mt_end] covered by known
    routing. Mirrors material_identity._overlap_mass but returns time, so the
    reference throughput can be reconstructed without re-deriving mass."""
    total = 0.0
    for r in routing:
        a = max(r.start, mt_start)
        b = min(r.end, mt_end)
        if b > a:
            total += (b - a).total_seconds() / 3600.0
    return total


def _boundary_near_band(routing, mt_start: datetime, mt_end: datetime,
                        t: datetime, spread_min: float) -> bool:
    """True if a genuine DESTINATION switch (visible as-of t) sits inside the
    band, or within `spread_min` minutes of it — i.e. residence dispersion could
    straddle it, so the band's material cannot be confidently assigned to one
    route. A rate-only change with the SAME destination is NOT a switch, and the
    artificial clip at t (and anything after t) is excluded for as-of safety."""
    ordered = sorted(routing, key=lambda r: r.start)
    switches: list[datetime] = []
    for a, b in zip(ordered, ordered[1:]):
        if a.destination != b.destination and b.start <= t and b.start != t:
            switches.append(b.start)             # the destination-change instant
    for edge in switches:
        if edge < mt_start:
            dist = (mt_start - edge).total_seconds() / 60.0
        elif edge > mt_end:
            dist = (edge - mt_end).total_seconds() / 60.0
        else:
            return True
        if dist <= spread_min:
            return True
    return False




def resolve_material_window(event: TransitionEvent,
                            decision_context: Optional[DecisionContext] = None,
                            decision_time: Optional[datetime] = None) -> MaterialResolution:
    """Operationalise the Phase-4 material mapper at decision time t.

    Reuses `map_material` (no re-implementation) and layers DECISION semantics
    on top: route dominance, mass reconciliation, support/coverage and an
    explicit mapping-quality verdict with provenance. As-of safe — only routing
    visible at/before t is consulted. Deterministic. SIMULATION/ASSUMPTION."""
    ctx = decision_context or DecisionContext()
    if decision_time is None:
        raise ValueError("decision_time is required")
    t = decision_time

    reasons: list[str] = []
    quality = MappingQuality.WELL_SUPPORTED

    # Map first (works for any params); the window is kept for transparency even
    # when the artifact version is wrong, but the verdict is forced UNAVAILABLE.
    mw = map_material(event, t, ctx.map_params)
    version_ok = ctx.map_params.version == RESIDENCE_MODEL_VERSION

    mt_start, mt_end = mw.material_time_start, mw.material_time_end
    visible = _visible_routing(event.routing, t)

    # ── route shares over the mapped mass (never collapse a boundary split) ──
    shares: dict = {}
    for dest, mass in mw.destinations:
        shares[dest] = shares.get(dest, 0.0) + mass
    mapped_mass = sum(shares.values())
    if mapped_mass > 0:
        route_shares = {d: m / mapped_mass for d, m in shares.items()}
        dominant_share = max(route_shares.values())
    else:
        route_shares = {}
        dominant_share = 0.0
    route_ambiguity = round(1.0 - dominant_share, 6) if route_shares else 1.0

    # ── mass accounting (discrepancies surfaced, never hidden) ───────────────
    covered_hours = _overlap_hours(visible, mt_start, mt_end)
    band_hours = (mt_end - mt_start).total_seconds() / 3600.0
    reference_rate = mapped_mass / covered_hours if covered_hours > 0 else 0.0
    expected_mass = reference_rate * band_hours
    unexplained_mass = expected_mass - mapped_mass
    if expected_mass > 0:
        reconciled = abs(unexplained_mass) <= ctx.mass_tol_frac * expected_mass
    else:
        reconciled = (mapped_mass == 0.0)
    mass_rec = MassReconciliation(
        expected_mass_tonnes=round(expected_mass, 6),
        mapped_mass_tonnes=round(mapped_mass, 6),
        unexplained_mass_tonnes=round(unexplained_mass, 6),
        tolerance_frac=ctx.mass_tol_frac, reconciled=reconciled)

    # support = routed material-time covered / intended window (folds in both
    # episode-start clipping and routing gaps inside the band).
    covered_min = covered_hours * 60.0
    support_fraction = min(1.0, covered_min / ctx.map_params.window_min) \
        if ctx.map_params.window_min > 0 else 0.0

    # ── ambiguity: dominant share below threshold, OR a routing boundary close
    #    enough that residence dispersion could straddle it ───────────────────
    boundary_near = _boundary_near_band(event.routing, mt_start, mt_end, t, mw.age_spread_min)
    multi_route = len(route_shares) > 1
    is_ambiguous = (multi_route and dominant_share < ctx.route_dominance_threshold) \
        or boundary_near

    # ── verdict tree (worst-of; every trigger keeps its reason code) ─────────
    def _flag(code: str, q: MappingQuality) -> None:
        nonlocal quality
        reasons.append(code)
        quality = _worst_quality(quality, q)

    if not version_ok:
        _flag(MR_VERSION_MISMATCH, MappingQuality.UNAVAILABLE)
    if not visible or not route_shares:
        _flag(MR_ROUTE_UNKNOWN, MappingQuality.UNAVAILABLE)
    if mapped_mass <= 0.0:
        _flag(MR_ZERO_FLOW, MappingQuality.UNAVAILABLE)
    if support_fraction < ctx.min_support_fraction:
        _flag(MR_INSUFFICIENT, MappingQuality.UNAVAILABLE)
    if is_ambiguous:
        _flag(MR_ROUTE_AMBIGUOUS, MappingQuality.AMBIGUOUS)
    if not reconciled:
        _flag(MR_MASS_UNRECONCILED, MappingQuality.PARTIALLY_SUPPORTED)
    if 0.0 < support_fraction < 1.0:
        _flag(MR_PARTIAL, MappingQuality.PARTIALLY_SUPPORTED)
    if not reasons:
        reasons.append(MR_OK)

    # route is "known" only when a single destination clearly dominates and the
    # mapping is not ambiguous/unavailable — the wrong route is NEVER chosen
    # silently; ambiguity yields primary_destination=None instead.
    route_known = (quality in (MappingQuality.WELL_SUPPORTED,
                               MappingQuality.PARTIALLY_SUPPORTED)
                   and not is_ambiguous
                   and dominant_share >= ctx.route_dominance_threshold)
    primary_destination = None
    if route_known and route_shares:
        primary_destination = max(route_shares, key=route_shares.get)

    blocking = tuple(c for c in reasons if c in BLOCKING_CODES)
    detail = {"covered_minutes": round(covered_min, 4),
              "band_minutes": round(band_hours * 60.0, 4),
              "reference_rate_tph": round(reference_rate, 6),
              "dominant_share": round(dominant_share, 6),
              "boundary_within_residence_spread": boundary_near,
              "visible_routing_intervals": len(visible),
              "version_ok": version_ok, "residence_model_version": RESIDENCE_MODEL_VERSION}

    return MaterialResolution(
        event_id=event.event_id, decision_time=t, material_window=mw,
        mapping_quality=quality, route_known=route_known,
        primary_destination=primary_destination, route_shares=route_shares,
        route_ambiguity=route_ambiguity, boundary_within_residence_spread=boundary_near,
        residence_uncertainty_min=mw.age_spread_min, support_fraction=round(support_fraction, 6),
        mass_reconciliation=mass_rec, reason_codes=tuple(reasons),
        blocking_reason_codes=blocking, detail=detail)





