"""Phase 10 — EXPECTED LOSS + VALUE-OF-INFORMATION + ECONOMIC LEDGER.

This module makes PrimePath economically decision-aware **behind** the Phase-9
policy gates. It is a PURE, DETERMINISTIC economic engine that:

  * consumes a finished Phase-9 ``DispositionResult`` (never raw data),
  * derives the set of PERMITTED actions from the frozen gate table,
  * computes an auditable expected-loss table over PERMITTED actions ONLY,
  * computes a deterministic discrete-outcome Value-of-Information for sampling,
  * emits a machine-readable ``EconomicLedger`` where every number traces to an
    input + a formula, and keeps REALIZED value separate from COUNTERFACTUAL.

NON-NEGOTIABLE INVARIANTS (enforced in code, see tests A-N):
  1. Economics NEVER decide permission. Phase 9 decides *whether* an action is
     allowed; Phase 10 only evaluates *consequence/value* among allowed actions.
  2. The engine can NEVER resurrect a blocked action. If hard gates force
     ABSTAIN, the only permitted action is ABSTAIN and no EL comparison can
     surface PRIME/HOLD/SAMPLE as "cheaper".
  3. ``prob_bad`` from Phase 6 is PROVISIONAL/ILLUSTRATIVE. The risk input is a
     pluggable, clearly-labelled proxy — never presented as a validated
     probability of bad material.

EVERYTHING here is SIMULATION / ASSUMPTION / ILLUSTRATIVE. Currency figures are
illustrative scenario inputs (``config.ECON_SCENARIOS``), NOT HMEL-validated
costs. No HMEL data, validation, savings, or safety claim is implied. A
PRIME-RELEASE CANDIDATE remains advisory and requires human/QC authorization.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Protocol, Tuple

from .config import EconScenario, ECON_SCENARIOS, DEFAULT_SCENARIO, POLICY
from .provenance import Provenance
from .disposition import (
    DispositionResult, Severity,
    HOLD, SAMPLE_NOW, PRIME_RELEASE_CANDIDATE, ABSTAIN,
)

ECONOMICS_VERSION = "economics-v1"
COST_MODEL_VERSION = "cost-model-v1"
VOI_MODEL_VERSION = "voi-discrete-v1"

# Units are explicit in every field name:
#   *_tonnes      : mass            (tonnes, t)
#   *_tph         : rate            (tonnes / hour)
#   *_per_tonne   : value / cost    (currency / tonne)
#   *_currency    : money           (currency, illustrative units)
#   *_min / *_hr  : time            (minutes / hours)
Currency = float

# default minimum VOI (currency) below which SAMPLE is not economically worth it
DEFAULT_MIN_VOI_CURRENCY: Currency = float(getattr(POLICY, "voi_threshold", 0.0))


# ── pluggable, clearly-labelled quality-risk input ───────────────────────────
# NONE of these is a validated probability of bad material. Each is a transparent
# PROXY carrying its own provenance so the ledger can never over-claim.
@dataclass(frozen=True)
class RiskEstimate:
    """A bounded risk proxy. ``p_bad`` in [0,1]; ``p_good = 1 - p_bad``."""
    p_bad: float
    kind: str                      # how the proxy was derived
    provenance: Provenance
    detail: str = ""
    validated: bool = False        # ALWAYS False — never a validated probability

    def __post_init__(self):
        if not (0.0 <= self.p_bad <= 1.0):
            raise ValueError(f"p_bad must be in [0,1], got {self.p_bad}")
        if self.validated:
            raise ValueError("risk proxy may never be flagged validated")

    @property
    def p_good(self) -> float:
        return 1.0 - self.p_bad

    def to_dict(self) -> dict:
        return {"p_bad_PROXY": self.p_bad, "p_good_PROXY": self.p_good,
                "kind": self.kind, "validated": self.validated,
                "provenance": self.provenance.value, "detail": self.detail,
                "note": "ILLUSTRATIVE risk proxy — NOT a validated probability "
                        "of bad material; not a decision trigger."}


class RiskInput(Protocol):
    """Pluggable risk-proxy interface consumed by the economic engine."""
    def estimate(self, result: DispositionResult) -> RiskEstimate: ...


@dataclass(frozen=True)
class IntervalDerivedRisk:
    """Bounded proxy from the calibrated interval vs spec band (Phase-6 interval,
    NOT p_bad). Risk = fraction of the predicted interval lying OUTSIDE spec."""
    def estimate(self, result: DispositionResult) -> RiskEstimate:
        lo, hi = result.interval
        band = result.spec_band
        if band is None or lo is None or hi is None or hi <= lo:
            return RiskEstimate(0.5, "interval_derived",
                                Provenance.ILLUSTRATIVE,
                                "degenerate interval/spec -> uninformative 0.5")
        blo, bhi = band
        inside = max(0.0, min(hi, bhi) - max(lo, blo))
        frac_out = 1.0 - inside / (hi - lo)
        frac_out = min(1.0, max(0.0, frac_out))
        return RiskEstimate(frac_out, "interval_derived", Provenance.SIMULATED,
                            f"fraction of interval [{lo:.3f},{hi:.3f}] outside "
                            f"spec [{blo:.3f},{bhi:.3f}]")


@dataclass(frozen=True)
class ProvisionalProbabilityRisk:
    """Uses Phase-6 ``prob_bad`` directly, explicitly labelled PROVISIONAL."""
    def estimate(self, result: DispositionResult) -> RiskEstimate:
        pb = result.prediction_summary.get("prob_bad_PROVISIONAL")
        if pb is None:
            return RiskEstimate(0.5, "provisional_prob_bad",
                                Provenance.ILLUSTRATIVE, "no prob_bad available")
        return RiskEstimate(float(pb), "provisional_prob_bad",
                            Provenance.ILLUSTRATIVE,
                            "Phase-6 provisional prob_bad used as proxy")


@dataclass(frozen=True)
class IllustrativeRisk:
    """A fixed, hand-set risk value for controlled scenarios."""
    p_bad: float = 0.5

    def estimate(self, result: DispositionResult) -> RiskEstimate:
        return RiskEstimate(self.p_bad, "illustrative_fixed",
                            Provenance.ILLUSTRATIVE, "fixed scenario risk proxy")


# ── permitted-action set derived from the FROZEN Phase-9 gate table ──────────
def derive_permitted_actions(result: DispositionResult) -> Tuple[str, ...]:
    """The set of actions Phase 9 ALLOWS, read from the gate table only.

    Hard-gate failure (BLOCK) => the ONLY permitted action is ABSTAIN. Otherwise
    HOLD and ABSTAIN are always permitted; PRIME is permitted iff no gate
    (BLOCK or CANDIDACY) blocks prime; SAMPLE iff Phase 9 found it eligible.

    This NEVER re-decides permission — it reflects Phase 9's gates. The economic
    engine may rank only within this set.
    """
    hard_fail = any((not g.passed) and g.severity == Severity.BLOCK
                    for g in result.gates)
    if hard_fail:
        return (ABSTAIN,)
    prime_blocked = any((not g.passed) and g.severity in (Severity.BLOCK,
                                                           Severity.CANDIDACY)
                        for g in result.gates)
    permitted = [HOLD, ABSTAIN]
    if not prime_blocked:
        permitted.insert(0, PRIME_RELEASE_CANDIDATE)
    if result.sample_eligibility is not None and result.sample_eligibility.eligible:
        permitted.append(SAMPLE_NOW)
    # stable canonical order
    order = {PRIME_RELEASE_CANDIDATE: 0, SAMPLE_NOW: 1, HOLD: 2, ABSTAIN: 3}
    return tuple(sorted(set(permitted), key=lambda a: order[a]))


# ── units-explicit, provenance-tagged cost components ───────────────────────
@dataclass(frozen=True)
class CostComponent:
    """One auditable money term. Every component names its formula + inputs."""
    name: str
    amount_currency: Currency
    provenance: Provenance
    formula: str
    inputs: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"name": self.name, "amount_currency": self.amount_currency,
                "provenance": self.provenance.value, "formula": self.formula,
                "inputs": dict(self.inputs)}


@dataclass(frozen=True)
class EconomicInputs:
    """Everything the engine needs, with explicit units. No raw data access."""
    event_id: str
    decision_id: str
    mass_tonnes: float                      # material in the decision window (t)
    recoverable_mass_tonnes: float          # <= mass_tonnes; NOT assumed = mass
    actual_route_value_per_tonne: Currency  # value of the route actually taken
    scenario: EconScenario = ECON_SCENARIOS[DEFAULT_SCENARIO]
    sample_latency_min: float = POLICY.sample_result_latency_min
    decision_horizon_min: float = POLICY.decision_horizon_min
    provenance: Provenance = Provenance.SIMULATED

    def __post_init__(self):
        if self.mass_tonnes < 0:
            raise ValueError("mass_tonnes must be >= 0")
        if not (0.0 <= self.recoverable_mass_tonnes <= self.mass_tonnes + 1e-9):
            raise ValueError("recoverable_mass_tonnes must be in [0, mass_tonnes]")

    @property
    def prime_value_per_tonne(self) -> Currency:
        return float(self.scenario.prime_price)

    @property
    def spread_per_tonne(self) -> Currency:
        """Opportunity value of priming good material vs the downgrade route."""
        return float(self.scenario.prime_price - self.scenario.downgrade_price)

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "decision_id": self.decision_id,
                "mass_tonnes": self.mass_tonnes,
                "recoverable_mass_tonnes": self.recoverable_mass_tonnes,
                "actual_route_value_per_tonne": self.actual_route_value_per_tonne,
                "prime_value_per_tonne": self.prime_value_per_tonne,
                "spread_per_tonne": self.spread_per_tonne,
                "sample_latency_min": self.sample_latency_min,
                "decision_horizon_min": self.decision_horizon_min,
                "scenario": self.scenario.name, "provenance": self.provenance.value}


# ── per-action expected loss (components sum EXACTLY to the expected loss) ────
@dataclass(frozen=True)
class ActionEconomics:
    action: str
    expected_loss_currency: Currency
    components: Tuple[CostComponent, ...]
    false_prime_exposure_currency: Currency   # unweighted worst-case if bad
    false_hold_exposure_currency: Currency    # unweighted worst-case if good
    risk: RiskEstimate
    permitted: bool

    def to_dict(self) -> dict:
        return {"action": self.action,
                "expected_loss_currency": self.expected_loss_currency,
                "false_prime_exposure_currency": self.false_prime_exposure_currency,
                "false_hold_exposure_currency": self.false_hold_exposure_currency,
                "permitted": self.permitted,
                "components": [c.to_dict() for c in self.components],
                "risk": self.risk.to_dict()}


def _hold_fraction(action: str, inp: EconomicInputs) -> float:
    """Opportunity-loss fraction a non-prime action imposes on recoverable good
    material. HOLD/ABSTAIN forgo the full spread; SAMPLE forgoes only the share
    of the horizon spent waiting for the result (ILLUSTRATIVE)."""
    if action == PRIME_RELEASE_CANDIDATE:
        return 0.0
    if action == SAMPLE_NOW:
        if inp.decision_horizon_min <= 0:
            return 1.0
        return min(1.0, max(0.0, inp.sample_latency_min / inp.decision_horizon_min))
    return 1.0  # HOLD / ABSTAIN


def compute_action_economics(action: str, inp: EconomicInputs,
                             risk: RiskEstimate, permitted: bool) -> ActionEconomics:
    """EL(a|x) = P(bad)*C_false_prime(a) + P(good)*C_false_hold(a)
                 + C_sample(a) + C_workflow(a).  (SIMULATED/ILLUSTRATIVE)"""
    sc = inp.scenario
    pb, pg = risk.p_bad, risk.p_good
    comps = []

    # A. false-prime consequence (commercial/quality, NOT a safety-incident claim)
    fp_exposure = (inp.mass_tonnes * float(sc.false_prime_consequence)
                   if action == PRIME_RELEASE_CANDIDATE else 0.0)
    comps.append(CostComponent(
        "false_prime", pb * fp_exposure, sc.provenance,
        "P(bad) * mass_tonnes * false_prime_consequence_per_tonne"
        if action == PRIME_RELEASE_CANDIDATE else "0 (action does not prime)",
        {"p_bad_PROXY": pb, "mass_tonnes": inp.mass_tonnes,
         "false_prime_consequence_per_tonne": float(sc.false_prime_consequence)}))

    # B. false-hold / opportunity loss on recoverable good material
    hold_frac = _hold_fraction(action, inp)
    fh_exposure = inp.recoverable_mass_tonnes * inp.spread_per_tonne * hold_frac
    comps.append(CostComponent(
        "false_hold_opportunity", pg * fh_exposure, sc.provenance,
        "P(good) * recoverable_mass_tonnes * spread_per_tonne * hold_fraction",
        {"p_good_PROXY": pg, "recoverable_mass_tonnes": inp.recoverable_mass_tonnes,
         "spread_per_tonne": inp.spread_per_tonne, "hold_fraction": hold_frac}))

    # C. sample cost (flat, deterministic — only when sampling)
    sample_cost = float(sc.sample_cost) if action == SAMPLE_NOW else 0.0
    comps.append(CostComponent(
        "sample_cost", sample_cost, sc.provenance,
        "scenario.sample_cost" if action == SAMPLE_NOW else "0 (no sample)",
        {"sample_cost": float(sc.sample_cost)}))

    # D/E. workflow cost (flat) for actions that trigger operational workflow
    workflow = (float(sc.workflow_cost)
                if action in (PRIME_RELEASE_CANDIDATE, SAMPLE_NOW) else 0.0)
    comps.append(CostComponent(
        "workflow_cost", workflow, sc.provenance,
        "scenario.workflow_cost" if workflow else "0 (no workflow triggered)",
        {"workflow_cost": float(sc.workflow_cost)}))

    el = sum(c.amount_currency for c in comps)
    return ActionEconomics(action, el, tuple(comps), fp_exposure, fh_exposure,
                           risk, permitted)


# ── expected-loss table over PERMITTED actions only ─────────────────────────
@dataclass(frozen=True)
class ExpectedLossReport:
    rows: Tuple[ActionEconomics, ...]          # permitted actions only
    min_loss_action: Optional[str]             # cheapest PERMITTED action
    permitted_actions: Tuple[str, ...]

    def as_action_map(self) -> Dict[str, Currency]:
        return {r.action: r.expected_loss_currency for r in self.rows}

    def get(self, action: str) -> Optional[ActionEconomics]:
        for r in self.rows:
            if r.action == action:
                return r
        return None

    def to_dict(self) -> dict:
        return {"permitted_actions": list(self.permitted_actions),
                "min_loss_action": self.min_loss_action,
                "rows": [r.to_dict() for r in self.rows],
                "note": "Expected loss is computed over PERMITTED actions ONLY. "
                        "min_loss_action may be highlighted but can NEVER override "
                        "the Phase-9 hard gates or resurrect a blocked action."}


def compute_expected_loss_report(result: DispositionResult, inp: EconomicInputs,
                                  risk_input: RiskInput) -> ExpectedLossReport:
    permitted = derive_permitted_actions(result)
    risk = risk_input.estimate(result)
    rows = tuple(compute_action_economics(a, inp, risk, permitted=True)
                 for a in permitted)
    min_action = min(rows, key=lambda r: r.expected_loss_currency).action if rows else None
    return ExpectedLossReport(rows, min_action, permitted)


# ── deterministic discrete-outcome Value of Information ─────────────────────
@dataclass(frozen=True)
class VOIBin:
    name: str
    probability: float            # prior probability of landing in this bin
    posterior_p_bad: float        # risk proxy AFTER observing this bin
    actions_available: Tuple[str, ...]
    min_loss_action: str
    min_loss_currency: Currency

    def to_dict(self) -> dict:
        return {"name": self.name, "probability": self.probability,
                "posterior_p_bad_PROXY": self.posterior_p_bad,
                "actions_available": list(self.actions_available),
                "min_loss_action": self.min_loss_action,
                "min_loss_currency": self.min_loss_currency}


@dataclass(frozen=True)
class VOIResult:
    voi_currency: Currency
    el_min_now_currency: Currency
    expected_el_post_sample_currency: Currency
    sample_cost_currency: Currency
    applicable: bool              # False if sample too late / cannot change action
    recommend_sample: bool
    min_voi_threshold_currency: Currency
    bins: Tuple[VOIBin, ...]
    reason: str
    provenance: Provenance = Provenance.SIMULATED
    voi_model_version: str = VOI_MODEL_VERSION

    def to_dict(self) -> dict:
        return {"voi_currency": self.voi_currency,
                "el_min_now_currency": self.el_min_now_currency,
                "expected_el_post_sample_currency": self.expected_el_post_sample_currency,
                "sample_cost_currency": self.sample_cost_currency,
                "applicable": self.applicable,
                "recommend_sample": self.recommend_sample,
                "min_voi_threshold_currency": self.min_voi_threshold_currency,
                "bins": [b.to_dict() for b in self.bins], "reason": self.reason,
                "provenance": self.provenance.value,
                "voi_model_version": self.voi_model_version,
                "note": "Deterministic discrete-outcome VOI approximation "
                        "(SIMULATED). Not a validated information value."}


# ILLUSTRATIVE: a sample is assumed to be a near-perfect quality readout. The
# residuals keep the posterior honest (never collapses to exactly 0/1).
GOOD_POSTERIOR_P_BAD = 0.02
BAD_POSTERIOR_P_BAD = 0.98


def _min_el(actions: Tuple[str, ...], inp: EconomicInputs,
            risk: RiskEstimate) -> Tuple[str, Currency]:
    best = None
    for a in actions:
        el = compute_action_economics(a, inp, risk, permitted=True).expected_loss_currency
        if best is None or el < best[1]:
            best = (a, el)
    return best


def compute_voi(result: DispositionResult, inp: EconomicInputs,
                risk_input: RiskInput,
                min_voi_threshold: Currency = DEFAULT_MIN_VOI_CURRENCY) -> VOIResult:
    """VOI = min current EL - E[min post-sample EL] - sample cost.

    Transparent 2-bin discrete-outcome model. A sample can resolve the quality
    (candidacy) uncertainty but can NEVER unblock a hard gate — so if PRIME is
    hard-gate blocked, or already permitted, or the result arrives after the
    decision horizon, sampling cannot change the permissible action and VOI is
    not applicable.
    """
    sc = inp.scenario
    risk = risk_input.estimate(result)
    permitted_now = derive_permitted_actions(result)
    hard_fail = any((not g.passed) and g.severity == Severity.BLOCK
                    for g in result.gates)
    # VOI compares taking the sample against the best action WITHOUT sampling,
    # so SAMPLE itself is excluded from the "act now" baseline.
    now_actions = tuple(a for a in permitted_now if a != SAMPLE_NOW) or (ABSTAIN,)
    el_min_now = _min_el(now_actions, inp, risk)[1]
    sample_cost = float(sc.sample_cost) + float(sc.workflow_cost)

    too_late = inp.sample_latency_min > inp.decision_horizon_min
    prime_already = PRIME_RELEASE_CANDIDATE in permitted_now
    # sampling only helps if PRIME is reachable (no hard block) but not yet permitted
    can_change_action = (not hard_fail) and (not prime_already)

    if hard_fail:
        reason = "hard gate forces ABSTAIN — sampling cannot unblock it"
    elif too_late:
        reason = "sample result arrives after the decision horizon"
    elif not can_change_action:
        reason = "sampling cannot change the permissible action set"
    else:
        reason = "sample can resolve quality uncertainty and unlock PRIME"

    applicable = (not hard_fail) and (not too_late) and can_change_action

    # post-sample action universes (SAMPLE itself never available after sampling)
    non_prime = tuple(a for a in (HOLD, ABSTAIN) if a in permitted_now or True)
    good_actions = (PRIME_RELEASE_CANDIDATE, HOLD, ABSTAIN) if can_change_action \
        else tuple(a for a in permitted_now if a != SAMPLE_NOW)
    bad_actions = non_prime

    good_risk = RiskEstimate(GOOD_POSTERIOR_P_BAD, "post_sample_good",
                             Provenance.SIMULATED, "assumed near-perfect lab readout")
    bad_risk = RiskEstimate(BAD_POSTERIOR_P_BAD, "post_sample_bad",
                            Provenance.SIMULATED, "assumed near-perfect lab readout")
    g_act, g_el = _min_el(good_actions, inp, good_risk)
    b_act, b_el = _min_el(bad_actions, inp, bad_risk)
    bins = (
        VOIBin("GOOD", risk.p_good, GOOD_POSTERIOR_P_BAD, good_actions, g_act, g_el),
        VOIBin("BAD", risk.p_bad, BAD_POSTERIOR_P_BAD, bad_actions, b_act, b_el),
    )
    expected_post = risk.p_good * g_el + risk.p_bad * b_el
    voi = el_min_now - expected_post - sample_cost if applicable else 0.0

    operationally_available = (result.sample_eligibility is not None
                               and result.sample_eligibility.eligible)
    recommend = bool(applicable and operationally_available
                     and voi > min_voi_threshold)
    return VOIResult(voi, el_min_now, expected_post, sample_cost, applicable,
                     recommend, float(min_voi_threshold), bins, reason)


# ── realized vs counterfactual value (kept strictly separate) ───────────────
@dataclass(frozen=True)
class ValueSplit:
    """REALIZED = value of the route the episode ACTUALLY took (observed).
    COUNTERFACTUAL = value under a hypothetical policy (e.g., had it primed).
    Counterfactual value is NEVER presented as observed savings."""
    realized_value_currency: Currency
    counterfactual_prime_value_currency: Currency
    counterfactual_opportunity_currency: Currency
    avoided_loss_currency: Optional[Currency]   # only when ground truth supports it
    realized_good: Optional[bool]
    note: str = ("Realized is observed; counterfactual is hypothetical. "
                 "avoided_loss is populated ONLY where the synthetic ground "
                 "truth supports it — never as a measured HMEL saving.")

    def to_dict(self) -> dict:
        return {"realized_value_currency": self.realized_value_currency,
                "counterfactual_prime_value_currency": self.counterfactual_prime_value_currency,
                "counterfactual_opportunity_currency": self.counterfactual_opportunity_currency,
                "avoided_loss_currency": self.avoided_loss_currency,
                "realized_good": self.realized_good, "note": self.note}


def compute_value_split(inp: EconomicInputs,
                        realized_good: Optional[bool] = None) -> ValueSplit:
    realized = inp.mass_tonnes * inp.actual_route_value_per_tonne
    cf_prime = inp.recoverable_mass_tonnes * inp.prime_value_per_tonne
    cf_opp = inp.recoverable_mass_tonnes * inp.spread_per_tonne
    avoided = cf_opp if realized_good is True else None
    return ValueSplit(realized, cf_prime, cf_opp, avoided, realized_good)


# ── annual scale-up: a SCENARIO function, never a hard-coded headline ───────
@dataclass(frozen=True)
class AnnualScaleUp:
    eligible_transitions_per_year: float
    validated_episode_value_currency: Currency
    availability: float
    adoption: float
    annual_value_currency: Currency
    scenario: str
    provenance: Provenance = Provenance.SIMULATED

    def to_dict(self) -> dict:
        return {"eligible_transitions_per_year": self.eligible_transitions_per_year,
                "validated_episode_value_currency": self.validated_episode_value_currency,
                "availability": self.availability, "adoption": self.adoption,
                "annual_value_currency": self.annual_value_currency,
                "scenario": self.scenario, "provenance": self.provenance.value,
                "note": "SCENARIO calculation only. No fixed annual savings is "
                        "claimed; every factor is an explicit, variable input."}


def scale_up_annual(validated_episode_value_currency: Currency,
                    eligible_transitions_per_year: float,
                    availability: float, adoption: float,
                    scenario: str = DEFAULT_SCENARIO) -> AnnualScaleUp:
    for nm, v in (("availability", availability), ("adoption", adoption)):
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"{nm} must be in [0,1], got {v}")
    annual = (eligible_transitions_per_year * validated_episode_value_currency
              * availability * adoption)
    return AnnualScaleUp(eligible_transitions_per_year,
                         validated_episode_value_currency, availability,
                         adoption, annual, scenario)


# ── machine-readable economic ledger + top-level engine ─────────────────────
@dataclass(frozen=True)
class EconomicResult:
    event_id: str
    decision_id: str
    phase9_action: str              # authoritative action — economics NEVER change it
    permitted_actions: Tuple[str, ...]
    economic_preferred_action: Optional[str]   # advisory min-loss PERMITTED action
    expected_loss: ExpectedLossReport
    voi: VOIResult
    value_split: ValueSplit
    inputs: EconomicInputs
    versions: Dict[str, str]
    provenance: Provenance = Provenance.SIMULATED

    def to_ledger(self) -> dict:
        """Flat, auditable record: every number traces to an input + formula."""
        chosen = self.expected_loss.get(self.phase9_action)
        return {
            "event_id": self.event_id, "decision_id": self.decision_id,
            "scenario": self.inputs.scenario.name,
            "phase9_action": self.phase9_action,
            "permitted_actions": list(self.permitted_actions),
            "economic_preferred_action_ADVISORY": self.economic_preferred_action,
            "mass_tonnes": self.inputs.mass_tonnes,
            "recoverable_mass_tonnes": self.inputs.recoverable_mass_tonnes,
            "prime_value_per_tonne": self.inputs.prime_value_per_tonne,
            "actual_route_value_per_tonne": self.inputs.actual_route_value_per_tonne,
            "spread_per_tonne": self.inputs.spread_per_tonne,
            "sample_cost_currency": float(self.inputs.scenario.sample_cost),
            "workflow_cost_currency": float(self.inputs.scenario.workflow_cost),
            "false_prime_exposure_currency": (chosen.false_prime_exposure_currency
                                              if chosen else None),
            "false_hold_exposure_currency": (chosen.false_hold_exposure_currency
                                             if chosen else None),
            "expected_loss_chosen_currency": (chosen.expected_loss_currency
                                              if chosen else None),
            "expected_loss_table": self.expected_loss.to_dict(),
            "voi": self.voi.to_dict(),
            "realized_value_currency": self.value_split.realized_value_currency,
            "counterfactual_opportunity_currency":
                self.value_split.counterfactual_opportunity_currency,
            "value_split": self.value_split.to_dict(),
            "versions": dict(self.versions),
            "provenance": self.provenance.value,
            "note": "SIMULATED/ILLUSTRATIVE economics. Phase-9 hard gates are "
                    "authoritative; economics rank only PERMITTED actions and "
                    "never resurrect a blocked action.",
        }

    def to_dict(self) -> dict:
        return self.to_ledger()


def evaluate_economics(result: DispositionResult, inp: EconomicInputs,
                       risk_input: Optional[RiskInput] = None,
                       min_voi_threshold: Currency = DEFAULT_MIN_VOI_CURRENCY,
                       realized_good: Optional[bool] = None) -> EconomicResult:
    """Pure economic evaluation BEHIND the Phase-9 gates. Reads a finished
    DispositionResult; never feeds back into permission."""
    risk_input = risk_input or IntervalDerivedRisk()
    report = compute_expected_loss_report(result, inp, risk_input)
    voi = compute_voi(result, inp, risk_input, min_voi_threshold)
    value_split = compute_value_split(inp, realized_good)
    # advisory preference is the cheapest PERMITTED action; it can never differ
    # from the permitted set, so it can never resurrect a blocked action.
    preferred = report.min_loss_action
    versions = {"economics": ECONOMICS_VERSION, "cost_model": COST_MODEL_VERSION,
                "voi_model": VOI_MODEL_VERSION, "policy": POLICY.version,
                "disposition": result.disposition_version,
                "scenario": inp.scenario.name}
    return EconomicResult(inp.event_id, inp.decision_id, result.action,
                          report.permitted_actions, preferred, report, voi,
                          value_split, inp, versions)
