"""Phase 9 — PrimePath DISPOSITION DECISION ENGINE (pure, deterministic).

Given the full evidence bundle (quality prediction + calibrated interval,
material-identity eligibility, sensor-health, OOD/applicability, assurance,
specification, dwell, policy, approval path and an injected cost interface),
this engine answers ONE question:

    "What action is currently PERMITTED?"

from the FROZEN action vocabulary:

    HOLD / FOLLOW CURRENT ROUTING
    SAMPLE NOW
    PRIME-RELEASE CANDIDATE
    ABSTAIN / FOLLOW SOP

The engine is ADVISORY ONLY. It does NOT certify material, bypass laboratory
approval, write DCS/APC setpoints, actuate valves, replace HMEL SOP, or make a
commercial release. PRIME-RELEASE CANDIDATE is a *candidate* that ALWAYS
requires human / quality authorization — never "prime released / certified /
approved / safe".

Design boundaries honoured here:
  * HARD GATES are evaluated BEFORE any action is selected; a failed hard gate
    forces ABSTAIN (never a "best guess" through a block).
  * Gate evaluation, candidacy/eligibility evaluation and action policy are kept
    SEPARATE so policy can be audited/changed without rewriting the engine.
  * Economics are an INJECTED, clearly-labelled SIMULATED/ILLUSTRATIVE interface
    (the full cost model, scenario ledger and VOI optimiser belong to Phase 10).
  * The Phase-6 `prob_bad` is treated as PROVISIONAL/ILLUSTRATIVE only; prime
    candidacy relies on the calibrated interval vs specification, material
    identity, health/applicability, dwell and approval — never on `prob_bad`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum
from typing import Optional, Protocol, Sequence

from . import config as C
from .applicability import ApplicabilityResult, ApplicabilityState
from .assurance import AssuranceResult
from .config import GradeSpec, Policy, POLICY
from .health import HealthState, SensorHealthReport
from .material_service import MaterialEligibilityResult, MappingQuality
from .provenance import Provenance
from .schemas import ACTIONS, DecisionSnapshot, PredictionBundle, TransitionEvent

DISPOSITION_VERSION = "disposition-v1"

# Actions (mirrors schemas.ACTIONS; named here for readability) ──────────────
HOLD = "HOLD"
SAMPLE_NOW = "SAMPLE_NOW"
PRIME_RELEASE_CANDIDATE = "PRIME_RELEASE_CANDIDATE"
ABSTAIN = "ABSTAIN"
assert {HOLD, SAMPLE_NOW, PRIME_RELEASE_CANDIDATE, ABSTAIN} == set(ACTIONS)

# "FOLLOW SOP" is the human-facing fallback label; as a vocabulary action it
# maps to ABSTAIN (defer to the Standard Operating Procedure / QC lab).
FALLBACK_FOLLOW_SOP = ABSTAIN

# ── Reason codes (machine- and human-readable) ───────────────────────────────
# PRIME candidacy (all must hold)
PRIME_INTERVAL_PASS = "PRIME_INTERVAL_PASS"
PRIME_DWELL_PASS = "PRIME_DWELL_PASS"
PRIME_MATERIAL_SUPPORTED = "PRIME_MATERIAL_SUPPORTED"
PRIME_HEALTH_PASS = "PRIME_HEALTH_PASS"
PRIME_APPLICABILITY_PASS = "PRIME_APPLICABILITY_PASS"
PRIME_APPROVAL_PATH_PASS = "PRIME_APPROVAL_PATH_PASS"
PRIME_CANDIDATE_REQUIRES_AUTHORIZATION = "PRIME_CANDIDATE_REQUIRES_AUTHORIZATION"
# HOLD
HOLD_INTERVAL_CROSSES_SPEC = "HOLD_INTERVAL_CROSSES_SPEC"
HOLD_DWELL_INCOMPLETE = "HOLD_DWELL_INCOMPLETE"
HOLD_EVIDENCE_INSUFFICIENT = "HOLD_EVIDENCE_INSUFFICIENT"
HOLD_MATERIAL_SUPPORT_INCOMPLETE = "HOLD_MATERIAL_SUPPORT_INCOMPLETE"
HOLD_HEALTH_DEGRADED = "HOLD_HEALTH_DEGRADED"
# SAMPLE NOW
SAMPLE_ELIGIBLE = "SAMPLE_ELIGIBLE"
SAMPLE_INFORMATION_MISSING = "SAMPLE_INFORMATION_MISSING"
SAMPLE_RESULT_LATENCY_TOO_LONG = "SAMPLE_RESULT_LATENCY_TOO_LONG"
SAMPLE_UNAVAILABLE = "SAMPLE_UNAVAILABLE"
# ABSTAIN (hard gate failures)
ABSTAIN_SENSOR_HEALTH = "ABSTAIN_SENSOR_HEALTH"
ABSTAIN_OOD = "ABSTAIN_OOD"
ABSTAIN_MATERIAL_MAPPING = "ABSTAIN_MATERIAL_MAPPING"
ABSTAIN_ROUTE_AMBIGUOUS = "ABSTAIN_ROUTE_AMBIGUOUS"
ABSTAIN_NO_CALIBRATION = "ABSTAIN_NO_CALIBRATION"
ABSTAIN_NO_PREDICTION = "ABSTAIN_NO_PREDICTION"
ABSTAIN_NO_SPECIFICATION = "ABSTAIN_NO_SPECIFICATION"
ABSTAIN_TIMESTAMP_ALIGNMENT = "ABSTAIN_TIMESTAMP_ALIGNMENT"
ABSTAIN_INVALID_TRANSITION = "ABSTAIN_INVALID_TRANSITION"
ABSTAIN_MODEL_VERSION = "ABSTAIN_MODEL_VERSION"
ABSTAIN_MAPPING_UNCERTAINTY = "ABSTAIN_MAPPING_UNCERTAINTY"
ABSTAIN_NO_APPROVAL_PATH = "ABSTAIN_NO_APPROVAL_PATH"
ABSTAIN_REQUIRED_INPUT = "ABSTAIN_REQUIRED_INPUT"
# Expiry / staleness
RECOMMENDATION_EXPIRED = "RECOMMENDATION_EXPIRED"


# ── Gate severity ────────────────────────────────────────────────────────────
class Severity(IntEnum):
    INFO = 0        # informational; never changes the action
    CANDIDACY = 1   # blocks PRIME candidacy only (-> HOLD / SAMPLE), not ABSTAIN
    BLOCK = 3       # hard gate: failure FORCES ABSTAIN / FOLLOW SOP


@dataclass(frozen=True)
class DispositionGate:
    """One checked condition in the audit table (mirrors the Phase-7 contract)."""
    gate_id: str
    passed: bool
    severity: Severity
    reason_code: str
    detail: str = ""
    provenance: Provenance = Provenance.SIMULATED
    version: str = DISPOSITION_VERSION

    @property
    def forces_abstain(self) -> bool:
        return (not self.passed) and self.severity is Severity.BLOCK

    @property
    def blocks_prime(self) -> bool:
        return (not self.passed) and self.severity in (Severity.BLOCK, Severity.CANDIDACY)

    def to_dict(self) -> dict:
        return {"gate_id": self.gate_id, "passed": self.passed,
                "severity": int(self.severity), "severity_name": self.severity.name,
                "reason_code": self.reason_code, "detail": self.detail,
                "provenance": self.provenance.value, "version": self.version}


# ── Dwell status (as-of causal) ──────────────────────────────────────────────
@dataclass(frozen=True)
class DwellStatus:
    """Whether the ONLINE MFI has stayed continuously in the target spec band for
    the grade's configured dwell, as-of the decision time (uses only obs <= t)."""
    required_min: float
    elapsed_min: float
    satisfied: bool
    in_spec_now: bool
    as_of: datetime
    provenance: Provenance = Provenance.SIMULATED

    def to_dict(self) -> dict:
        return {"required_min": self.required_min, "elapsed_min": self.elapsed_min,
                "satisfied": self.satisfied, "in_spec_now": self.in_spec_now,
                "as_of": self.as_of.isoformat(), "provenance": self.provenance.value}


def compute_dwell_status(event: TransitionEvent, decision_time: datetime,
                         spec: GradeSpec) -> DwellStatus:
    """As-of dwell: length of the current continuous in-spec run on MFI_online
    ending at the latest observation at/before `decision_time`. Causal: no
    observation after `decision_time` is consulted."""
    obs = sorted((o for o in event.series if o.tag == "MFI_online"
                  and o.timestamp <= decision_time), key=lambda o: o.timestamp)
    if not obs:
        return DwellStatus(spec.dwell_min, 0.0, False, False, decision_time)
    run_start: Optional[datetime] = None
    run_end: Optional[datetime] = None
    for o in obs:
        if spec.in_spec(o.value):
            run_start = run_start or o.timestamp
            run_end = o.timestamp
        else:
            run_start = None
            run_end = None
    in_spec_now = spec.in_spec(obs[-1].value)
    elapsed = 0.0 if run_start is None else (run_end - run_start).total_seconds() / 60.0
    satisfied = in_spec_now and elapsed >= spec.dwell_min
    return DwellStatus(spec.dwell_min, elapsed, satisfied, in_spec_now, decision_time)


# ── Sample eligibility (NO VOI optimiser here — Phase 10) ────────────────────
@dataclass(frozen=True)
class SampleEligibility:
    """Whether a confirmatory lab sample is operationally an option NOW. The
    VALUE of sampling (VOI) is deliberately NOT computed here (Phase 10)."""
    sample_available: bool
    sample_cost_available: bool
    expected_result_latency_min: float
    decision_horizon_min: float
    current_decision_uncertainty: float   # interval width / spec-band width
    eligible: bool
    reason_codes: tuple[str, ...]
    provenance: Provenance = Provenance.SIMULATED

    def to_dict(self) -> dict:
        return {"sample_available": self.sample_available,
                "sample_cost_available": self.sample_cost_available,
                "expected_result_latency_min": self.expected_result_latency_min,
                "decision_horizon_min": self.decision_horizon_min,
                "current_decision_uncertainty": self.current_decision_uncertainty,
                "eligible": self.eligible, "reason_codes": list(self.reason_codes),
                "provenance": self.provenance.value}


# ── Expected-loss interface (INJECTED, SIMULATED/ILLUSTRATIVE) ───────────────
# The full cost model, scenario ledger and VOI optimiser belong to Phase 10.
# Here we only define the INTERFACE and a clearly-labelled illustrative provider.
# These numbers DO NOT drive the Phase-9 action selection (that is gate/policy
# driven); they are reported alongside it for Phase-10 to consume.
COST_MODEL_VERSION = "illustrative-cost-v0"


@dataclass(frozen=True)
class ExpectedLossRow:
    action: str
    expected_loss: float
    cost_model_version: str
    scenario: str
    inputs_used: dict
    provenance: Provenance = Provenance.SIMULATED

    def to_dict(self) -> dict:
        return {"action": self.action, "expected_loss": self.expected_loss,
                "cost_model_version": self.cost_model_version, "scenario": self.scenario,
                "inputs_used": dict(self.inputs_used), "provenance": self.provenance.value}


@dataclass(frozen=True)
class ExpectedLossTable:
    rows: tuple[ExpectedLossRow, ...]

    def get(self, action: str) -> Optional[ExpectedLossRow]:
        for r in self.rows:
            if r.action == action:
                return r
        return None

    def as_action_map(self) -> dict[str, float]:
        return {r.action: r.expected_loss for r in self.rows}

    def to_dict(self) -> dict:
        return {"rows": [r.to_dict() for r in self.rows],
                "cost_model_version": COST_MODEL_VERSION,
                "provenance": Provenance.SIMULATED.value,
                "note": "SIMULATED/ILLUSTRATIVE — not a validated economic result "
                        "and NOT used to select the Phase-9 action."}


class CostProvider(Protocol):
    """Injected economics. Pure: same evidence -> same table."""
    def expected_losses(self, evidence: "DispositionEvidence") -> ExpectedLossTable: ...


@dataclass(frozen=True)
class IllustrativeCostProvider:
    """A deterministic, clearly-labelled SIMULATED cost provider. Uses the
    provisional p(bad) ONLY as an illustrative weight — never as a validated
    probability, and never to decide the action."""
    scenario_id: str = C.DEFAULT_SCENARIO

    def expected_losses(self, evidence: "DispositionEvidence") -> ExpectedLossTable:
        sc = C.get_scenario(self.scenario_id)
        pb = evidence.prediction.prob_bad if evidence.prediction is not None else 0.5
        pb = min(1.0, max(0.0, float(pb)))  # provisional/illustrative only
        pg = 1.0 - pb
        opportunity = max(0.0, sc.prime_price - sc.downgrade_price)
        used = {"scenario": sc.name, "provisional_prob_bad_ILLUSTRATIVE": pb,
                "prime_price": sc.prime_price, "downgrade_price": sc.downgrade_price,
                "false_prime_consequence": sc.false_prime_consequence,
                "sample_cost": sc.sample_cost, "workflow_cost": sc.workflow_cost}
        rows = (
            ExpectedLossRow(PRIME_RELEASE_CANDIDATE, sc.false_prime_consequence * pb,
                            COST_MODEL_VERSION, sc.name, used),
            ExpectedLossRow(HOLD, opportunity * pg, COST_MODEL_VERSION, sc.name, used),
            ExpectedLossRow(SAMPLE_NOW, sc.sample_cost + sc.workflow_cost,
                            COST_MODEL_VERSION, sc.name, used),
            ExpectedLossRow(ABSTAIN, sc.workflow_cost, COST_MODEL_VERSION, sc.name, used),
        )
        return ExpectedLossTable(rows)


# ── Approval path configuration ──────────────────────────────────────────────
@dataclass(frozen=True)
class ApprovalConfig:
    """Who must authorize a PRIME-RELEASE CANDIDATE. A configured path is a HARD
    requirement; actual authorization is NEVER performed by this engine."""
    required_role: str = C.POLICY.required_approver
    authorized_by: Optional[str] = None       # engine never sets this
    authorized_at: Optional[datetime] = None

    @property
    def path_configured(self) -> bool:
        return bool(self.required_role and self.required_role.strip())

    def to_dict(self) -> dict:
        return {"required_role": self.required_role, "authorized_by": self.authorized_by,
                "authorized_at": self.authorized_at.isoformat() if self.authorized_at else None,
                "path_configured": self.path_configured}


# ── Disposition policy (engine knobs; wraps the frozen config.Policy) ────────
@dataclass(frozen=True)
class DispositionPolicy:
    """Engine-level policy. Thresholds are POLICY/ASSUMPTION values, NOT HMEL
    operating limits. The base `config.Policy` is reused verbatim; engine-only
    knobs (how to treat an ambiguous route, max mapping uncertainty) are added
    here so the frozen config schema is not edited."""
    base: Policy = field(default_factory=lambda: C.POLICY)
    # On an AMBIGUOUS material route the SAFE default is ABSTAIN (never silently
    # pick a destination). May be set to HOLD by explicit, documented policy.
    ambiguous_route_action: str = ABSTAIN
    # Require WELL_SUPPORTED mapping for a PRIME candidate; PARTIALLY_SUPPORTED
    # is usable for routing decisions but not for a prime candidate.
    require_well_supported_for_prime: bool = True
    # Max residence/mapping uncertainty (minutes) tolerated before ABSTAIN.
    max_residence_uncertainty_min: float = 180.0
    # Expected model/calibration versions; if set, a mismatch forces ABSTAIN.
    expected_model_version: Optional[str] = None
    expected_calibration_version: Optional[str] = None

    def __post_init__(self):
        if self.ambiguous_route_action not in (ABSTAIN, HOLD):
            raise ValueError("ambiguous_route_action must be ABSTAIN or HOLD")
        if self.max_residence_uncertainty_min < 0:
            raise ValueError("max_residence_uncertainty_min must be >= 0")

    @property
    def version(self) -> str:
        return self.base.version

    def to_dict(self) -> dict:
        return {"base_policy_version": self.base.version,
                "nominal_coverage": self.base.nominal_coverage,
                "decision_horizon_min": self.base.decision_horizon_min,
                "sample_result_latency_min": self.base.sample_result_latency_min,
                "recommendation_expiry_min": self.base.recommendation_expiry_min,
                "required_approver": self.base.required_approver,
                "ambiguous_route_action": self.ambiguous_route_action,
                "require_well_supported_for_prime": self.require_well_supported_for_prime,
                "max_residence_uncertainty_min": self.max_residence_uncertainty_min,
                "expected_model_version": self.expected_model_version,
                "expected_calibration_version": self.expected_calibration_version,
                "disposition_version": DISPOSITION_VERSION,
                "provenance": "ASSUMPTION — POLICY values, not HMEL operating limits"}


DEFAULT_DISPOSITION_POLICY = DispositionPolicy()


# ── Evidence bundle (the ONLY input the engine reads; it queries no raw data) ─
@dataclass(frozen=True)
class DispositionEvidence:
    """The complete, pre-assembled evidence the engine consumes. The engine does
    NOT read raw plant data, re-run models, or re-map material — every input is
    supplied here so the decision is a pure function of this bundle + policy."""
    event: TransitionEvent
    decision_time: datetime
    spec: Optional[GradeSpec]
    prediction: Optional[PredictionBundle]
    material_eligibility: Optional[MaterialEligibilityResult]
    health_report: Optional[SensorHealthReport]
    applicability_result: Optional[ApplicabilityResult]
    assurance_result: Optional[AssuranceResult] = None
    dwell_status: Optional[DwellStatus] = None
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    sample_available: bool = False
    sample_cost_available: bool = True
    versions: dict = field(default_factory=dict)
    # Optional re-evaluation clock for staleness; defaults to decision_time.
    current_time: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {"event_id": self.event.event_id,
                "decision_time": self.decision_time.isoformat(),
                "grade_from": self.event.grade_from, "grade_to": self.event.grade_to,
                "has_prediction": self.prediction is not None,
                "has_spec": self.spec is not None,
                "has_material_eligibility": self.material_eligibility is not None,
                "has_health": self.health_report is not None,
                "has_applicability": self.applicability_result is not None,
                "sample_available": self.sample_available,
                "approval": self.approval.to_dict(), "versions": dict(self.versions)}


# ── Disposition result (rich; produces a fully-populated DecisionSnapshot) ───
@dataclass(frozen=True)
class DispositionResult:
    event_id: str
    decision_time: datetime
    action: str
    fallback_action: str
    gates: tuple[DispositionGate, ...]
    reason_codes: tuple[str, ...]
    expected_loss_table: ExpectedLossTable
    sample_eligibility: SampleEligibility
    # evidence summaries (for the audit record)
    prediction_summary: dict
    interval: Optional[tuple[float, float]]
    spec_band: Optional[tuple[float, float]]
    dwell_status: Optional[DwellStatus]
    material_mapping_quality: Optional[str]
    material_route_known: Optional[bool]
    health_state: Optional[str]
    applicability_state: Optional[str]
    assurance_state: Optional[str]
    approver_role: str
    expiry: datetime
    expired: bool
    versions: dict
    note: str
    provenance: Provenance = Provenance.SIMULATED
    disposition_version: str = DISPOSITION_VERSION

    def to_snapshot(self) -> DecisionSnapshot:
        """Project onto the frozen Phase-1 DecisionSnapshot, fully populated."""
        return DecisionSnapshot(
            event_id=self.event_id,
            decision_time=self.decision_time,
            action=self.action,
            expected_loss=self.expected_loss_table.as_action_map(),
            reason_codes=tuple(self.reason_codes),
            voi=0.0,  # provisional placeholder — VOI optimiser is Phase 10
            expiry=self.expiry,
            approver_role=self.approver_role,
            fallback_action=self.fallback_action,
            versions=dict(self.versions),
            authorized_by=None,       # engine NEVER authorizes
            authorized_at=None,
            provenance=self.provenance,
        )

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "decision_time": self.decision_time.isoformat(),
            "action": self.action,
            "fallback_action": self.fallback_action,
            "reason_codes": list(self.reason_codes),
            "gates": [g.to_dict() for g in self.gates],
            "expected_loss_table": self.expected_loss_table.to_dict(),
            "sample_eligibility": self.sample_eligibility.to_dict(),
            "prediction_summary": self.prediction_summary,
            "interval": list(self.interval) if self.interval else None,
            "spec_band": list(self.spec_band) if self.spec_band else None,
            "dwell_status": self.dwell_status.to_dict() if self.dwell_status else None,
            "material_mapping_quality": self.material_mapping_quality,
            "material_route_known": self.material_route_known,
            "health_state": self.health_state,
            "applicability_state": self.applicability_state,
            "assurance_state": self.assurance_state,
            "approver_role": self.approver_role,
            "expiry": self.expiry.isoformat(),
            "expired": self.expired,
            "versions": dict(self.versions),
            "note": self.note,
            "provenance": self.provenance.value,
            "disposition_version": self.disposition_version,
        }


# ── Internal helpers ─────────────────────────────────────────────────────────
def _finite(x) -> bool:
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return False
    return xf == xf and xf not in (float("inf"), float("-inf"))


def _G(gate_id, passed, severity, reason, detail=""):
    return DispositionGate(gate_id, passed, severity, reason, detail)


def evaluate_hard_gates(ev: DispositionEvidence,
                        policy: DispositionPolicy) -> list[DispositionGate]:
    """HARD gates (Severity.BLOCK) — evaluated BEFORE any action is chosen.
    A single failure forces ABSTAIN / FOLLOW SOP. Returned in a stable order so
    the first failing gate gives a deterministic primary reason."""
    g: list[DispositionGate] = []
    S = Severity.BLOCK

    # A. valid transition
    valid_tx = (ev.event is not None and ev.event.grade_from != ev.event.grade_to
                and bool(ev.event.series))
    g.append(_G("valid_transition", valid_tx, S, ABSTAIN_INVALID_TRANSITION,
                "" if valid_tx else "missing/degenerate transition event"))

    # B. timestamp alignment (tz-aware, as-of >= started_at)
    t = ev.decision_time
    aligned = (t is not None and t.tzinfo is not None and ev.event is not None
               and t >= ev.event.started_at)
    g.append(_G("timestamp_alignment", aligned, S, ABSTAIN_TIMESTAMP_ALIGNMENT,
                "" if aligned else "decision_time not aligned to event timeline"))

    # C. prediction available
    pred = ev.prediction
    has_pred = pred is not None and _finite(getattr(pred, "point_mfi", None))
    g.append(_G("prediction_available", has_pred, S, ABSTAIN_NO_PREDICTION,
                "" if has_pred else "no finite quality prediction"))

    # D. calibrated interval available
    cal_ok = (has_pred and _finite(pred.lower_mfi) and _finite(pred.upper_mfi)
              and pred.lower_mfi <= pred.upper_mfi and bool(pred.calibration_version))
    g.append(_G("calibrated_interval", cal_ok, S, ABSTAIN_NO_CALIBRATION,
                "" if cal_ok else "no calibrated prediction interval"))

    # E. material window available
    me = ev.material_eligibility
    win_ok = me is not None and me.material_window_available
    g.append(_G("material_window_available", win_ok, S, ABSTAIN_MATERIAL_MAPPING,
                "" if win_ok else "material production window unavailable"))

    # F. material mapping not blocking (support sufficient / mapping not UNAVAILABLE)
    supp_ok = me is not None and not me.is_blocking and \
        me.mapping_quality is not MappingQuality.UNAVAILABLE
    g.append(_G("material_support_sufficient", supp_ok, S, ABSTAIN_MATERIAL_MAPPING,
                "" if supp_ok else f"blocking material codes: "
                f"{list(me.blocking_reason_codes) if me else None}"))

    # G. route known / ambiguity handling (severity depends on policy)
    is_ambiguous = me is not None and me.mapping_quality is MappingQuality.AMBIGUOUS
    route_known = me is not None and me.route_known
    if is_ambiguous and policy.ambiguous_route_action == ABSTAIN:
        g.append(_G("route_known", False, Severity.BLOCK, ABSTAIN_ROUTE_AMBIGUOUS,
                    "ambiguous route; policy=ABSTAIN (never silently pick)"))
    elif is_ambiguous:  # policy == HOLD -> candidacy block, not abstain
        g.append(_G("route_known", False, Severity.CANDIDACY, HOLD_MATERIAL_SUPPORT_INCOMPLETE,
                    "ambiguous route; policy=HOLD"))
    else:
        g.append(_G("route_known", route_known, Severity.CANDIDACY,
                    PRIME_MATERIAL_SUPPORTED if route_known else HOLD_MATERIAL_SUPPORT_INCOMPLETE,
                    "" if route_known else "downstream route not resolved"))

    # H. critical sensor health (ABNORMAL/UNAVAILABLE force ABSTAIN; DEGRADED is candidacy)
    hs = ev.health_report.overall_state if ev.health_report is not None else HealthState.UNAVAILABLE
    health_hard_ok = hs in (HealthState.NORMAL, HealthState.DEGRADED)
    g.append(_G("sensor_health", health_hard_ok, S, ABSTAIN_SENSOR_HEALTH,
                f"health={hs.name}"))

    # I. applicability / OOD
    ap = ev.applicability_result.state if ev.applicability_result is not None \
        else ApplicabilityState.UNAVAILABLE
    appl_ok = ap is ApplicabilityState.NORMAL
    g.append(_G("applicability", appl_ok, S, ABSTAIN_OOD, f"applicability={ap.name}"))

    # J. specification available
    spec_ok = ev.spec is not None
    g.append(_G("specification_available", spec_ok, S, ABSTAIN_NO_SPECIFICATION,
                "" if spec_ok else "no commercial specification"))

    # K. residence / mapping uncertainty within policy
    ru = me.residence_uncertainty_min if me is not None else float("inf")
    unc_ok = me is not None and ru <= policy.max_residence_uncertainty_min
    g.append(_G("mapping_uncertainty", unc_ok, S, ABSTAIN_MAPPING_UNCERTAINTY,
                f"residence_uncertainty_min={ru}"))

    # L. model/calibration version match (only if an expected version is pinned)
    ver_ok = True
    if policy.expected_model_version is not None:
        ver_ok = has_pred and pred.model_version == policy.expected_model_version
    if ver_ok and policy.expected_calibration_version is not None:
        ver_ok = has_pred and pred.calibration_version == policy.expected_calibration_version
    g.append(_G("model_version", ver_ok, S, ABSTAIN_MODEL_VERSION,
                "" if ver_ok else "model/calibration version mismatch"))

    # M. approval path configured
    path_ok = ev.approval.path_configured
    g.append(_G("approval_path_configured", path_ok, S, ABSTAIN_NO_APPROVAL_PATH,
                "" if path_ok else "no approval path configured"))
    return g


def evaluate_prime_candidacy_gates(ev: DispositionEvidence,
                                   policy: DispositionPolicy) -> list[DispositionGate]:
    """CANDIDACY gates (Severity.CANDIDACY): all must pass for a PRIME candidate.
    A failure here never forces ABSTAIN — it steers to HOLD / SAMPLE NOW.
    (route_known is evaluated among the hard gates with candidacy severity.)"""
    g: list[DispositionGate] = []
    S = Severity.CANDIDACY

    # interval entirely within spec (point-in-spec is NOT sufficient)
    pred, spec = ev.prediction, ev.spec
    if pred is not None and spec is not None and _finite(pred.lower_mfi) and _finite(pred.upper_mfi):
        within = pred.lower_mfi >= spec.mfi_low and pred.upper_mfi <= spec.mfi_high
    else:
        within = False
    g.append(_G("interval_within_spec", within, S,
                PRIME_INTERVAL_PASS if within else HOLD_INTERVAL_CROSSES_SPEC,
                "" if within else "calibrated interval crosses a spec limit"))

    # dwell satisfied (as-of)
    dw = ev.dwell_status
    dwell_ok = dw is not None and dw.satisfied
    g.append(_G("dwell_satisfied", dwell_ok, S,
                PRIME_DWELL_PASS if dwell_ok else HOLD_DWELL_INCOMPLETE,
                "" if dwell_ok else "target-grade dwell not yet satisfied"))

    # health NORMAL for a confident prime (DEGRADED is usable but not prime)
    hs = ev.health_report.overall_state if ev.health_report is not None else HealthState.UNAVAILABLE
    health_normal = hs is HealthState.NORMAL
    g.append(_G("health_normal_for_prime", health_normal, S,
                PRIME_HEALTH_PASS if health_normal else HOLD_HEALTH_DEGRADED,
                f"health={hs.name}"))

    # applicability NORMAL (restated at candidacy level for the audit table)
    ap = ev.applicability_result.state if ev.applicability_result is not None \
        else ApplicabilityState.UNAVAILABLE
    appl_ok = ap is ApplicabilityState.NORMAL
    g.append(_G("applicability_for_prime", appl_ok, S,
                PRIME_APPLICABILITY_PASS if appl_ok else ABSTAIN_OOD, f"applicability={ap.name}"))

    # material WELL_SUPPORTED for a prime candidate
    me = ev.material_eligibility
    if policy.require_well_supported_for_prime:
        mat_ok = me is not None and me.mapping_quality is MappingQuality.WELL_SUPPORTED and me.route_known
    else:
        mat_ok = me is not None and me.route_known
    g.append(_G("material_well_supported", mat_ok, S,
                PRIME_MATERIAL_SUPPORTED if mat_ok else HOLD_MATERIAL_SUPPORT_INCOMPLETE,
                "" if mat_ok else f"mapping_quality="
                f"{me.mapping_quality.value if me else None}"))
    return g


def build_sample_eligibility(ev: DispositionEvidence,
                             policy: DispositionPolicy) -> SampleEligibility:
    """Is a confirmatory lab sample an operational option NOW? (No VOI here.)"""
    reasons: list[str] = []
    latency = policy.base.sample_result_latency_min
    horizon = policy.base.decision_horizon_min
    # decision uncertainty = interval width relative to the spec band width
    unc = 0.0
    pred, spec = ev.prediction, ev.spec
    if pred is not None and spec is not None and _finite(pred.lower_mfi) and _finite(pred.upper_mfi):
        band = max(1e-9, spec.mfi_high - spec.mfi_low)
        unc = max(0.0, (pred.upper_mfi - pred.lower_mfi) / band)
    latency_ok = latency <= horizon
    eligible = ev.sample_available and ev.sample_cost_available and latency_ok
    if not ev.sample_available:
        reasons.append(SAMPLE_UNAVAILABLE)
    if not ev.sample_cost_available:
        reasons.append(SAMPLE_INFORMATION_MISSING)
    if not latency_ok:
        reasons.append(SAMPLE_RESULT_LATENCY_TOO_LONG)
    if eligible:
        reasons.append(SAMPLE_ELIGIBLE)
    return SampleEligibility(ev.sample_available, ev.sample_cost_available, latency,
                             horizon, unc, eligible, tuple(reasons))


def evaluate_disposition(evidence: DispositionEvidence,
                         policy: DispositionPolicy = DEFAULT_DISPOSITION_POLICY,
                         cost_provider: Optional[CostProvider] = None) -> DispositionResult:
    """Pure, deterministic disposition decision. Same (evidence, policy,
    cost_provider) ALWAYS yields the same DispositionResult. HARD gates are
    evaluated BEFORE any action is selected; a failed hard gate forces ABSTAIN.

    Action precedence (gates/eligibility/policy kept separate):
      1. any hard gate fails          -> ABSTAIN  / FOLLOW SOP
      2. recommendation stale/expired -> FOLLOW SOP (recompute), never retained
      3. all prime candidacy gates pass -> PRIME-RELEASE CANDIDATE (needs auth)
      4. a sample can resolve the gap  -> SAMPLE NOW (eligibility only; no VOI)
      5. otherwise                     -> HOLD / FOLLOW CURRENT ROUTING
    """
    if cost_provider is None:
        cost_provider = IllustrativeCostProvider()
    ev = evidence

    # fill as-of dwell if the caller did not supply it
    if ev.dwell_status is None and ev.spec is not None and ev.event is not None:
        ev = _with_dwell(ev, compute_dwell_status(ev.event, ev.decision_time, ev.spec))

    hard = evaluate_hard_gates(ev, policy)
    cand = evaluate_prime_candidacy_gates(ev, policy)
    all_gates = tuple(hard + cand)
    sample_elig = build_sample_eligibility(ev, policy)
    loss_table = cost_provider.expected_losses(ev)

    # expiry / staleness
    expiry = ev.decision_time + timedelta(minutes=policy.base.recommendation_expiry_min)
    now = ev.current_time or ev.decision_time
    expired = now > expiry

    forcing = [g for g in hard if g.forces_abstain]
    prime_blockers = [g for g in all_gates if g.blocks_prime]
    approver_role = ev.approval.required_role or policy.base.required_approver

    if forcing:
        action = ABSTAIN
        reasons = tuple(dict.fromkeys(g.reason_code for g in forcing))
        note = ("ABSTAIN / FOLLOW SOP — a hard gate blocked disposition; the "
                "engine never 'best-guesses' through a block.")
    elif expired:
        action = FALLBACK_FOLLOW_SOP
        reasons = (RECOMMENDATION_EXPIRED,)
        note = ("Recommendation expired — fall back to SOP and RECOMPUTE; a stale "
                "disposition is never silently retained.")
    elif not prime_blockers:
        action = PRIME_RELEASE_CANDIDATE
        reasons = tuple(dict.fromkeys(
            [g.reason_code for g in cand if g.passed] + [PRIME_CANDIDATE_REQUIRES_AUTHORIZATION]))
        note = ("PRIME-RELEASE CANDIDATE — advisory only. NOT released/certified/"
                f"approved/safe. Requires authorization by: {approver_role}.")
    elif sample_elig.eligible:
        action = SAMPLE_NOW
        reasons = tuple(dict.fromkeys(
            [SAMPLE_ELIGIBLE] + [g.reason_code for g in prime_blockers]))
        note = ("SAMPLE NOW — a confirmatory lab sample can resolve the remaining "
                "uncertainty within the decision horizon (VOI deferred to Phase 10).")
    else:
        action = HOLD
        blockers = [g.reason_code for g in prime_blockers] or [HOLD_EVIDENCE_INSUFFICIENT]
        reasons = tuple(dict.fromkeys(blockers))
        note = "HOLD / FOLLOW CURRENT ROUTING — not yet a prime candidate."

    pred = ev.prediction
    pred_summary = {
        "point_mfi": pred.point_mfi if pred else None,
        "nominal_coverage": pred.nominal_coverage if pred else None,
        "model_version": pred.model_version if pred else None,
        "calibration_version": pred.calibration_version if pred else None,
        # p(bad) is PROVISIONAL/ILLUSTRATIVE — never a validated failure probability
        "prob_bad_PROVISIONAL": pred.prob_bad if pred else None,
        "prob_bad_note": "ILLUSTRATIVE/PROVISIONAL — not used for prime candidacy",
    }
    interval = (pred.lower_mfi, pred.upper_mfi) if pred and _finite(pred.lower_mfi) else None
    spec_band = (ev.spec.mfi_low, ev.spec.mfi_high) if ev.spec else None
    me = ev.material_eligibility

    versions = {"disposition": DISPOSITION_VERSION, "policy": policy.version,
                "cost_model": COST_MODEL_VERSION}
    if pred:
        versions["model"] = pred.model_version
        versions["calibration"] = pred.calibration_version
    if me:
        versions["material_service"] = me.service_version
    versions.update(ev.versions)

    return DispositionResult(
        event_id=ev.event.event_id if ev.event else "UNKNOWN",
        decision_time=ev.decision_time,
        action=action,
        fallback_action=FALLBACK_FOLLOW_SOP,
        gates=all_gates,
        reason_codes=reasons,
        expected_loss_table=loss_table,
        sample_eligibility=sample_elig,
        prediction_summary=pred_summary,
        interval=interval,
        spec_band=spec_band,
        dwell_status=ev.dwell_status,
        material_mapping_quality=me.mapping_quality.value if me else None,
        material_route_known=me.route_known if me else None,
        health_state=ev.health_report.overall_state.name if ev.health_report else None,
        applicability_state=ev.applicability_result.state.name if ev.applicability_result else None,
        assurance_state=ev.assurance_result.assurance_state.name if ev.assurance_result else None,
        approver_role=approver_role,
        expiry=expiry,
        expired=expired,
        versions=versions,
        note=note,
    )


def _with_dwell(ev: DispositionEvidence, dw: DwellStatus) -> DispositionEvidence:
    from dataclasses import replace
    return replace(ev, dwell_status=dw)







