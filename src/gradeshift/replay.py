"""Phase 12 — COUNTERFACTUAL REPLAY.

A deterministic OFFLINE experiment: for the same transition episode and the same
decision timeline, compare how different disposition policies would behave when
each is given EXACTLY the information available at decision time t. Future truth
(labs, routing, interventions, final disposition) is revealed ONLY after a
policy has produced its recommendation — a strict causal firewall.

Policies:
  * SOPPolicy            — SIMULATED CURRENT/SOP TIMING FIXTURE (time-based)
  * PointThresholdPolicy — point estimate vs spec, ignores the calibrated interval
  * PrimePathPolicy      — the REAL Phase-9 + Phase-10 production stack (no re-impl)
  * OraclePolicy         — ORACLE — DIAGNOSTIC ONLY (uses future truth as a bound;
                           NEVER deployable, NEVER a competing product)

Locked-test discipline: replay may CONSUME frozen locked episodes but never
refits/recalibrates/retunes/updates anything, and parameters are never tuned
after observing results. Everything is SIMULATION/ASSUMPTION — not HMEL-validated.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Protocol, Tuple

from .config import GradeSpec, POLICY
from .provenance import Provenance
from .schemas import (PredictionBundle, TransitionEvent, RoutingInterval,
                      LabSample, ProvenancedObservation)
from .features import AsOfSnapshot, as_of, build_features, MaterialMapParams
from .health import assess_sensor_health
from . import disposition as D
from . import economics as E

REPLAY_VERSION = "replay-v1"

# frozen action labels (mirror the disposition vocabulary)
HOLD = D.HOLD
SAMPLE_NOW = D.SAMPLE_NOW
PRIME_RELEASE_CANDIDATE = D.PRIME_RELEASE_CANDIDATE
ABSTAIN = D.ABSTAIN

# policy identifiers
SOP = "SOP_FIXTURE"
POINT_THRESHOLD = "POINT_THRESHOLD"
PRIMEPATH = "PRIMEPATH"
ORACLE = "ORACLE_DIAGNOSTIC_ONLY"


# ── causal as-of event truncation (structural firewall) ─────────────────────
def as_of_event(event: TransitionEvent, t: datetime) -> TransitionEvent:
    """Return a copy of the event with EVERYTHING after t removed: online
    observations, labs whose result is known only later, routing clipped to t,
    and interventions after t. This makes the future-truth firewall STRUCTURAL —
    a policy physically cannot read post-t data from this event."""
    series = tuple(o for o in event.series if o.timestamp <= t)
    labs = tuple(l for l in event.labs if l.result_at <= t)       # known only when resulted
    routing = tuple(replace(r, end=min(r.end, t)) for r in event.routing if r.start <= t)
    interventions = tuple(iv for iv in event.interventions
                          if getattr(iv, "timestamp", getattr(iv, "at", t)) <= t) \
        if event.interventions else ()
    return replace(event, series=series, labs=labs, routing=routing,
                   interventions=interventions, ended_at=t)


# ── firewalled as-of context handed to every policy ─────────────────────────
@dataclass(frozen=True)
class AsOfContext:
    """Everything a policy may see at decision time t — and nothing after it.
    Future truth is NOT a field here (except an oracle-only diagnostic channel
    the engine attaches solely for the Oracle pass)."""
    event_id: str
    decision_time: datetime
    grade_from: str
    grade_to: str
    unit: str
    spec: Optional[GradeSpec]
    elapsed_min: float
    snapshot: AsOfSnapshot
    as_of_event: TransitionEvent                 # truncated: no post-t data
    features: Optional[Dict[str, float]]
    point_estimate: Optional[float]
    prediction: Optional[PredictionBundle]
    material_eligibility: object
    material_window_summary: Dict[str, object]
    health_report: object
    applicability_result: object
    versions: Dict[str, str]
    provenance: Provenance = Provenance.SIMULATED
    # ORACLE-ONLY diagnostic channel; None for every deployable policy
    oracle_truth: Optional[Dict[str, object]] = None

    def to_dict(self) -> dict:
        return {"event_id": self.event_id,
                "decision_time": self.decision_time.isoformat(),
                "grade_from": self.grade_from, "grade_to": self.grade_to,
                "unit": self.unit, "elapsed_min": self.elapsed_min,
                "spec_band": (self.spec.mfi_low, self.spec.mfi_high) if self.spec else None,
                "point_estimate": self.point_estimate,
                "interval": ((self.prediction.lower_mfi, self.prediction.upper_mfi)
                             if self.prediction else None),
                "material_window_summary": dict(self.material_window_summary),
                "health_state": getattr(self.health_report, "overall_state", None)
                and self.health_report.overall_state.value,
                "applicability_state": getattr(self.applicability_result, "state", None)
                and self.applicability_result.state.value,
                "as_of_evidence_ids": {
                    "observations": [o.timestamp.isoformat() for o in self.snapshot.observations],
                    "lab_results": [l.sample_id for l in self.snapshot.lab_results],
                    "routing_visible": [r.destination for r in self.snapshot.routing_visible]},
                "versions": dict(self.versions)}


@dataclass(frozen=True)
class ReplayDecision:
    policy: str
    decision_time: datetime
    action: str
    reason_codes: Tuple[str, ...] = ()
    permitted_actions: Tuple[str, ...] = ()
    expected_loss: Optional[Dict[str, float]] = None
    requested_sample: bool = False
    note: str = ""
    provenance: Provenance = Provenance.SIMULATED

    def to_dict(self) -> dict:
        return {"policy": self.policy, "decision_time": self.decision_time.isoformat(),
                "action": self.action, "reason_codes": list(self.reason_codes),
                "permitted_actions": list(self.permitted_actions),
                "expected_loss": self.expected_loss,
                "requested_sample": self.requested_sample, "note": self.note,
                "provenance": self.provenance.value}


class ReplayPolicy(Protocol):
    name: str
    def decide(self, ctx: AsOfContext) -> ReplayDecision: ...


# ── A. SIMULATED CURRENT/SOP TIMING FIXTURE (deterministic, time-based) ──────
@dataclass(frozen=True)
class SOPPolicy:
    """A documented, SIMULATED stand-in for current operating practice: a
    fixed-dwell timing rule that releases a candidate purely on elapsed time
    since the transition start, with NO uncertainty, material, or OOD reasoning.
    NOT 'HMEL current SOP' — no HMEL procedure evidence is claimed."""
    sop_dwell_min: float = 180.0                 # documented assumption
    name: str = SOP

    def decide(self, ctx: AsOfContext) -> ReplayDecision:
        if ctx.elapsed_min >= self.sop_dwell_min:
            action, note = PRIME_RELEASE_CANDIDATE, "SOP fixed-dwell elapsed"
        else:
            action, note = HOLD, "SOP fixed-dwell not yet elapsed"
        return ReplayDecision(self.name, ctx.decision_time, action,
                              reason_codes=("SOP_FIXED_DWELL",), permitted_actions=(action,),
                              note="SIMULATED CURRENT/SOP TIMING FIXTURE — " + note)


# ── B. POINT-THRESHOLD BASELINE (point estimate vs spec; no interval) ───────
@dataclass(frozen=True)
class PointThresholdPolicy:
    """Knows ONLY the point estimate and the spec band. Does NOT know the
    calibrated interval, material identity, sensor health, OOD, or economics.
    Demonstrates why point-only reasoning differs from PrimePath."""
    name: str = POINT_THRESHOLD

    def decide(self, ctx: AsOfContext) -> ReplayDecision:
        if ctx.point_estimate is None or ctx.spec is None:
            return ReplayDecision(self.name, ctx.decision_time, ABSTAIN,
                                  reason_codes=("POINT_NO_PREDICTION",),
                                  permitted_actions=(ABSTAIN,),
                                  note="no point estimate / spec available")
        in_spec = ctx.spec.mfi_low <= ctx.point_estimate <= ctx.spec.mfi_high
        action = PRIME_RELEASE_CANDIDATE if in_spec else HOLD
        return ReplayDecision(self.name, ctx.decision_time, action,
                              reason_codes=("POINT_IN_SPEC" if in_spec else "POINT_OUT_OF_SPEC",),
                              permitted_actions=(action,),
                              note="point estimate vs spec; calibrated interval IGNORED")


# ── C. PRIMEPATH (the REAL Phase-9 + Phase-10 stack; no re-implementation) ───
@dataclass(frozen=True)
class PrimePathPolicy:
    name: str = PRIMEPATH

    def decide(self, ctx: AsOfContext) -> ReplayDecision:
        evid = D.DispositionEvidence(
            event=ctx.as_of_event, decision_time=ctx.decision_time, spec=ctx.spec,
            prediction=ctx.prediction, material_eligibility=ctx.material_eligibility,
            health_report=ctx.health_report, applicability_result=ctx.applicability_result,
            sample_available=True)                # sampling is operationally offered
        result = D.evaluate_disposition(evid)     # <-- production engine, unchanged
        permitted = E.derive_permitted_actions(result)
        return ReplayDecision(self.name, ctx.decision_time, result.action,
                              reason_codes=tuple(result.reason_codes),
                              permitted_actions=permitted,
                              requested_sample=(result.action == SAMPLE_NOW),
                              note="PrimePath hard-gates-first; economics downstream")


# ── D. ORACLE — DIAGNOSTIC ONLY (future truth as a bound; NEVER deployable) ─
@dataclass(frozen=True)
class OraclePolicy:
    name: str = ORACLE

    def decide(self, ctx: AsOfContext) -> ReplayDecision:
        truth = ctx.oracle_truth
        if truth is None:
            return ReplayDecision(self.name, ctx.decision_time, ABSTAIN,
                                  reason_codes=("ORACLE_NO_TRUTH",), permitted_actions=(ABSTAIN,),
                                  note="ORACLE — DIAGNOSTIC ONLY: no revealed truth")
        action = PRIME_RELEASE_CANDIDATE if truth.get("was_in_spec") else HOLD
        return ReplayDecision(self.name, ctx.decision_time, action,
                              reason_codes=("ORACLE_BOUND",), permitted_actions=(action,),
                              note="ORACLE — DIAGNOSTIC ONLY: loss-minimizing bound using "
                                   "future truth; NOT a deployable policy or a product.")


# ── reveal future truth (ONLY after deployable policies have decided) ───────
def reveal_truth(event: TransitionEvent, t: datetime, spec: Optional[GradeSpec]
                 ) -> Dict[str, object]:
    """Future-truth, used for SCORING and for the Oracle bound. Never passed to a
    deployable policy's decide()."""
    future_labs = [l for l in event.labs if l.result_at > t]
    revealed = future_labs[0].mfi if future_labs else (
        event.labs[-1].mfi if event.labs else None)
    in_spec = (spec is not None and revealed is not None
               and spec.mfi_low <= revealed <= spec.mfi_high)
    route = next((r.destination for r in event.routing if r.start <= t < r.end),
                 event.routing[-1].destination if event.routing else "UNKNOWN")
    return {"revealed_mfi": revealed, "was_in_spec": bool(in_spec),
            "actual_route": route}


# ── per-decision outcome scoring (downstream of the decision; uses truth) ────
@dataclass(frozen=True)
class DecisionOutcome:
    policy: str
    decision_time: datetime
    action: str
    was_in_spec: Optional[bool]
    affected_mass_tonnes: float
    false_prime: bool
    false_hold: bool
    is_sample: bool
    is_abstain: bool
    false_prime_exposure_currency: float
    false_hold_opportunity_currency: float
    sample_cost_currency: float
    workflow_cost_currency: float
    realized_value_currency: float
    counterfactual_value_currency: float

    @property
    def loss_currency(self) -> float:
        return (self.false_prime_exposure_currency + self.false_hold_opportunity_currency
                + self.sample_cost_currency + self.workflow_cost_currency)

    def to_dict(self) -> dict:
        return {"policy": self.policy, "decision_time": self.decision_time.isoformat(),
                "action": self.action, "was_in_spec": self.was_in_spec,
                "affected_mass_tonnes": self.affected_mass_tonnes,
                "false_prime": self.false_prime, "false_hold": self.false_hold,
                "is_sample": self.is_sample, "is_abstain": self.is_abstain,
                "false_prime_exposure_currency": self.false_prime_exposure_currency,
                "false_hold_opportunity_currency": self.false_hold_opportunity_currency,
                "sample_cost_currency": self.sample_cost_currency,
                "workflow_cost_currency": self.workflow_cost_currency,
                "realized_value_currency": self.realized_value_currency,
                "counterfactual_value_currency": self.counterfactual_value_currency,
                "loss_currency": self.loss_currency}


def score_decision(dec: ReplayDecision, ctx: AsOfContext, truth: Dict[str, object],
                   scenario) -> DecisionOutcome:
    """Compute the economic/decision consequence of ONE decision against revealed
    truth. Strictly downstream — never influences the decision itself."""
    mass = float(ctx.material_window_summary.get("mapped_mass_tonnes", 0.0))
    in_spec = truth.get("was_in_spec")
    primes = dec.action == PRIME_RELEASE_CANDIDATE
    holds = dec.action in (HOLD, ABSTAIN, SAMPLE_NOW)
    false_prime = bool(primes and in_spec is False)
    false_hold = bool(holds and in_spec is True)
    spread = float(scenario.prime_price - scenario.downgrade_price)
    fp_exp = mass * float(scenario.false_prime_consequence) if false_prime else 0.0
    fh_opp = mass * spread if false_hold else 0.0
    sample_cost = float(scenario.sample_cost) if dec.action == SAMPLE_NOW else 0.0
    workflow = float(scenario.workflow_cost) if dec.action in (PRIME_RELEASE_CANDIDATE,
                                                               SAMPLE_NOW) else 0.0
    # realized = value of the actually-correct route; counterfactual = prime value if good
    realized = mass * (float(scenario.prime_price) if (primes and in_spec)
                       else float(scenario.downgrade_price))
    counterfactual = mass * spread if in_spec else 0.0
    return DecisionOutcome(dec.policy, dec.decision_time, dec.action, in_spec, mass,
                           false_prime, false_hold, dec.action == SAMPLE_NOW,
                           dec.action == ABSTAIN, fp_exp, fh_opp, sample_cost,
                           workflow, realized, counterfactual)


# ── replay episode container (fully reproducible manifest) ──────────────────
@dataclass(frozen=True)
class ReplayEpisode:
    event_id: str
    partition: str
    decision_times: Tuple[datetime, ...]
    contexts: Tuple[AsOfContext, ...]
    decisions: Dict[str, Tuple[ReplayDecision, ...]]       # policy -> decisions
    outcomes: Dict[str, Tuple[DecisionOutcome, ...]]
    truths: Tuple[Dict[str, object], ...]
    manifest: Dict[str, object]

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "partition": self.partition,
                "decision_times": [t.isoformat() for t in self.decision_times],
                "decisions": {p: [d.to_dict() for d in ds]
                              for p, ds in self.decisions.items()},
                "outcomes": {p: [o.to_dict() for o in os]
                             for p, os in self.outcomes.items()},
                "truths": list(self.truths), "manifest": dict(self.manifest)}


# ── the deterministic replay engine ─────────────────────────────────────────
class ReplayEngine:
    """Holds FROZEN artifacts (model, calibration, OOD detector, map params,
    economic scenario) and replays policies over a decision timeline. It never
    refits/recalibrates/retunes anything."""

    def __init__(self, gbm, calib, detector, map_params, scenario,
                 sop_dwell_min: float = 180.0,
                 policies: Optional[List[ReplayPolicy]] = None):
        self.gbm = gbm
        self.calib = calib
        self.detector = detector
        self.mp = map_params or MaterialMapParams()
        self.scenario = scenario
        self.cal_ver = f"{calib.calibration_version}:{calib.method}"
        self.deployable = policies or [SOPPolicy(sop_dwell_min=sop_dwell_min),
                                       PointThresholdPolicy(), PrimePathPolicy()]
        self.oracle = OraclePolicy()

    def _versions(self) -> Dict[str, str]:
        return {"replay": REPLAY_VERSION, "model": self.gbm.model_version,
                "calibration": self.cal_ver, "policy": POLICY.version,
                "economics": E.ECONOMICS_VERSION, "scenario": self.scenario.name}

    def build_context(self, event: TransitionEvent, t: datetime,
                      spec: Optional[GradeSpec]) -> AsOfContext:
        from .material_service import resolve_material_window, DecisionContext
        aoe = as_of_event(event, t)              # structural firewall
        snap = as_of(aoe, t)
        feats = build_features(aoe, t, self.mp)
        point = float(self.gbm.predict_one(feats))
        lo, hi, _ = self.calib.interval(point, None)
        pred = PredictionBundle(event_id=event.event_id, decision_time=t, point_mfi=point,
                                lower_mfi=lo, upper_mfi=hi,
                                nominal_coverage=self.calib.nominal_coverage, prob_bad=0.0,
                                model_version=self.gbm.model_version,
                                calibration_version=self.cal_ver)
        if spec is not None:
            ctx_mat = DecisionContext(map_params=self.mp, target_grade=spec.grade_id,
                                      spec_band=(spec.mfi_low, spec.mfi_high))
            resolution = resolve_material_window(aoe, ctx_mat, t)
            mat_elig = resolution.to_eligibility()
            mws = {"mapped_mass_tonnes": resolution.material_window.mapped_mass_tonnes,
                   "mean_age_min": resolution.material_window.mean_age_min,
                   "production_time_start": resolution.material_window.production_time_start.isoformat(),
                   "material_time_start": resolution.material_window.material_time_start.isoformat(),
                   "primary_destination": resolution.primary_destination,
                   "mapping_quality": resolution.mapping_quality.value,
                   "route_known": resolution.route_known}
        else:
            mat_elig, mws = None, {"mapped_mass_tonnes": 0.0}
        return AsOfContext(
            event_id=event.event_id, decision_time=t, grade_from=event.grade_from,
            grade_to=event.grade_to, unit=event.unit, spec=spec,
            elapsed_min=(t - event.started_at).total_seconds() / 60.0, snapshot=snap,
            as_of_event=aoe, features=feats, point_estimate=point, prediction=pred,
            material_eligibility=mat_elig, material_window_summary=mws,
            health_report=assess_sensor_health(aoe, t),
            applicability_result=self.detector.assess_event(aoe, t),
            versions=self._versions())

    def replay_episode(self, event: TransitionEvent, timestamps: List[datetime],
                       spec: Optional[GradeSpec], partition: str = "LOCKED_TEST"
                       ) -> ReplayEpisode:
        contexts: List[AsOfContext] = []
        truths: List[Dict[str, object]] = []
        dec: Dict[str, List[ReplayDecision]] = {p.name: [] for p in self.deployable}
        dec[self.oracle.name] = []
        out: Dict[str, List[DecisionOutcome]] = {k: [] for k in dec}
        for t in timestamps:
            ctx = self.build_context(event, t, spec)
            # 1) deployable policies decide with NO access to future truth
            step_decisions = {p.name: p.decide(ctx) for p in self.deployable}
            # 2) ONLY NOW reveal future truth (for Oracle bound + scoring)
            truth = reveal_truth(event, t, spec)
            oracle_dec = self.oracle.decide(replace(ctx, oracle_truth=truth))
            step_decisions[self.oracle.name] = oracle_dec
            for name, d in step_decisions.items():
                dec[name].append(d)
                out[name].append(score_decision(d, ctx, truth, self.scenario))
            contexts.append(ctx)
            truths.append(truth)
        manifest = {"versions": self._versions(), "sop_dwell_min":
                    next((p.sop_dwell_min for p in self.deployable
                          if isinstance(p, SOPPolicy)), None),
                    "n_timestamps": len(timestamps),
                    "note": "Frozen replay manifest; decisions reproducible from it."}
        return ReplayEpisode(
            event.event_id, partition, tuple(timestamps), tuple(contexts),
            {k: tuple(v) for k, v in dec.items()}, {k: tuple(v) for k, v in out.items()},
            tuple(truths), manifest)


# ── component metrics (NO single 'winner score' — raw components only) ──────
def compute_policy_metrics(ep: ReplayEpisode, policy: str) -> dict:
    decs = ep.decisions.get(policy, ())
    outs = ep.outcomes.get(policy, ())
    n = len(decs)
    cand_times = [d.decision_time for d in decs if d.action == PRIME_RELEASE_CANDIDATE]
    t0 = ep.decision_times[0] if ep.decision_times else None
    ttc = ((min(cand_times) - t0).total_seconds() / 60.0
           if cand_times and t0 else None)
    fp = [o for o in outs if o.false_prime]
    fh = [o for o in outs if o.false_hold]
    samples = [o for o in outs if o.is_sample]
    # a sample is "useful" if, at that step, the interval crossed spec (uncertainty
    # a confirmatory lab could resolve)
    useful = 0
    for d, ctx in zip(decs, ep.contexts):
        if d.action == SAMPLE_NOW and ctx.prediction is not None and ctx.spec is not None:
            if ctx.prediction.lower_mfi < ctx.spec.mfi_low or ctx.prediction.upper_mfi > ctx.spec.mfi_high:
                useful += 1
    return {
        "n_decisions": n,
        "time_to_candidate_min": ttc,
        "false_prime_rate": len(fp) / n if n else None,
        "false_prime_mass_tonnes": sum(o.affected_mass_tonnes for o in fp),
        "false_hold_rate": len(fh) / n if n else None,
        "false_hold_decisions": len(fh),
        "false_hold_mass_tonnes": sum(o.affected_mass_tonnes for o in fh),
        "n_samples": len(samples),
        "useful_sample_fraction": (useful / len(samples)) if samples else None,
        "abstention_rate": sum(1 for d in decs if d.action == ABSTAIN) / n if n else None,
        "false_prime_exposure_currency": sum(o.false_prime_exposure_currency for o in outs),
        "false_hold_opportunity_currency": sum(o.false_hold_opportunity_currency for o in outs),
        "sample_cost_currency": sum(o.sample_cost_currency for o in outs),
        "workflow_cost_currency": sum(o.workflow_cost_currency for o in outs),
        "gross_avoidable_loss_currency": sum(o.loss_currency for o in outs),
        "realized_value_currency": sum(o.realized_value_currency for o in outs),
        "counterfactual_value_currency": sum(o.counterfactual_value_currency for o in outs),
    }


def compute_regret(ep: ReplayEpisode) -> Dict[str, float]:
    """Expected regret vs the ORACLE DIAGNOSTIC lower bound (diagnostic only —
    the oracle is not a product)."""
    oracle_loss = sum(o.loss_currency for o in ep.outcomes.get(ORACLE, ()))
    return {p: sum(o.loss_currency for o in outs) - oracle_loss
            for p, outs in ep.outcomes.items()}


def build_comparison_table(ep: ReplayEpisode) -> dict:
    """Raw component comparison across policies. Explicitly NO overall score/rank."""
    regret = compute_regret(ep)
    rows = []
    for p in list(ep.decisions):
        m = compute_policy_metrics(ep, p)
        rows.append({"policy": p, "candidate_time_min": m["time_to_candidate_min"],
                     "n_samples": m["n_samples"],
                     "false_prime_mass_tonnes": m["false_prime_mass_tonnes"],
                     "false_hold_mass_tonnes": m["false_hold_mass_tonnes"],
                     "abstention_rate": m["abstention_rate"],
                     "counterfactual_value_currency": m["counterfactual_value_currency"],
                     "gross_avoidable_loss_currency": m["gross_avoidable_loss_currency"],
                     "expected_regret_vs_oracle_currency": regret.get(p)})
    return {"rows": rows, "oracle_label": "ORACLE — DIAGNOSTIC ONLY (not deployable)",
            "note": "Raw component metrics only. No overall 'winner' score or ranking "
                    "is produced. SIMULATED/ILLUSTRATIVE economics."}


def event_trace(ep: ReplayEpisode, policy: str = PRIMEPATH, step: int = 0) -> dict:
    """A complete machine-readable evidence chain for one decision:
    as-of evidence -> prediction -> interval -> material window -> health/OOD ->
    policy action -> later truth -> outcome/economics."""
    ctx = ep.contexts[step]
    dec = ep.decisions[policy][step]
    out = ep.outcomes[policy][step]
    return {"event_id": ep.event_id, "policy": policy, "step": step,
            "as_of_context": ctx.to_dict(), "decision": dec.to_dict(),
            "later_truth": ep.truths[step], "outcome": out.to_dict(),
            "note": "Full evidence chain: knew -> predicted -> did NOT know -> "
                    "recommended -> material window -> happened later -> value."}


# ── canonical ILLUSTRATIVE DEMO FIXTURE (NEVER mixed with validation) ───────
def demo_fixture(scenario=None) -> dict:
    """A transparent, frozen demo timeline T1..T5 that feeds CONTROLLED evidence
    into the REAL Phase-9 engine (no model, no locked data). It is explicitly an
    ILLUSTRATIVE DEMO FIXTURE and must never enter the validation set."""
    from datetime import timezone
    from .material_service import MaterialEligibilityResult, MappingQuality, MATERIAL_SERVICE_VERSION
    from .health import SensorHealthReport, HealthState
    from .applicability import ApplicabilityResult, ApplicabilityState
    from . import config as _C
    scenario = scenario or _C.ECON_SCENARIOS[_C.DEFAULT_SCENARIO]
    base = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ev = __import__("gradeshift.simulate", fromlist=["generate_episode"]).generate_episode(
        "DEMO-A2B", "A", "B", seed=4242, start_time=base)
    spec = _C.get_grade("B")

    def _t(m): return base + timedelta(minutes=m)

    def pred(lo, hi):
        return PredictionBundle(event_id=ev.event_id, decision_time=_t(400),
                                point_mfi=(lo + hi) / 2, lower_mfi=lo, upper_mfi=hi,
                                nominal_coverage=0.9, prob_bad=0.2,
                                model_version="demo-m", calibration_version="demo-c")

    def mat():
        return MaterialEligibilityResult(True, MappingQuality.WELL_SUPPORTED, True, True,
                                         10.0, 0.0, (), ("MATERIAL_WELL_SUPPORTED",),
                                         Provenance.SIMULATED, MATERIAL_SERVICE_VERSION)

    def evid(prediction, dwell_ok, sample):
        return D.DispositionEvidence(
            event=ev, decision_time=_t(400), spec=spec, prediction=prediction,
            material_eligibility=mat(),
            health_report=SensorHealthReport(_t(400), HealthState.NORMAL, True, {}, (),
                                             "h", Provenance.SIMULATED),
            applicability_result=ApplicabilityResult(ApplicabilityState.NORMAL, 0.0, (),
                                                     "", "f", "d", "a", Provenance.SIMULATED),
            dwell_status=D.DwellStatus(30.0, 60.0 if dwell_ok else 5.0, dwell_ok, True, _t(400)),
            sample_available=sample)

    steps = []
    # T1: point in-spec but interval crosses the limit -> HOLD
    r1 = D.evaluate_disposition(evid(pred(7.5, 8.3), dwell_ok=True, sample=False))
    steps.append({"t": "T1", "narrative": "point in-spec, interval crosses limit",
                  "action": r1.action, "reason_codes": list(r1.reason_codes),
                  "expected": HOLD})
    # T2: sampling would resolve the uncertainty -> SAMPLE NOW
    r2 = D.evaluate_disposition(evid(pred(7.5, 8.3), dwell_ok=True, sample=True))
    steps.append({"t": "T2", "narrative": "sample would resolve material uncertainty",
                  "action": r2.action, "reason_codes": list(r2.reason_codes),
                  "expected": SAMPLE_NOW})
    # T3: interval in-spec, dwell satisfied, material supported, health+OOD normal -> PRIME
    r3 = D.evaluate_disposition(evid(pred(7.7, 8.3), dwell_ok=True, sample=False))
    steps.append({"t": "T3", "narrative": "interval in-spec, dwell ok, supported, normal",
                  "action": r3.action, "reason_codes": list(r3.reason_codes),
                  "expected": PRIME_RELEASE_CANDIDATE})
    # T4: reveal future lab truth and reconcile
    revealed = 7.95
    was_in_spec = spec.mfi_low <= revealed <= spec.mfi_high
    steps.append({"t": "T4", "narrative": "future lab truth revealed -> reconcile",
                  "revealed_mfi": revealed, "was_in_spec": was_in_spec})
    # T5: economic ledger for the PRIME decision
    econ_in = E.EconomicInputs(ev.event_id, "DEMO@T3", mass_tonnes=50.0,
                               recoverable_mass_tonnes=50.0,
                               actual_route_value_per_tonne=float(scenario.downgrade_price),
                               scenario=scenario)
    econ = E.evaluate_economics(r3, econ_in, realized_good=was_in_spec)
    steps.append({"t": "T5", "narrative": "economic ledger compares consequences",
                  "ledger": econ.to_ledger()})
    return {"label": "ILLUSTRATIVE DEMO FIXTURE — not validation evidence",
            "event_id": ev.event_id, "frozen_seed": 4242, "steps": steps,
            "evidence_chain": ["knew", "predicted", "did_not_know", "recommended",
                               "material_window", "happened_later", "value_difference"],
            "note": "Controlled evidence into the REAL Phase-9 engine; NOT produced "
                    "by the model and NEVER mixed with the locked validation set."}
