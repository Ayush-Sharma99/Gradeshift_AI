"""Phase 7C — COMBINED ASSURANCE STATE + reusable HARD-GATE CONTRACT.

This module composes the THREE independent evidence layers without merging
them into a single scalar:
  * prediction availability (Phase 5/6 estimator produced a usable point)
  * sensor / data health      (Phase 7A)
  * model applicability / OOD (Phase 7B)

It produces a COMBINED ASSURANCE STATE for downstream phases while PRESERVING
each underlying state. It is NOT the final disposition engine — it never emits
HOLD / SAMPLE NOW / PRIME-RELEASE CANDIDATE. It only decides whether the
evidence is sound enough to be *considered* for a decision, and exposes a
reusable hard-gate contract that Phase 8/9 will consume.

HARD-GATE CONTRACT: a critical health or applicability failure yields a
GateResult whose `forces_action == "ABSTAIN"` (fallback: FOLLOW SOP). An
unhealthy or out-of-domain state can therefore NEVER be turned into a confident
prime-release candidate by any later phase that honours the contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol

from .applicability import ApplicabilityResult, ApplicabilityState
from .health import HealthState, SensorHealthReport
from .schemas import ACTIONS

ASSURANCE_VERSION = "assurance-v1"

HARD_GATE_ABSTAIN = "ABSTAIN"          # must be a member of schemas.ACTIONS
FALLBACK_FOLLOW_SOP = "FOLLOW_SOP"     # human/QC standard operating procedure
assert HARD_GATE_ABSTAIN in ACTIONS


class AssuranceState(str, Enum):
    ELIGIBLE_FOR_FURTHER_DECISION = "ELIGIBLE_FOR_FURTHER_DECISION"
    ELIGIBLE_WITH_CONSTRAINTS = "ELIGIBLE_WITH_CONSTRAINTS"   # DEGRADED but not blocked
    BLOCKED_BY_PREDICTION_UNAVAILABLE = "BLOCKED_BY_PREDICTION_UNAVAILABLE"
    BLOCKED_BY_SENSOR_HEALTH = "BLOCKED_BY_SENSOR_HEALTH"
    BLOCKED_BY_APPLICABILITY = "BLOCKED_BY_APPLICABILITY"


@dataclass(frozen=True)
class GateResult:
    """One hard-gate evaluation. `forces_action` is None (gate passed) or an
    action from schemas.ACTIONS that MUST be adopted (critical failure)."""
    gate_id: str
    passed: bool
    forces_action: Optional[str]
    reason_codes: tuple
    severity: int
    detail: str

    def to_dict(self) -> dict:
        return {"gate_id": self.gate_id, "passed": self.passed,
                "forces_action": self.forces_action,
                "reason_codes": list(self.reason_codes),
                "severity": self.severity, "detail": self.detail}


@dataclass(frozen=True)
class AssuranceInputs:
    """The three independent evidence layers, each kept intact."""
    prediction_available: bool
    required_features_available: bool
    health_report: SensorHealthReport
    applicability_result: ApplicabilityResult


class Gate(Protocol):
    gate_id: str
    def evaluate(self, inputs: "AssuranceInputs") -> GateResult: ...


class PredictionAvailabilityGate:
    """Prediction (or a required feature) absent -> ABSTAIN. This is a data
    availability gate, kept distinct from both health and applicability."""
    gate_id = "prediction_availability"

    def evaluate(self, inputs: AssuranceInputs) -> GateResult:
        ok = inputs.prediction_available and inputs.required_features_available
        return GateResult(
            self.gate_id, ok, None if ok else HARD_GATE_ABSTAIN,
            () if ok else ("PREDICTION_UNAVAILABLE",), 0 if ok else 3,
            "point estimate and required features present" if ok
            else "no usable point estimate / required feature at decision time")


class SensorHealthGate:
    """ABNORMAL or UNAVAILABLE health -> ABSTAIN. DEGRADED passes but is flagged
    (it must still prevent a *confident* prime candidacy downstream)."""
    gate_id = "sensor_health"

    def evaluate(self, inputs: AssuranceInputs) -> GateResult:
        hr = inputs.health_report
        blocking = hr.overall_state in (HealthState.ABNORMAL, HealthState.UNAVAILABLE)
        from .health import _RANK
        return GateResult(
            self.gate_id, not blocking, HARD_GATE_ABSTAIN if blocking else None,
            tuple(hr.reason_codes()), _RANK[hr.overall_state],
            f"sensor health {hr.overall_state.value}")


class ApplicabilityGate:
    """OOD / UNSUPPORTED / applicability-UNAVAILABLE -> ABSTAIN."""
    gate_id = "applicability"

    def evaluate(self, inputs: AssuranceInputs) -> GateResult:
        ar = inputs.applicability_result
        blocking = ar.state in (ApplicabilityState.OOD, ApplicabilityState.UNSUPPORTED,
                                ApplicabilityState.UNAVAILABLE)
        return GateResult(
            self.gate_id, not blocking, HARD_GATE_ABSTAIN if blocking else None,
            tuple(ar.reason_codes), 2 if blocking else 0,
            f"applicability {ar.state.value}")


DEFAULT_GATES = (PredictionAvailabilityGate(), SensorHealthGate(), ApplicabilityGate())


def evaluate_gates(inputs: AssuranceInputs, gates=DEFAULT_GATES) -> list:
    return [g.evaluate(inputs) for g in gates]


def gates_force_abstain(results) -> bool:
    return any(r.forces_action == HARD_GATE_ABSTAIN for r in results)


@dataclass(frozen=True)
class AssuranceResult:
    """Combined state that PRESERVES each underlying evidence state. NOT a final
    disposition — Phase 8 owns HOLD / SAMPLE NOW / PRIME CANDIDATE / ABSTAIN."""
    assurance_state: AssuranceState
    prediction_available: bool
    sensor_health_state: HealthState
    applicability_state: ApplicabilityState
    forced_action: Optional[str]
    fallback_action: str
    gate_results: tuple
    reason_codes: tuple
    note: str
    assurance_version: str = ASSURANCE_VERSION

    def to_dict(self) -> dict:
        return {"assurance_state": self.assurance_state.value,
                "prediction_available": self.prediction_available,
                "sensor_health_state": self.sensor_health_state.value,
                "applicability_state": self.applicability_state.value,
                "forced_action": self.forced_action,
                "fallback_action": self.fallback_action,
                "reason_codes": list(self.reason_codes),
                "gate_results": [g.to_dict() for g in self.gate_results],
                "note": self.note, "assurance_version": self.assurance_version}


def assess_assurance(inputs: AssuranceInputs, gates=DEFAULT_GATES) -> AssuranceResult:
    """Deterministic combination. Blocking precedence:
    prediction/data -> sensor health -> applicability. A single scalar is never
    produced; the three states travel together."""
    results = evaluate_gates(inputs, gates)
    by_id = {r.gate_id: r for r in results}
    forced = HARD_GATE_ABSTAIN if gates_force_abstain(results) else None
    hr = inputs.health_report
    ar = inputs.applicability_result

    if not by_id["prediction_availability"].passed:
        state = AssuranceState.BLOCKED_BY_PREDICTION_UNAVAILABLE
        note = "prediction/required feature unavailable at decision time"
    elif not by_id["sensor_health"].passed:
        state = AssuranceState.BLOCKED_BY_SENSOR_HEALTH
        note = f"sensor health critical ({hr.overall_state.value})"
    elif not by_id["applicability"].passed:
        state = AssuranceState.BLOCKED_BY_APPLICABILITY
        note = f"operating point not in trained domain ({ar.state.value})"
    elif hr.overall_state == HealthState.DEGRADED:
        state = AssuranceState.ELIGIBLE_WITH_CONSTRAINTS
        note = "evidence usable but DEGRADED: no confident prime candidacy"
    else:
        state = AssuranceState.ELIGIBLE_FOR_FURTHER_DECISION
        note = "all evidence layers sound; eligible for Phase 8 decision"

    reasons = sorted(set(hr.reason_codes()) | set(ar.reason_codes)
                     | ({"PREDICTION_UNAVAILABLE"}
                        if not by_id["prediction_availability"].passed else set()))
    return AssuranceResult(
        assurance_state=state, prediction_available=inputs.prediction_available,
        sensor_health_state=hr.overall_state, applicability_state=ar.state,
        forced_action=forced, fallback_action=FALLBACK_FOLLOW_SOP,
        gate_results=tuple(results), reason_codes=tuple(reasons), note=note)
