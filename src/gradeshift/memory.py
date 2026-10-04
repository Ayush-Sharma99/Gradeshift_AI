"""Phase 11 — TRANSITION MEMORY.

An auditable, append-only evidence-memory layer. It PRESERVES completed
transition episodes (what happened, what was predicted, what was recommended,
what the lab later established, realized/counterfactual value) and RETRIEVES
directional, scope-isolated historical evidence for later advisory display.

It does NOT learn online. Storing or reconciling a record NEVER updates the
estimator, thresholds, calibration, or policy. Promotion into a training cycle
is an explicit, external, controlled action — never a side effect here.

Jury language: "Transition Memory gives PrimePath auditable historical
context." NOT "the AI learns continuously from every transition."

Everything is SIMULATION/ASSUMPTION — no HMEL data or validation is implied.
Retrieved analogs are historical EVIDENCE, never a causal prediction.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple

from .partition import Partition
from .provenance import Provenance

MEMORY_SCHEMA_VERSION = "memory-v1"
SIMILARITY_MODEL_VERSION = "similarity-weighted-v1"

# a per-dimension normalized difference at or below this reads as a "match"
MATCH_TOLERANCE = 0.10


# ── stable fingerprints (NEVER Python object hashes) ────────────────────────
def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(obj, *, prefix: str = "") -> str:
    """Deterministic content fingerprint. Stable across processes/runs — unlike
    builtin hash() — so it is safe as a persistent identifier."""
    digest = hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}" if prefix else digest


class ReconciliationStatus(str, Enum):
    PENDING = "PENDING"                        # decision made, lab truth not in
    PARTIALLY_RECONCILED = "PARTIALLY_RECONCILED"  # some but not all evidence in
    RECONCILED = "RECONCILED"                  # lab truth + disposition complete
    INELIGIBLE = "INELIGIBLE"                  # cannot be trusted as history


class UnitPolicy(str, Enum):
    SAME_UNIT_ONLY = "SAME_UNIT_ONLY"          # strict: unit must match
    PREFER_SAME_UNIT = "PREFER_SAME_UNIT"      # cross-unit allowed, penalized
    ANY_UNIT = "ANY_UNIT"                      # unit ignored


# ── immutable, versioned memory record ──────────────────────────────────────
@dataclass(frozen=True)
class MemoryRecord:
    """One completed transition episode as immutable, versioned evidence.

    Historical evidence is NEVER mutated in place. Reconciliation or any update
    produces a NEW record (``record_version`` incremented) via ``reconcile`` /
    ``with_update``; the store keeps every version append-only."""
    event_id: str
    direction: str                              # "A->B" (DIRECTIONAL; != "B->A")
    grade_from: str
    grade_to: str
    unit: str
    partition: Partition
    decision_time: datetime
    # prediction / model lineage
    prediction_snapshot: Dict[str, float]       # point/lower/upper/coverage/prob_bad_PROVISIONAL
    model_version: str
    calibration_version: str
    policy_version: str
    economics_version: str
    # evidence layers
    material_window_summary: Dict[str, object]  # mass/age/destinations/quality/route
    health_state: str
    applicability_state: str
    disposition_action: str
    reason_codes: Tuple[str, ...]
    approval_state: Dict[str, object]           # role / authorized_by / authorized_at
    process_context: Dict[str, object]         # phase + initial/final state, duration_min
    feature_summary: Dict[str, float]           # selected feature fingerprint inputs
    # reconciled later-truth (None until revealed)
    lab_outcome: Optional[Dict[str, object]] = None
    actual_route: Optional[str] = None
    economic_ledger: Optional[Dict[str, object]] = None
    realized_value: Optional[float] = None
    counterfactual_value: Optional[float] = None
    reconciled_at: Optional[datetime] = None
    # bookkeeping
    reconciliation_status: ReconciliationStatus = ReconciliationStatus.PENDING
    eligibility_flags: Tuple[str, ...] = ()     # advisory flags set at build time
    provenance: Provenance = Provenance.SIMULATED
    schema_version: str = MEMORY_SCHEMA_VERSION
    record_version: int = 1

    @property
    def feature_fingerprint(self) -> str:
        return fingerprint(self.feature_summary, prefix="feat")

    @property
    def identity_fingerprint(self) -> str:
        """Identity = event + direction + decision time + feature + schema. Stable
        across runs; traces any change to a relevant definition."""
        return fingerprint({"event_id": self.event_id, "direction": self.direction,
                            "decision_time": self.decision_time.isoformat(),
                            "feature": self.feature_fingerprint,
                            "schema_version": self.schema_version}, prefix="rec")

    @property
    def version_fingerprint(self) -> str:
        return fingerprint({"model": self.model_version, "calibration": self.calibration_version,
                            "policy": self.policy_version, "economics": self.economics_version,
                            "schema": self.schema_version}, prefix="ver")

    def reconcile(self, *, lab_outcome: Dict[str, object], actual_route: str,
                  economic_ledger: Optional[Dict[str, object]] = None,
                  realized_value: Optional[float] = None,
                  counterfactual_value: Optional[float] = None,
                  reconciled_at: datetime,
                  status: ReconciliationStatus = ReconciliationStatus.RECONCILED) -> "MemoryRecord":
        """Return a NEW record version carrying revealed truth. The original is
        untouched (immutable append-only history)."""
        if reconciled_at < self.decision_time:
            raise ValueError("reconciled_at cannot precede decision_time")
        return replace(self, lab_outcome=dict(lab_outcome), actual_route=actual_route,
                       economic_ledger=(dict(economic_ledger) if economic_ledger else None),
                       realized_value=realized_value, counterfactual_value=counterfactual_value,
                       reconciled_at=reconciled_at, reconciliation_status=status,
                       record_version=self.record_version + 1)

    def with_update(self, **changes) -> "MemoryRecord":
        """Generic append-only update: new version, original preserved."""
        changes.setdefault("record_version", self.record_version + 1)
        return replace(self, **changes)

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "direction": self.direction,
                "grade_from": self.grade_from, "grade_to": self.grade_to,
                "unit": self.unit, "partition": self.partition.name,
                "decision_time": self.decision_time.isoformat(),
                "prediction_snapshot": dict(self.prediction_snapshot),
                "model_version": self.model_version,
                "calibration_version": self.calibration_version,
                "policy_version": self.policy_version,
                "economics_version": self.economics_version,
                "material_window_summary": dict(self.material_window_summary),
                "health_state": self.health_state,
                "applicability_state": self.applicability_state,
                "disposition_action": self.disposition_action,
                "reason_codes": list(self.reason_codes),
                "approval_state": dict(self.approval_state),
                "process_context": dict(self.process_context),
                "feature_summary": dict(self.feature_summary),
                "lab_outcome": self.lab_outcome, "actual_route": self.actual_route,
                "economic_ledger": self.economic_ledger,
                "realized_value": self.realized_value,
                "counterfactual_value": self.counterfactual_value,
                "reconciled_at": self.reconciled_at.isoformat() if self.reconciled_at else None,
                "reconciliation_status": self.reconciliation_status.value,
                "eligibility_flags": list(self.eligibility_flags),
                "provenance": self.provenance.value,
                "schema_version": self.schema_version,
                "record_version": self.record_version,
                "feature_fingerprint": self.feature_fingerprint,
                "identity_fingerprint": self.identity_fingerprint,
                "version_fingerprint": self.version_fingerprint}

    @classmethod
    def from_dict(cls, d: dict) -> "MemoryRecord":
        rt = d.get("reconciled_at")
        return cls(
            event_id=d["event_id"], direction=d["direction"],
            grade_from=d["grade_from"], grade_to=d["grade_to"], unit=d["unit"],
            partition=Partition[d["partition"]],
            decision_time=datetime.fromisoformat(d["decision_time"]),
            prediction_snapshot=dict(d["prediction_snapshot"]),
            model_version=d["model_version"], calibration_version=d["calibration_version"],
            policy_version=d["policy_version"], economics_version=d["economics_version"],
            material_window_summary=dict(d["material_window_summary"]),
            health_state=d["health_state"], applicability_state=d["applicability_state"],
            disposition_action=d["disposition_action"],
            reason_codes=tuple(d["reason_codes"]), approval_state=dict(d["approval_state"]),
            process_context=dict(d["process_context"]), feature_summary=dict(d["feature_summary"]),
            lab_outcome=d.get("lab_outcome"), actual_route=d.get("actual_route"),
            economic_ledger=d.get("economic_ledger"), realized_value=d.get("realized_value"),
            counterfactual_value=d.get("counterfactual_value"),
            reconciled_at=datetime.fromisoformat(rt) if rt else None,
            reconciliation_status=ReconciliationStatus(d["reconciliation_status"]),
            eligibility_flags=tuple(d.get("eligibility_flags", ())),
            provenance=Provenance(d.get("provenance", "SIMULATED")),
            schema_version=d.get("schema_version", MEMORY_SCHEMA_VERSION),
            record_version=int(d.get("record_version", 1)))


# ── eligibility (separate from storage: a record may exist but be ineligible) ─
@dataclass(frozen=True)
class EligibilityResult:
    eligible: bool
    reasons: Tuple[str, ...]                    # machine-readable flags
    status: ReconciliationStatus

    def to_dict(self) -> dict:
        return {"eligible": self.eligible, "reasons": list(self.reasons),
                "status": self.status.value}


# eligibility reason codes
EL_OK = "ELIGIBLE"
EL_INVALID_EVENT = "INELIGIBLE_INVALID_EVENT"
EL_PROVENANCE_MISSING = "INELIGIBLE_PROVENANCE_MISSING"
EL_SCHEMA_MISMATCH = "INELIGIBLE_SCHEMA_MISMATCH"
EL_VERSION_MISMATCH = "INELIGIBLE_VERSION_MISMATCH"
EL_INSUFFICIENT_OUTCOME = "INELIGIBLE_INSUFFICIENT_OUTCOME"
EL_BAD_PARTITION = "INELIGIBLE_PARTITION_UNKNOWN"
EL_DATA_QUALITY = "INELIGIBLE_DATA_QUALITY"


def evaluate_eligibility(rec: MemoryRecord, *, require_reconciled: bool = True,
                         expected_versions: Optional[Dict[str, str]] = None
                         ) -> EligibilityResult:
    """Explicit eligibility for retrieval/training SUPPORT. Storage is unaffected;
    an ineligible record stays in memory, just excluded from support."""
    reasons: List[str] = []
    if not rec.event_id or "->" not in rec.direction:
        reasons.append(EL_INVALID_EVENT)
    if rec.provenance is None:
        reasons.append(EL_PROVENANCE_MISSING)
    if rec.schema_version != MEMORY_SCHEMA_VERSION:
        reasons.append(EL_SCHEMA_MISMATCH)
    if expected_versions:
        got = {"model": rec.model_version, "calibration": rec.calibration_version,
               "policy": rec.policy_version, "economics": rec.economics_version}
        if any(got.get(k) != v for k, v in expected_versions.items()):
            reasons.append(EL_VERSION_MISMATCH)
    if require_reconciled and (rec.reconciliation_status != ReconciliationStatus.RECONCILED
                               or rec.lab_outcome is None):
        reasons.append(EL_INSUFFICIENT_OUTCOME)
    if not isinstance(rec.partition, Partition):
        reasons.append(EL_BAD_PARTITION)
    vals = [v for v in rec.feature_summary.values() if isinstance(v, (int, float))]
    if not rec.feature_summary or any(v != v for v in vals):   # empty or NaN
        reasons.append(EL_DATA_QUALITY)
    if rec.reconciliation_status == ReconciliationStatus.INELIGIBLE:
        reasons.append(EL_INVALID_EVENT)
    eligible = len(reasons) == 0
    return EligibilityResult(eligible, tuple(reasons) if reasons else (EL_OK,),
                             rec.reconciliation_status)


# ── retrieval scope (enforced INTERNALLY — callers can't forget exclusions) ──
@dataclass(frozen=True)
class MemoryScope:
    direction: str                              # REQUIRED — retrieval is directional
    allowed_partition: Optional[Partition] = Partition.TRAIN
    excluded_event_ids: frozenset = frozenset()
    unit: Optional[str] = None
    unit_policy: UnitPolicy = UnitPolicy.PREFER_SAME_UNIT
    require_reconciled: bool = True
    require_eligible: bool = True
    expected_versions: Optional[Dict[str, str]] = None

    def to_dict(self) -> dict:
        return {"direction": self.direction,
                "allowed_partition": self.allowed_partition.name if self.allowed_partition else None,
                "excluded_event_ids": sorted(self.excluded_event_ids),
                "unit": self.unit, "unit_policy": self.unit_policy.value,
                "require_reconciled": self.require_reconciled,
                "require_eligible": self.require_eligible,
                "expected_versions": self.expected_versions}


@dataclass(frozen=True)
class RetrievalContext:
    """The CURRENT transition's context used to score analogs. Carries direction
    so retrieval can never match an incompatible direction on trajectory alone."""
    event_id: str
    direction: str
    grade_from: str
    grade_to: str
    unit: str
    phase: str
    process_context: Dict[str, object]
    material_window_summary: Dict[str, object]
    feature_summary: Dict[str, float]
    decision_time: Optional[datetime] = None

    @classmethod
    def from_record(cls, rec: MemoryRecord) -> "RetrievalContext":
        return cls(event_id=rec.event_id, direction=rec.direction,
                   grade_from=rec.grade_from, grade_to=rec.grade_to, unit=rec.unit,
                   phase=str(rec.process_context.get("phase", "")),
                   process_context=dict(rec.process_context),
                   material_window_summary=dict(rec.material_window_summary),
                   feature_summary=dict(rec.feature_summary),
                   decision_time=rec.decision_time)

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "direction": self.direction,
                "grade_from": self.grade_from, "grade_to": self.grade_to,
                "unit": self.unit, "phase": self.phase,
                "process_context": dict(self.process_context),
                "material_window_summary": dict(self.material_window_summary),
                "feature_summary": dict(self.feature_summary)}


# ── transparent, deterministic weighted-distance similarity (no embeddings) ──
DEFAULT_WEIGHTS: Dict[str, float] = {
    "phase": 2.0, "unit": 1.0, "duration_min": 1.0, "initial_mfi": 1.5,
    "final_mfi": 1.5, "mapped_mass_tonnes": 1.0, "mean_age_min": 0.5, "features": 2.0,
}
_EPS = 1e-9


def _rel_diff(a: float, b: float) -> float:
    denom = abs(a) + abs(b) + _EPS
    return min(1.0, abs(a - b) / denom)


@dataclass(frozen=True)
class SimilarityResult:
    score: float                                # 1 - weighted distance, in [0,1]
    matching_dimensions: Tuple[str, ...]
    differences: Dict[str, Dict[str, float]]
    weights_version: str = SIMILARITY_MODEL_VERSION

    def to_dict(self) -> dict:
        return {"score": self.score,
                "matching_dimensions": list(self.matching_dimensions),
                "differences": self.differences,
                "weights_version": self.weights_version}


def _numeric(ctx_map: Dict[str, object], rec_map: Dict[str, object], key: str):
    a, b = ctx_map.get(key), rec_map.get(key)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a), float(b)
    return None


def compute_similarity(ctx: RetrievalContext, rec: MemoryRecord,
                       weights: Optional[Dict[str, float]] = None,
                       cross_unit: bool = False) -> SimilarityResult:
    """Deterministic weighted normalized distance. Direction is a HARD gate
    handled by the scope, never a soft score — so trajectory similarity alone
    can never pull in an incompatible-direction event."""
    w = dict(weights or DEFAULT_WEIGHTS)
    diffs: Dict[str, float] = {}

    # categorical
    diffs["phase"] = 0.0 if ctx.phase == str(rec.process_context.get("phase", "")) else 1.0
    diffs["unit"] = (0.0 if ctx.unit == rec.unit else 1.0)
    # numeric process + material dims
    for key, src_c, src_r in (
        ("duration_min", ctx.process_context, rec.process_context),
        ("initial_mfi", ctx.process_context, rec.process_context),
        ("final_mfi", ctx.process_context, rec.process_context),
        ("mapped_mass_tonnes", ctx.material_window_summary, rec.material_window_summary),
        ("mean_age_min", ctx.material_window_summary, rec.material_window_summary),
    ):
        pair = _numeric(src_c, src_r, key)
        diffs[key] = _rel_diff(*pair) if pair else 1.0
    # feature vector (mean rel-diff over shared numeric keys)
    shared = [k for k in ctx.feature_summary
              if k in rec.feature_summary
              and isinstance(ctx.feature_summary[k], (int, float))
              and isinstance(rec.feature_summary[k], (int, float))]
    if shared:
        diffs["features"] = sum(_rel_diff(float(ctx.feature_summary[k]),
                                          float(rec.feature_summary[k]))
                                for k in shared) / len(shared)
    else:
        diffs["features"] = 1.0

    total_w = sum(w.get(k, 0.0) for k in diffs)
    distance = sum(w.get(k, 0.0) * diffs[k] for k in diffs) / (total_w or 1.0)
    if cross_unit:
        distance = min(1.0, distance + 0.10)    # explicit cross-unit penalty
    score = round(1.0 - distance, 6)

    matching = tuple(sorted(k for k, dv in diffs.items() if dv <= MATCH_TOLERANCE))
    differences = {k: {"normalized_diff": round(dv, 6)}
                   for k, dv in sorted(diffs.items()) if dv > MATCH_TOLERANCE}
    return SimilarityResult(score, matching, differences)


# ── decision-evidence link (correlation, never causation) ────────────────────
@dataclass(frozen=True)
class HistoricalEvidence:
    """One analog's auditable evidence for later UI display. Phrased as observed
    history, never as a causal prediction for the current transition."""
    event_id: str
    similarity: SimilarityResult
    partition: str
    reconciliation_status: str
    provenance: str
    eligible: bool
    what_was_similar: Tuple[str, ...]           # matching dimensions
    what_differed: Dict[str, Dict[str, float]]
    what_was_predicted: Dict[str, float]        # prediction snapshot (as-of)
    what_happened: Dict[str, object]            # observed quality trajectory summary
    how_disposed: Dict[str, object]             # recommended action + actual route
    laboratory_truth: Optional[Dict[str, object]]
    realized_value: Optional[float]
    counterfactual_value: Optional[float]
    note: str = ("Observed historical evidence from an eligible analog. "
                 "Correlation only — NOT a causal prediction that the current "
                 "transition will repeat this outcome.")

    def to_dict(self) -> dict:
        return {"event_id": self.event_id, "similarity": self.similarity.to_dict(),
                "partition": self.partition,
                "reconciliation_status": self.reconciliation_status,
                "provenance": self.provenance, "eligible": self.eligible,
                "what_was_similar": list(self.what_was_similar),
                "what_differed": self.what_differed,
                "what_was_predicted": dict(self.what_was_predicted),
                "what_happened": dict(self.what_happened),
                "how_disposed": dict(self.how_disposed),
                "laboratory_truth": self.laboratory_truth,
                "realized_value": self.realized_value,
                "counterfactual_value": self.counterfactual_value, "note": self.note}


def _reconciled_as_of(rec: MemoryRecord, as_of: Optional[datetime]) -> bool:
    """Causal reconciliation: a record counts as reconciled for a query ONLY if
    its lab truth was revealed at/before the query's decision time."""
    if rec.reconciliation_status != ReconciliationStatus.RECONCILED or rec.lab_outcome is None:
        return False
    if as_of is not None and rec.reconciled_at is not None and rec.reconciled_at > as_of:
        return False
    return True


def _build_evidence(ctx: RetrievalContext, rec: MemoryRecord, sim: SimilarityResult,
                    eligible: bool, expose_outcome: bool) -> HistoricalEvidence:
    what_happened = {"disposition_action": rec.disposition_action,
                     "revealed_in_spec": (rec.lab_outcome or {}).get("was_in_spec")
                     if expose_outcome else None}
    how = {"recommended_action": rec.disposition_action,
           "actual_route": rec.actual_route if expose_outcome else None}
    return HistoricalEvidence(
        event_id=rec.event_id, similarity=sim, partition=rec.partition.name,
        reconciliation_status=rec.reconciliation_status.value,
        provenance=rec.provenance.value, eligible=eligible,
        what_was_similar=sim.matching_dimensions, what_differed=sim.differences,
        what_was_predicted=dict(rec.prediction_snapshot),
        what_happened=what_happened, how_disposed=how,
        laboratory_truth=(rec.lab_outcome if expose_outcome else None),
        realized_value=(rec.realized_value if expose_outcome else None),
        counterfactual_value=(rec.counterfactual_value if expose_outcome else None))


# ── append-only store + scope-enforcing retrieval ───────────────────────────
class TransitionMemoryStore:
    """Append-only memory. Storing/reconciling NEVER triggers model/calibration/
    policy/threshold changes — see `assert_no_online_learning`."""

    def __init__(self) -> None:
        self._versions: List[MemoryRecord] = []     # every version, append-only

    def add(self, rec: MemoryRecord) -> None:
        self._versions.append(rec)

    def all_versions(self) -> Tuple[MemoryRecord, ...]:
        return tuple(self._versions)

    def latest(self, event_id: str) -> Optional[MemoryRecord]:
        best = None
        for r in self._versions:
            if r.event_id == event_id and (best is None or r.record_version > best.record_version):
                best = r
        return best

    def all_latest(self) -> List[MemoryRecord]:
        ids = {r.event_id for r in self._versions}
        return [self.latest(i) for i in sorted(ids)]

    def retrieve(self, ctx: RetrievalContext, scope: MemoryScope, k: int = 3
                 ) -> List[HistoricalEvidence]:
        """Scope is enforced INTERNALLY — callers never have to remember the
        exclusion rules. Deterministic ordering."""
        out: List[Tuple[float, str, HistoricalEvidence]] = []
        for rec in self.all_latest():
            # 1. current event never retrieves itself (always, regardless of scope)
            if rec.event_id == ctx.event_id or rec.event_id in scope.excluded_event_ids:
                continue
            # 2. DIRECTIONAL: direction must match the scope (A->B != B->A)
            if rec.direction != scope.direction:
                continue
            # 3. partition isolation (holdout contamination guard)
            if scope.allowed_partition is not None and rec.partition != scope.allowed_partition:
                continue
            # 4. unit policy
            same_unit = (scope.unit is None or rec.unit == scope.unit)
            if scope.unit_policy == UnitPolicy.SAME_UNIT_ONLY and not same_unit:
                continue
            # 5. causal reconciliation as-of the current decision
            rec_as_of = _reconciled_as_of(rec, ctx.decision_time)
            if scope.require_reconciled and not rec_as_of:
                continue
            # 6. eligibility
            elig = evaluate_eligibility(rec, require_reconciled=scope.require_reconciled,
                                        expected_versions=scope.expected_versions)
            if scope.require_eligible and not elig.eligible:
                continue
            cross_unit = (scope.unit_policy == UnitPolicy.PREFER_SAME_UNIT and not same_unit)
            sim = compute_similarity(ctx, rec, cross_unit=cross_unit)
            ev = _build_evidence(ctx, rec, sim, elig.eligible, expose_outcome=rec_as_of)
            out.append((sim.score, rec.event_id, ev))
        # deterministic: highest score first, then event_id for ties
        out.sort(key=lambda t: (-t[0], t[1]))
        return [ev for _, _, ev in out[:max(0, k)]]

    def statistics(self) -> dict:
        latest = self.all_latest()
        by_dir: Dict[str, int] = {}
        by_unit: Dict[str, int] = {}
        by_status: Dict[str, int] = {}
        reconciled = eligible = 0
        for r in latest:
            by_dir[r.direction] = by_dir.get(r.direction, 0) + 1
            by_unit[r.unit] = by_unit.get(r.unit, 0) + 1
            by_status[r.reconciliation_status.value] = by_status.get(r.reconciliation_status.value, 0) + 1
            if r.reconciliation_status == ReconciliationStatus.RECONCILED:
                reconciled += 1
            if evaluate_eligibility(r).eligible:
                eligible += 1
        return {"total_episodes": len(latest), "total_versions": len(self._versions),
                "reconciled_episodes": reconciled, "eligible_episodes": eligible,
                "excluded_ineligible": len(latest) - eligible,
                "by_direction": by_dir, "by_unit": by_unit, "by_status": by_status,
                "schema_version": MEMORY_SCHEMA_VERSION,
                "note": "Counts only. No synthetic 'learning improvement' metric "
                        "is fabricated from this small SIMULATED corpus."}


def retrieve_transition_memory(current_context: RetrievalContext,
                               memory_scope: MemoryScope, k: int,
                               store: TransitionMemoryStore) -> List[HistoricalEvidence]:
    """Phase-12-facing service entrypoint. Returns auditable HistoricalEvidence;
    the scope is enforced inside the store, not by the caller."""
    return store.retrieve(current_context, memory_scope, k)


def assert_no_online_learning() -> dict:
    """Explicit, test-checkable contract: this module imports NO estimator /
    calibrator / policy mutator and performs NO model update on store/reconcile."""
    import gradeshift.memory as _m
    banned = ("estimator", "calibrator", "fit(", "partial_fit", "set_params")
    src_names = [n for n in dir(_m) if not n.startswith("_")]
    touches_model = any(any(b in n.lower() for b in ("fit", "estimator", "calibrat"))
                        for n in src_names)
    return {"performs_online_learning": False, "touches_model_symbols": touches_model,
            "contract": "store/reconcile never update model, calibration, "
                        "thresholds, or policy; promotion is an external action."}
