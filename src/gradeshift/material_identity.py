"""Material identity / residence-time mapping (Phase 4).

Answers, for a decision at reactor-evidence time t: *what downstream material
window does the current process evidence correspond to, when was it produced,
how much mass, where is it routed, and how certain is that mapping?*

Two time axes are kept DISTINCT and never collapsed into one timestamp:
  * production (reactor-state) time — when material was made in the reactor;
  * downstream material (commercial) time — when that material passes the
    routing / disposition point.

The link between them is a residence-time distribution (RTD) kernel plus a
SEPARATE deterministic transport delay:

    downstream_material_time = production_time + transport_delay + residence(theta)

where residence(theta) ~ RTD kernel (random, dispersed) and transport_delay is
deterministic (shifts the mean, adds NO spread). We never hide all delay in one
number: `mean_age_min` carries total delay + mean residence, while
`age_spread_min` carries ONLY the kernel's residence dispersion.

ANTI-OVERCLAIM: the CSTR / Erlang kernels here are ILLUSTRATIVE, SIMULATED
ASSUMPTIONS. They are NOT HMEL's measured residence-time distribution, a
plant-validated reactor model, or a digital twin. Residence-time uncertainty is
exposed (not pretended exact) so later phases can gate on it.

CAUSALITY: `map_material` is as-of safe — it uses only routing/production
visible at or before t (future routing switches and future rate changes are
clipped away). `reconcile_episode` is an explicitly non-causal post-hoc audit
used for mass-conservation checks only; the decision path must not consume it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from scipy.stats import gamma as _gamma

from .provenance import Provenance
from .schemas import MaterialWindow, RoutingInterval, TransitionEvent

# The residence/transport mapping is a declared SIMULATION ASSUMPTION.
MAPPING_PROVENANCE = Provenance.ASSUMPTION
RESIDENCE_MODEL_VERSION = "residence-map-v1"


def _require_utc(t: datetime) -> datetime:
    if not isinstance(t, datetime) or t.tzinfo is None:
        raise ValueError("time t must be timezone-aware (UTC)")
    return t.astimezone(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────
# Residence-time kernels (RTD). ILLUSTRATIVE / SIMULATED — not plant-measured.
# ──────────────────────────────────────────────────────────────────────────


class ResidenceKernel:
    """Abstract RTD over residence age theta >= 0 (minutes)."""
    name: str = "ABSTRACT"

    def mean(self) -> float:
        raise NotImplementedError

    def var(self) -> float:
        raise NotImplementedError

    def std(self) -> float:
        return math.sqrt(self.var())

    def pdf(self, theta: float) -> float:
        raise NotImplementedError

    def cdf(self, theta: float) -> float:
        raise NotImplementedError

    def quantile(self, p: float) -> float:
        raise NotImplementedError


class CSTRKernel(ResidenceKernel):
    """Single ideal CSTR — the MINIMUM residence model. Exponential RTD:
    E(theta) = (1/tau) exp(-theta/tau), mean = tau, var = tau**2. This is the
    maximally-mixed limit (also Erlang with k=1)."""

    def __init__(self, tau_min: float):
        if tau_min <= 0:
            raise ValueError("CSTR tau_min must be positive")
        self.tau = float(tau_min)
        self.name = "CSTR"

    def mean(self) -> float:
        return self.tau

    def var(self) -> float:
        return self.tau ** 2

    def pdf(self, theta: float) -> float:
        if theta < 0:
            return 0.0
        return math.exp(-theta / self.tau) / self.tau

    def cdf(self, theta: float) -> float:
        if theta <= 0:
            return 0.0
        return 1.0 - math.exp(-theta / self.tau)

    def quantile(self, p: float) -> float:
        if not 0.0 <= p < 1.0:
            raise ValueError("quantile p must be in [0, 1)")
        return -self.tau * math.log(1.0 - p)


class ErlangKernel(ResidenceKernel):
    """Tanks-in-series (k equal CSTRs, total mean tau). Erlang/Gamma RTD with
    shape k, scale tau/k: mean = tau, var = tau**2 / k. Larger k -> narrower
    (more plug-flow-like); k = 1 reduces to the single CSTR. Justified only as a
    tunable illustrative dispersion model, NOT a plant-fit."""

    def __init__(self, tau_min: float, k: int):
        if tau_min <= 0:
            raise ValueError("Erlang tau_min must be positive")
        if int(k) != k or k < 1:
            raise ValueError("Erlang k (tanks in series) must be an integer >= 1")
        self.tau = float(tau_min)
        self.k = int(k)
        self.scale = self.tau / self.k
        self.name = f"ERLANG(k={self.k})"

    def mean(self) -> float:
        return self.tau

    def var(self) -> float:
        return self.tau ** 2 / self.k

    def pdf(self, theta: float) -> float:
        if theta < 0:
            return 0.0
        return float(_gamma.pdf(theta, a=self.k, scale=self.scale))

    def cdf(self, theta: float) -> float:
        if theta <= 0:
            return 0.0
        return float(_gamma.cdf(theta, a=self.k, scale=self.scale))

    def quantile(self, p: float) -> float:
        if not 0.0 <= p < 1.0:
            raise ValueError("quantile p must be in [0, 1)")
        return float(_gamma.ppf(p, a=self.k, scale=self.scale))


# ──────────────────────────────────────────────────────────────────────────
# Mapping parameters and kernel factory
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class MaterialMapParams:
    """Configurable residence/transport mapping. All values are SIMULATED
    ASSUMPTIONS, not plant-validated."""
    kernel: str = "CSTR"            # "CSTR" or "ERLANG"
    tau_min: float = 150.0         # mean reactor residence time
    erlang_k: int = 3              # tanks-in-series (ignored for CSTR)
    transport_delay_min: float = 12.0   # deterministic plug-flow transport delay
    extra_delay_min: float = 0.0        # optional additional deterministic delay
    coverage: float = 0.90         # central mass for production-time support
    window_min: float = 60.0       # downstream material-time band width
    version: str = RESIDENCE_MODEL_VERSION

    def __post_init__(self) -> None:
        if self.tau_min <= 0:
            raise ValueError("tau_min must be positive")
        if self.transport_delay_min < 0 or self.extra_delay_min < 0:
            raise ValueError("delays must be non-negative")
        if not 0.0 < self.coverage < 1.0:
            raise ValueError("coverage must be in (0, 1)")
        if self.window_min <= 0:
            raise ValueError("window_min must be positive")
        if int(self.erlang_k) != self.erlang_k or self.erlang_k < 1:
            raise ValueError("erlang_k must be an integer >= 1")
        if self.kernel.upper() not in ("CSTR", "ERLANG", "TANKS"):
            raise ValueError(f"unknown kernel {self.kernel!r}")

    @property
    def total_delay_min(self) -> float:
        return self.transport_delay_min + self.extra_delay_min


def build_kernel(params: MaterialMapParams) -> ResidenceKernel:
    k = params.kernel.upper()
    if k == "CSTR":
        return CSTRKernel(params.tau_min)
    return ErlangKernel(params.tau_min, params.erlang_k)


# ──────────────────────────────────────────────────────────────────────────
# Mass split across routing destinations
# ──────────────────────────────────────────────────────────────────────────


def _overlap_mass(routing: Sequence[RoutingInterval],
                  mt_start: datetime, mt_end: datetime) -> list[tuple[str, float]]:
    """Mass of the downstream band [mt_start, mt_end] split across routing
    destinations by temporal overlap. A band spanning a routing boundary yields
    MULTIPLE entries — mass is never collapsed onto a single route."""
    out: list[tuple[str, float]] = []
    for r in sorted(routing, key=lambda r: r.start):
        a = max(r.start, mt_start)
        b = min(r.end, mt_end)
        if b > a:
            hours = (b - a).total_seconds() / 3600.0
            out.append((r.destination, r.rate_tph * hours))
    return out


def _visible_routing(routing: Sequence[RoutingInterval], t: datetime) -> list[RoutingInterval]:
    """Routing known as-of t: only intervals that have started (start <= t), each
    clipped to end at t. Future switch times and future rate changes are removed,
    so nothing downstream of the decision can leak."""
    out: list[RoutingInterval] = []
    for r in routing:
        if r.start <= t:
            end = min(r.end, t)
            if end > r.start:
                out.append(RoutingInterval(r.start, end, r.destination, r.rate_tph))
    return out


# ──────────────────────────────────────────────────────────────────────────
# Core mapper
# ──────────────────────────────────────────────────────────────────────────


def map_material(event: TransitionEvent, t: datetime,
                 params: Optional[MaterialMapParams] = None,
                 *, routing: Optional[Sequence[RoutingInterval]] = None) -> MaterialWindow:
    """As-of-safe material identity for a decision at time t.

    The downstream material band is [t - window_min, t] (ends at the decision,
    never reaches into the future). Its mass is split across routing destinations
    KNOWN as-of t, and mapped back through (transport delay + residence kernel)
    to a production-time support at the configured coverage. Deterministic.
    """
    params = params or MaterialMapParams()
    t = _require_utc(t)
    kernel = build_kernel(params)
    total_delay = params.total_delay_min

    mt_end = t
    mt_start = t - timedelta(minutes=params.window_min)
    if mt_start < event.started_at:          # no material predates the episode
        mt_start = event.started_at

    if routing is None:
        routing = _visible_routing(event.routing, t)
    dests = _overlap_mass(routing, mt_start, mt_end)
    mapped_mass = sum(m for _, m in dests)

    # Production-time support: map the band back by transport delay + residence
    # quantiles. Older material (larger theta) was produced earlier.
    lo = (1.0 - params.coverage) / 2.0
    hi = 1.0 - lo
    theta_lo = kernel.quantile(lo)
    theta_hi = kernel.quantile(hi)
    prod_start = mt_start - timedelta(minutes=total_delay + theta_hi)
    prod_end = mt_end - timedelta(minutes=total_delay + theta_lo)

    mean_age = total_delay + kernel.mean()   # delay shifts the mean …
    age_spread = kernel.std()                # … but adds NO spread (deterministic)

    return MaterialWindow(
        event_id=event.event_id, decision_time=t,
        mean_age_min=mean_age, age_spread_min=age_spread, mapped_mass_tonnes=mapped_mass,
        material_time_start=mt_start, material_time_end=mt_end,
        production_time_start=prod_start, production_time_end=prod_end,
        destinations=tuple(dests), kernel=kernel.name, tau_min=params.tau_min,
        transport_delay_min=params.transport_delay_min, extra_delay_min=params.extra_delay_min,
        coverage=params.coverage, version=params.version,
        mapping_provenance=MAPPING_PROVENANCE)


def _episode_end(event: TransitionEvent) -> datetime:
    if event.ended_at is not None:
        return event.ended_at
    ends = [r.end for r in event.routing]
    return max(ends) if ends else event.started_at


def reconcile_episode(event: TransitionEvent,
                      params: Optional[MaterialMapParams] = None) -> MaterialWindow:
    """POST-HOC AUDIT (explicitly NON-CAUSAL): map the whole produced band
    [started_at, ended_at] using the COMPLETE routing record, for mass-conservation
    reconciliation. The decision path must never consume this — only `map_material`
    is as-of safe."""
    params = params or MaterialMapParams()
    start = event.started_at
    end = _episode_end(event)
    full_window_min = (end - start).total_seconds() / 60.0
    if full_window_min <= 0:
        full_window_min = max(params.window_min, 1.0)
    rp = replace(params, window_min=full_window_min)
    return map_material(event, end, rp, routing=event.routing)
