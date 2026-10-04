"""Typed, validated domain schemas carrying the decision lineage.

Every observation and economic input is provenance-tagged (fixes defect D6).
All timestamps are timezone-aware UTC (validated). Each schema supports a
round-trip (`to_dict`/`from_dict`) so events can be persisted and replayed
deterministically. Validation raises `ValueError` on construction of an
invalid record — nothing silently coerces.

Lineage order:
  ProvenancedObservation / LabSample  → raw tagged inputs
  RoutingInterval                     → how material was actually routed
  TransitionEvent                     → immutable episode (series + labs + routing)
  MaterialWindow                      → residence-time map: what is at the decision point
  PredictionBundle                    → point + calibrated interval + p(bad)
  DecisionSnapshot                    → action, EL table, reasons, approver, expiry, versions
  TransitionOutcome                   → revealed later-truth reconciliation
  TransitionMemoryRecord              → immutable, retrievable only after reconciliation
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional

from .provenance import Provenance, EvidenceLevel

# ──────────────────────────────────────────────────────────────────────────
# Shared helpers
# ──────────────────────────────────────────────────────────────────────────


def _require_utc(ts: datetime, label: str) -> datetime:
    """Every timestamp in the system must be timezone-aware UTC."""
    if not isinstance(ts, datetime):
        raise ValueError(f"{label} must be a datetime, got {type(ts).__name__}")
    if ts.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware (UTC); naive datetime rejected")
    if ts.utcoffset() != timezone.utc.utcoffset(None):
        # Normalize any aware tz to UTC rather than rejecting.
        return ts.astimezone(timezone.utc)
    return ts


def _iso(ts: Optional[datetime]) -> Optional[str]:
    return ts.isoformat() if ts is not None else None


def _parse_ts(s: Optional[str], label: str) -> Optional[datetime]:
    if s is None:
        return None
    return _require_utc(datetime.fromisoformat(s), label)


def _prov(p: Any) -> Provenance:
    return p if isinstance(p, Provenance) else Provenance(p)


# ──────────────────────────────────────────────────────────────────────────
# Raw tagged inputs
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProvenancedObservation:
    """A single process-series reading with explicit provenance and units."""
    tag: str                    # e.g. "MFI_inst", "H2_ratio", "bed_temp"
    value: float
    unit: str
    timestamp: datetime
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _require_utc(self.timestamp, "observation.timestamp"))
        object.__setattr__(self, "provenance", _prov(self.provenance))
        if not self.tag:
            raise ValueError("observation.tag must be non-empty")
        if not isinstance(self.value, (int, float)):
            raise ValueError("observation.value must be numeric")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["timestamp"] = _iso(self.timestamp)
        d["provenance"] = self.provenance.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ProvenancedObservation":
        return cls(tag=d["tag"], value=float(d["value"]), unit=d["unit"],
                   timestamp=_parse_ts(d["timestamp"], "observation.timestamp"),
                   provenance=_prov(d.get("provenance", Provenance.SIMULATED)))


@dataclass(frozen=True)
class LabSample:
    """A lab MFI measurement. The core blind-window object: the truth exists at
    `collected_at` but is only KNOWABLE at `result_at`. No decision made before
    `result_at` may use `mfi` (enforced downstream by time alignment)."""
    sample_id: str
    grade_id: str
    mfi: float                  # g/10min, the measured analyte of record
    collected_at: datetime      # when material was sampled
    result_at: datetime         # when the lab result became available
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "collected_at", _require_utc(self.collected_at, "lab.collected_at"))
        object.__setattr__(self, "result_at", _require_utc(self.result_at, "lab.result_at"))
        object.__setattr__(self, "provenance", _prov(self.provenance))
        if self.mfi <= 0:
            raise ValueError("lab.mfi must be positive (g/10min)")
        if self.result_at < self.collected_at:
            raise ValueError("lab.result_at cannot precede lab.collected_at")

    @property
    def latency_min(self) -> float:
        return (self.result_at - self.collected_at).total_seconds() / 60.0

    def to_dict(self) -> dict[str, Any]:
        return {"sample_id": self.sample_id, "grade_id": self.grade_id, "mfi": self.mfi,
                "collected_at": _iso(self.collected_at), "result_at": _iso(self.result_at),
                "provenance": self.provenance.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LabSample":
        return cls(sample_id=d["sample_id"], grade_id=d["grade_id"], mfi=float(d["mfi"]),
                   collected_at=_parse_ts(d["collected_at"], "lab.collected_at"),
                   result_at=_parse_ts(d["result_at"], "lab.result_at"),
                   provenance=_prov(d.get("provenance", Provenance.SIMULATED)))


# ──────────────────────────────────────────────────────────────────────────
# Routing & the immutable episode
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RoutingInterval:
    """How transitional material was actually dispositioned over a time span."""
    start: datetime
    end: datetime
    destination: str            # "PRIME" | "DOWNGRADE" | "RECYCLE" | ...
    rate_tph: float             # tonnes/hour throughput over the interval

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", _require_utc(self.start, "routing.start"))
        object.__setattr__(self, "end", _require_utc(self.end, "routing.end"))
        if self.end < self.start:
            raise ValueError("routing.end cannot precede routing.start")
        if self.rate_tph < 0:
            raise ValueError("routing.rate_tph must be non-negative")

    @property
    def mass_tonnes(self) -> float:
        return self.rate_tph * (self.end - self.start).total_seconds() / 3600.0

    def to_dict(self) -> dict[str, Any]:
        return {"start": _iso(self.start), "end": _iso(self.end),
                "destination": self.destination, "rate_tph": self.rate_tph}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RoutingInterval":
        return cls(start=_parse_ts(d["start"], "routing.start"),
                   end=_parse_ts(d["end"], "routing.end"),
                   destination=d["destination"], rate_tph=float(d["rate_tph"]))


@dataclass(frozen=True)
class Intervention:
    """An abnormality or operator intervention during the episode (e.g. a sensor
    fault flag, a manual routing override, a trip). Timestamped; provenance-tagged.
    `kind` is a free label; `note` is human-readable context."""
    timestamp: datetime
    kind: str
    note: str = ""
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _require_utc(self.timestamp, "intervention.timestamp"))
        object.__setattr__(self, "provenance", _prov(self.provenance))
        if not self.kind:
            raise ValueError("intervention.kind must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {"timestamp": _iso(self.timestamp), "kind": self.kind,
                "note": self.note, "provenance": self.provenance.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Intervention":
        return cls(timestamp=_parse_ts(d["timestamp"], "intervention.timestamp"),
                   kind=d["kind"], note=d.get("note", ""),
                   provenance=_prov(d.get("provenance", Provenance.SIMULATED)))


@dataclass(frozen=True)
class TransitionEvent:
    """An immutable grade-transition episode. The atomic unit of splitting:
    no event_id may ever span train/calibration/test partitions."""
    event_id: str
    grade_from: str
    grade_to: str
    started_at: datetime
    series: tuple[ProvenancedObservation, ...] = field(default_factory=tuple)
    labs: tuple[LabSample, ...] = field(default_factory=tuple)
    routing: tuple[RoutingInterval, ...] = field(default_factory=tuple)
    interventions: tuple[Intervention, ...] = field(default_factory=tuple)
    ended_at: Optional[datetime] = None
    unit: str = "SIM-UNIT-1"
    versions: dict[str, str] = field(default_factory=dict)
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", _require_utc(self.started_at, "event.started_at"))
        object.__setattr__(self, "series", tuple(self.series))
        object.__setattr__(self, "labs", tuple(self.labs))
        object.__setattr__(self, "routing", tuple(self.routing))
        object.__setattr__(self, "interventions", tuple(self.interventions))
        object.__setattr__(self, "provenance", _prov(self.provenance))
        if self.ended_at is not None:
            object.__setattr__(self, "ended_at", _require_utc(self.ended_at, "event.ended_at"))
            if self.ended_at < self.started_at:
                raise ValueError("event.ended_at cannot precede event.started_at")
        if not self.event_id:
            raise ValueError("event.event_id must be non-empty")
        if self.grade_from == self.grade_to:
            raise ValueError("event.grade_from and grade_to must differ (a transition)")

    @property
    def direction(self) -> str:
        return f"{self.grade_from}->{self.grade_to}"

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "grade_from": self.grade_from,
                "grade_to": self.grade_to, "started_at": _iso(self.started_at),
                "series": [o.to_dict() for o in self.series],
                "labs": [s.to_dict() for s in self.labs],
                "routing": [r.to_dict() for r in self.routing],
                "interventions": [iv.to_dict() for iv in self.interventions],
                "ended_at": _iso(self.ended_at), "unit": self.unit,
                "versions": dict(self.versions), "provenance": self.provenance.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TransitionEvent":
        return cls(event_id=d["event_id"], grade_from=d["grade_from"], grade_to=d["grade_to"],
                   started_at=_parse_ts(d["started_at"], "event.started_at"),
                   series=tuple(ProvenancedObservation.from_dict(x) for x in d.get("series", [])),
                   labs=tuple(LabSample.from_dict(x) for x in d.get("labs", [])),
                   routing=tuple(RoutingInterval.from_dict(x) for x in d.get("routing", [])),
                   interventions=tuple(Intervention.from_dict(x) for x in d.get("interventions", [])),
                   ended_at=_parse_ts(d.get("ended_at"), "event.ended_at"),
                   unit=d.get("unit", "SIM-UNIT-1"), versions=dict(d.get("versions", {})),
                   provenance=_prov(d.get("provenance", Provenance.SIMULATED)))


# ──────────────────────────────────────────────────────────────────────────
# Decision-point objects
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MaterialWindow:
    """Residence-time map output: what material a decision at `decision_time`
    corresponds to downstream, keeping production (reactor-state) time and
    downstream material time as DISTINCT axes.

    * material-time support = [material_time_start, material_time_end]: the
      downstream commercial-material band the window covers (its routing clock).
    * production-time support = [production_time_start, production_time_end]:
      when, in reactor time, that band was produced (mapped back through the
      residence-time kernel + transport delay at `coverage` quantiles).
    * destinations = per-route mass split; a window spanning a routing boundary
      splits mass across destinations rather than collapsing to one route.
    * mean_age_min / age_spread_min = total delay (transport + extra) plus the
      kernel mean, and the kernel's residence-time dispersion. Deterministic
      transport delay shifts the mean but adds NO spread — the two are kept
      separate, never hidden in one number.

    SIMULATED / ASSUMPTION: the kernel is an illustrative RTD, not HMEL's
    measured reactor dynamics, a plant-validated model, or a digital twin."""
    event_id: str
    decision_time: datetime
    mean_age_min: float             # total delay + kernel mean residence age
    age_spread_min: float           # residence-time dispersion (kernel std)
    mapped_mass_tonnes: float       # mass represented by this window
    material_time_start: Optional[datetime] = None
    material_time_end: Optional[datetime] = None
    production_time_start: Optional[datetime] = None
    production_time_end: Optional[datetime] = None
    destinations: tuple[tuple[str, float], ...] = ()   # (destination, mass_tonnes)
    kernel: str = ""
    tau_min: float = 0.0
    transport_delay_min: float = 0.0
    extra_delay_min: float = 0.0
    coverage: float = 0.0
    version: str = ""
    mapping_provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", _require_utc(self.decision_time, "window.decision_time"))
        object.__setattr__(self, "mapping_provenance", _prov(self.mapping_provenance))
        for name in ("material_time_start", "material_time_end",
                     "production_time_start", "production_time_end"):
            val = getattr(self, name)
            if val is not None:
                object.__setattr__(self, name, _require_utc(val, f"window.{name}"))
        object.__setattr__(self, "destinations",
                           tuple((str(d), float(m)) for d, m in self.destinations))
        if self.mean_age_min < 0 or self.age_spread_min < 0:
            raise ValueError("window ages must be non-negative")
        if self.mapped_mass_tonnes < 0:
            raise ValueError("window.mapped_mass_tonnes must be non-negative")
        if any(m < 0 for _, m in self.destinations):
            raise ValueError("window destination mass must be non-negative")
        if (self.material_time_start is not None and self.material_time_end is not None
                and self.material_time_end < self.material_time_start):
            raise ValueError("window material_time_end cannot precede material_time_start")
        if (self.production_time_start is not None and self.production_time_end is not None
                and self.production_time_end < self.production_time_start):
            raise ValueError("window production_time_end cannot precede production_time_start")

    @property
    def destination_mass(self) -> dict[str, float]:
        """Mass per destination, summed across any repeated routes."""
        out: dict[str, float] = {}
        for dest, mass in self.destinations:
            out[dest] = out.get(dest, 0.0) + mass
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "decision_time": _iso(self.decision_time),
                "mean_age_min": self.mean_age_min, "age_spread_min": self.age_spread_min,
                "mapped_mass_tonnes": self.mapped_mass_tonnes,
                "material_time_start": _iso(self.material_time_start),
                "material_time_end": _iso(self.material_time_end),
                "production_time_start": _iso(self.production_time_start),
                "production_time_end": _iso(self.production_time_end),
                "destinations": [[d, m] for d, m in self.destinations],
                "kernel": self.kernel, "tau_min": self.tau_min,
                "transport_delay_min": self.transport_delay_min,
                "extra_delay_min": self.extra_delay_min, "coverage": self.coverage,
                "version": self.version,
                "mapping_provenance": self.mapping_provenance.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MaterialWindow":
        return cls(event_id=d["event_id"],
                   decision_time=_parse_ts(d["decision_time"], "window.decision_time"),
                   mean_age_min=float(d["mean_age_min"]), age_spread_min=float(d["age_spread_min"]),
                   mapped_mass_tonnes=float(d["mapped_mass_tonnes"]),
                   material_time_start=_parse_ts(d.get("material_time_start"), "window.material_time_start"),
                   material_time_end=_parse_ts(d.get("material_time_end"), "window.material_time_end"),
                   production_time_start=_parse_ts(d.get("production_time_start"), "window.production_time_start"),
                   production_time_end=_parse_ts(d.get("production_time_end"), "window.production_time_end"),
                   destinations=tuple((str(x[0]), float(x[1])) for x in d.get("destinations", [])),
                   kernel=d.get("kernel", ""), tau_min=float(d.get("tau_min", 0.0)),
                   transport_delay_min=float(d.get("transport_delay_min", 0.0)),
                   extra_delay_min=float(d.get("extra_delay_min", 0.0)),
                   coverage=float(d.get("coverage", 0.0)), version=d.get("version", ""),
                   mapping_provenance=_prov(d.get("mapping_provenance", Provenance.SIMULATED)))


@dataclass(frozen=True)
class PredictionBundle:
    """Point estimate + calibrated prediction interval + derived bad-probability.
    A point estimate ALONE must never trigger candidacy — the interval and
    p(bad) are first-class and travel together with model/calibration versions."""
    event_id: str
    decision_time: datetime
    point_mfi: float
    lower_mfi: float            # calibrated interval lower
    upper_mfi: float            # calibrated interval upper
    nominal_coverage: float     # e.g. 0.90
    prob_bad: float             # P(true MFI outside spec band), in [0, 1]
    model_version: str
    calibration_version: str
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", _require_utc(self.decision_time, "pred.decision_time"))
        object.__setattr__(self, "provenance", _prov(self.provenance))
        if self.lower_mfi > self.upper_mfi:
            raise ValueError("pred.lower_mfi cannot exceed pred.upper_mfi")
        if not (0.0 <= self.prob_bad <= 1.0):
            raise ValueError("pred.prob_bad must be in [0, 1]")
        if not (0.0 < self.nominal_coverage < 1.0):
            raise ValueError("pred.nominal_coverage must be in (0, 1)")

    @property
    def width(self) -> float:
        return self.upper_mfi - self.lower_mfi

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decision_time"] = _iso(self.decision_time)
        d["provenance"] = self.provenance.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PredictionBundle":
        return cls(event_id=d["event_id"],
                   decision_time=_parse_ts(d["decision_time"], "pred.decision_time"),
                   point_mfi=float(d["point_mfi"]), lower_mfi=float(d["lower_mfi"]),
                   upper_mfi=float(d["upper_mfi"]), nominal_coverage=float(d["nominal_coverage"]),
                   prob_bad=float(d["prob_bad"]), model_version=d["model_version"],
                   calibration_version=d["calibration_version"],
                   provenance=_prov(d.get("provenance", Provenance.SIMULATED)))


# ──────────────────────────────────────────────────────────────────────────
# Action vocabulary + the decision snapshot
# ──────────────────────────────────────────────────────────────────────────

ACTIONS = ("HOLD", "SAMPLE_NOW", "PRIME_RELEASE_CANDIDATE", "ABSTAIN")


@dataclass(frozen=True)
class DecisionSnapshot:
    """The recommendation record. Advisory only — PRIME_RELEASE_CANDIDATE is a
    candidate, never a certification; human authorization is recorded separately.
    Carries the full expected-loss table, reason codes, VOI, expiry, fallback,
    and every artifact version that produced it (assurance)."""
    event_id: str
    decision_time: datetime
    action: str                             # one of ACTIONS
    expected_loss: dict[str, float]         # action -> ₹ expected loss
    reason_codes: tuple[str, ...]           # machine-readable justifications
    voi: float                              # ₹ value of information for SAMPLE_NOW
    expiry: datetime                        # recommendation validity horizon
    approver_role: str                      # who must authorize
    fallback_action: str                    # action if recommendation expires unactioned
    versions: dict[str, str] = field(default_factory=dict)  # data/model/calib/ood/policy/econ
    authorized_by: Optional[str] = None     # recorded, never synthesized
    authorized_at: Optional[datetime] = None
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", _require_utc(self.decision_time, "decision.decision_time"))
        object.__setattr__(self, "expiry", _require_utc(self.expiry, "decision.expiry"))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        object.__setattr__(self, "provenance", _prov(self.provenance))
        if self.authorized_at is not None:
            object.__setattr__(self, "authorized_at",
                               _require_utc(self.authorized_at, "decision.authorized_at"))
        if self.action not in ACTIONS:
            raise ValueError(f"decision.action must be one of {ACTIONS}, got {self.action!r}")
        if self.fallback_action not in ACTIONS:
            raise ValueError(f"decision.fallback_action must be one of {ACTIONS}")
        if self.expiry < self.decision_time:
            raise ValueError("decision.expiry cannot precede decision.decision_time")

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "decision_time": _iso(self.decision_time),
                "action": self.action, "expected_loss": dict(self.expected_loss),
                "reason_codes": list(self.reason_codes), "voi": self.voi,
                "expiry": _iso(self.expiry), "approver_role": self.approver_role,
                "fallback_action": self.fallback_action, "versions": dict(self.versions),
                "authorized_by": self.authorized_by, "authorized_at": _iso(self.authorized_at),
                "provenance": self.provenance.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "DecisionSnapshot":
        return cls(event_id=d["event_id"],
                   decision_time=_parse_ts(d["decision_time"], "decision.decision_time"),
                   action=d["action"], expected_loss={k: float(v) for k, v in d["expected_loss"].items()},
                   reason_codes=tuple(d.get("reason_codes", [])), voi=float(d["voi"]),
                   expiry=_parse_ts(d["expiry"], "decision.expiry"), approver_role=d["approver_role"],
                   fallback_action=d["fallback_action"], versions=dict(d.get("versions", {})),
                   authorized_by=d.get("authorized_by"),
                   authorized_at=_parse_ts(d.get("authorized_at"), "decision.authorized_at"),
                   provenance=_prov(d.get("provenance", Provenance.SIMULATED)))


# ──────────────────────────────────────────────────────────────────────────
# Reconciliation & memory
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TransitionOutcome:
    """Later-truth reconciliation of a decision against the revealed lab result.
    Separates false-prime (released bad as candidate) from false-hold (withheld
    good material). Realized value is signed ₹ against the fallback/SOP baseline."""
    event_id: str
    decision_time: datetime
    revealed_mfi: float             # the lab truth that was blind at decision time
    was_in_spec: bool
    recommended_action: str
    false_prime: bool               # candidate recommended but material was bad
    false_hold: bool                # held/sampled but material was good
    realized_value: float           # ₹ vs baseline (signed)
    reconciled_at: datetime
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_time", _require_utc(self.decision_time, "outcome.decision_time"))
        object.__setattr__(self, "reconciled_at", _require_utc(self.reconciled_at, "outcome.reconciled_at"))
        object.__setattr__(self, "provenance", _prov(self.provenance))
        if self.recommended_action not in ACTIONS:
            raise ValueError(f"outcome.recommended_action must be one of {ACTIONS}")
        if self.false_prime and self.false_hold:
            raise ValueError("outcome cannot be both false_prime and false_hold")
        if self.reconciled_at < self.decision_time:
            raise ValueError("outcome.reconciled_at cannot precede outcome.decision_time")

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decision_time"] = _iso(self.decision_time)
        d["reconciled_at"] = _iso(self.reconciled_at)
        d["provenance"] = self.provenance.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TransitionOutcome":
        return cls(event_id=d["event_id"],
                   decision_time=_parse_ts(d["decision_time"], "outcome.decision_time"),
                   revealed_mfi=float(d["revealed_mfi"]), was_in_spec=bool(d["was_in_spec"]),
                   recommended_action=d["recommended_action"], false_prime=bool(d["false_prime"]),
                   false_hold=bool(d["false_hold"]), realized_value=float(d["realized_value"]),
                   reconciled_at=_parse_ts(d["reconciled_at"], "outcome.reconciled_at"),
                   provenance=_prov(d.get("provenance", Provenance.SIMULATED)))


@dataclass(frozen=True)
class TransitionMemoryRecord:
    """Immutable memory of a completed, reconciled transition. Eligible for
    DIRECTIONAL analog retrieval (A->B is not B->A) only after reconciliation —
    never before, and holdout events are isolated from retrieval during eval."""
    event_id: str
    direction: str                  # "A->B"
    decision: DecisionSnapshot
    outcome: TransitionOutcome
    reconciled: bool = True
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", _prov(self.provenance))
        if not self.reconciled:
            raise ValueError("memory record may only be created after reconciliation")
        if self.decision.event_id != self.event_id or self.outcome.event_id != self.event_id:
            raise ValueError("memory record event_id must match its decision and outcome")

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "direction": self.direction,
                "decision": self.decision.to_dict(), "outcome": self.outcome.to_dict(),
                "reconciled": self.reconciled, "provenance": self.provenance.value}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TransitionMemoryRecord":
        return cls(event_id=d["event_id"], direction=d["direction"],
                   decision=DecisionSnapshot.from_dict(d["decision"]),
                   outcome=TransitionOutcome.from_dict(d["outcome"]),
                   reconciled=bool(d.get("reconciled", True)),
                   provenance=_prov(d.get("provenance", Provenance.SIMULATED)))
