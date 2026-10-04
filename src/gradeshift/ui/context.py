"""PrimePath UI Runtime Context & Artifact Loader.

Loads and caches persisted Phase 5–13 artifacts (`.joblib` models and `.json`
reports), constructs the deterministic 18-event synthetic corpus, initializes
the `ReplayEngine` and `TransitionMemoryStore`, and enforces strict separation
between execution modes:

  * `ILLUSTRATIVE_DEMO`   — Canonical A->B walkthrough (`DEMO-A2B`, steps T1..T5 + fault branch)
  * `SYNTHETIC_REPLAY`    — Interactive replay across the 18-event synthetic corpus
  * `LOCKED_VALIDATION`   — Read-only inspection of frozen Phase-13 validation results

Domain modules never import Streamlit; this module is pure Python so it can be
tested directly in pytest and wrapped by `@st.cache_resource` in the UI layer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import config as C
from .. import disposition as D
from .. import economics as E
from .. import faults as F
from .. import memory as M
from .. import replay as R
from .. import validation as V
from ..applicability import ApplicabilityDetector, ApplicabilityResult, ApplicabilityState
from ..calibrator import SplitConformalCalibrator
from ..estimator import GBMQualityEstimator
from ..features import MaterialMapParams, as_of, build_features
from ..health import HealthState, SensorHealthReport, assess_sensor_health
from ..material_service import (
    MATERIAL_SERVICE_VERSION,
    DecisionContext,
    MappingQuality,
    MaterialEligibilityResult,
    resolve_material_window,
)
from ..partition import Partition, chronological_split
from ..pipeline import default_corpus
from ..provenance import Provenance
from ..schemas import PredictionBundle, TransitionEvent
from ..simulate import generate_episode

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ARTIFACTS_DIR = REPO_ROOT / "artifacts"


class ExecutionMode(str, Enum):
    """Explicit operating/evidence mode displayed on every PrimePath screen."""
    ILLUSTRATIVE_DEMO = "ILLUSTRATIVE_DEMO"
    SYNTHETIC_REPLAY = "SYNTHETIC_REPLAY"
    LOCKED_VALIDATION = "LOCKED_VALIDATION"


MODE_META: Dict[str, Dict[str, str]] = {
    ExecutionMode.ILLUSTRATIVE_DEMO.value: {
        "label": "ILLUSTRATIVE DEMO",
        "badge_kind": "amber",
        "banner_title": "ILLUSTRATIVE DEMO FIXTURE (NOT VALIDATION EVIDENCE)",
        "description": (
            "Controlled A→B scenario feeding deterministic evidence into the real Phase-9 "
            "Disposition Engine and Phase-10 Economic Ledger to demonstrate HOLD → SAMPLE NOW "
            "→ PRIME-RELEASE CANDIDATE → Lab Reconciliation, plus fault-triggered ABSTAIN."
        ),
        "evidence_level": "E2 / E3 (Illustrative Walkthrough)",
    },
    ExecutionMode.SYNTHETIC_REPLAY.value: {
        "label": "SYNTHETIC REPLAY",
        "badge_kind": "blue",
        "banner_title": "SYNTHETIC CORPUS REPLAY (CAUSAL AS-OF FIREWALL)",
        "description": (
            "Interactive counterfactual replay across the 18-event seeded CSTR/Erlang "
            "synthetic corpus using the frozen GBM estimator, split-conformal calibrator, "
            "and train-only OOD detector."
        ),
        "evidence_level": "E2 / E3 (Synthetic Simulation)",
    },
    ExecutionMode.LOCKED_VALIDATION.value: {
        "label": "LOCKED VALIDATION",
        "badge_kind": "green",
        "banner_title": "LOCKED VALIDATION PACKAGE (FROZEN PHASE-13 EVIDENCE)",
        "description": (
            "Read-only frozen evaluation over 5 locked test events (235 decisions). "
            "PrimePath abstains on 100% of locked rows (B→C, C→B unseen in TRAIN), "
            "achieving 0.0 t false-prime mass vs 1356.0 t (SOP) and 588.0 t (Point)."
        ),
        "evidence_level": "E2 / E3 (Frozen Validation)",
    },
}


class ApprovalStatus(str, Enum):
    """Operator/QC authorization state in the interactive UI."""
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING_HUMAN_AUTHORIZATION = "PENDING_HUMAN_AUTHORIZATION"
    HUMAN_AUTHORIZED_IN_DEMO = "HUMAN_AUTHORIZED_IN_DEMO"
    REJECTED_OR_HELD = "REJECTED_OR_HELD"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@dataclass
class RuntimeContext:
    """Central runtime state holding frozen artifacts, models, corpus, and memory."""
    artifacts_dir: Path
    gbm: GBMQualityEstimator
    calibrator: SplitConformalCalibrator
    detector: ApplicabilityDetector
    map_params: MaterialMapParams
    corpus: List[TransitionEvent]
    events_by_id: Dict[str, TransitionEvent]
    partitions: Dict[str, Partition]
    memory_store: M.TransitionMemoryStore
    # Precomputed JSON reports
    final_validation: Dict[str, Any]
    phase5_manifest: Dict[str, Any]
    phase5_metrics: Dict[str, Any]
    phase6_metrics: Dict[str, Any]
    phase7_report: Dict[str, Any]
    phase8_report: Dict[str, Any]
    phase9_report: Dict[str, Any]
    phase10_report: Dict[str, Any]
    phase11_report: Dict[str, Any]
    phase12_report: Dict[str, Any]
    frozen_manifest: Dict[str, Any]
    # Cached replay episodes keyed by (event_id, scenario_name)
    _replay_cache: Dict[Tuple[str, str], R.ReplayEpisode] = field(default_factory=dict)

    @property
    def versions(self) -> Dict[str, str]:
        cal_ver = f"{self.calibrator.calibration_version}:{self.calibrator.method}"
        return {
            "model": self.gbm.model_version,
            "calibration": cal_ver,
            "detector": self.detector.detector_version,
            "disposition": D.DISPOSITION_VERSION,
            "policy": C.POLICY.version,
            "economics": E.ECONOMICS_VERSION,
            "memory": M.MEMORY_SCHEMA_VERSION,
            "replay": R.REPLAY_VERSION,
        }

    @property
    def fingerprints(self) -> Dict[str, str]:
        return dict(self.final_validation.get("reproducibility_fingerprints", {}))

    def decision_grid(self, event: TransitionEvent, step_min: int = 10) -> List[datetime]:
        """Return the causal 10-minute decision timeline for an episode."""
        t = event.started_at + timedelta(minutes=30)
        end_ts = event.ended_at or max(
            (o.timestamp for o in event.series),
            default=event.started_at + timedelta(minutes=480),
        )
        end = end_ts - timedelta(minutes=10)
        out: List[datetime] = []
        while t <= end:
            out.append(t)
            t += timedelta(minutes=step_min)
        return out

    def get_replay_episode(
        self,
        event_id: str,
        scenario_name: str = C.DEFAULT_SCENARIO,
    ) -> R.ReplayEpisode:
        """Replay an episode from the 18-event corpus (cached per event & scenario)."""
        key = (event_id, scenario_name)
        if key not in self._replay_cache:
            ev = self.events_by_id[event_id]
            part = self.partitions[event_id].value
            spec = C.get_grade(ev.grade_to)
            sc = C.get_scenario(scenario_name)
            engine = R.ReplayEngine(
                self.gbm,
                self.calibrator,
                self.detector,
                self.map_params,
                sc,
            )
            grid = self.decision_grid(ev)
            self._replay_cache[key] = engine.replay_episode(ev, grid, spec, partition=part)
        return self._replay_cache[key]

    def evaluate_event_at(
        self,
        event: TransitionEvent,
        t: datetime,
        scenario_name: str = C.DEFAULT_SCENARIO,
        sample_available: bool = True,
        fault_kind: Optional[str] = None,
    ) -> Tuple[R.AsOfContext, D.DispositionResult, E.EconomicResult]:
        """Evaluate the full PrimePath stack on `event` at decision time `t`."""
        work_event = apply_fault_preset(event, t, fault_kind) if fault_kind else event
        spec = C.get_grade(work_event.grade_to)
        sc = C.get_scenario(scenario_name)
        engine = R.ReplayEngine(
            self.gbm,
            self.calibrator,
            self.detector,
            self.map_params,
            sc,
        )
        ctx = engine.build_context(work_event, t, spec)
        evid = D.DispositionEvidence(
            event=ctx.as_of_event,
            decision_time=t,
            spec=spec,
            prediction=ctx.prediction,
            material_eligibility=ctx.material_eligibility,
            health_report=ctx.health_report,
            applicability_result=ctx.applicability_result,
            sample_available=sample_available,
            versions=self.versions,
        )
        disp = D.evaluate_disposition(evid)
        mass = float(ctx.material_window_summary.get("mapped_mass_tonnes", 50.0))
        if mass <= 0:
            mass = 8.33
        econ_in = E.EconomicInputs(
            event_id=work_event.event_id,
            decision_id=f"{work_event.event_id}@{t.isoformat()}",
            mass_tonnes=mass,
            recoverable_mass_tonnes=mass,
            actual_route_value_per_tonne=float(sc.downgrade_price),
            scenario=sc,
        )
        econ = E.evaluate_economics(disp, econ_in)
        return ctx, disp, econ


def apply_fault_preset(
    event: TransitionEvent,
    t: datetime,
    fault_kind: Optional[str],
) -> TransitionEvent:
    """Apply a deterministic sensor fault preset from `gradeshift.faults`."""
    if not fault_kind or fault_kind == "NONE":
        return event
    if fault_kind == "FROZEN_MFI":
        return F.freeze_signal(
            event,
            "MFI_online",
            t - timedelta(minutes=35),
            t,
        )
    if fault_kind == "MISSING_MFI":
        return F.drop_signal(event, "MFI_online")
    if fault_kind == "STALE_MFI":
        return F.stale_signal(event, "MFI_online", t - timedelta(minutes=30))
    if fault_kind == "SPIKE_MFI":
        return F.spike_signal(event, "MFI_online", t, multiplier=4.0)
    if fault_kind == "GAP_H2":
        return F.gap_signal(
            event,
            "H2_ratio",
            t - timedelta(minutes=25),
            t - timedelta(minutes=2),
        )
    if fault_kind == "TIMESTAMP_DISORDER":
        return F.disorder_signal(event, "MFI_online", at=t - timedelta(minutes=5))
    return event


def _build_memory_store(
    corpus: List[TransitionEvent],
    partitions: Dict[str, Partition],
    gbm: GBMQualityEstimator,
    calib: SplitConformalCalibrator,
    detector: ApplicabilityDetector,
    map_params: MaterialMapParams,
) -> M.TransitionMemoryStore:
    """Populate an immutable TransitionMemoryStore with all 18 corpus episodes."""
    store = M.TransitionMemoryStore()
    sc = C.get_scenario(C.DEFAULT_SCENARIO)
    engine = R.ReplayEngine(gbm, calib, detector, map_params, sc)
    for ev in corpus:
        part = partitions[ev.event_id]
        spec = C.get_grade(ev.grade_to)
        end_ts = ev.ended_at or max(
            (o.timestamp for o in ev.series),
            default=ev.started_at + timedelta(minutes=480),
        )
        t = ev.started_at + timedelta(minutes=220)
        if t > end_ts - timedelta(minutes=10):
            t = end_ts - timedelta(minutes=20)
        ctx = engine.build_context(ev, t, spec)
        evid = D.DispositionEvidence(
            event=ctx.as_of_event,
            decision_time=t,
            spec=spec,
            prediction=ctx.prediction,
            material_eligibility=ctx.material_eligibility,
            health_report=ctx.health_report,
            applicability_result=ctx.applicability_result,
            sample_available=True,
        )
        disp = D.evaluate_disposition(evid)
        truth = R.reveal_truth(ev, t, spec)
        mass = float(ctx.material_window_summary.get("mapped_mass_tonnes", 50.0)) or 8.33
        econ_in = E.EconomicInputs(
            event_id=ev.event_id,
            decision_id=f"{ev.event_id}@{t.isoformat()}",
            mass_tonnes=mass,
            recoverable_mass_tonnes=mass,
            actual_route_value_per_tonne=float(sc.downgrade_price),
            scenario=sc,
        )
        was_good = bool(truth.get("was_in_spec", False))
        econ = E.evaluate_economics(disp, econ_in, realized_good=was_good)
        m_vals = [o.value for o in ev.series if o.tag == "MFI_online"]
        rec = M.MemoryRecord(
            event_id=ev.event_id,
            direction=ev.direction,
            grade_from=ev.grade_from,
            grade_to=ev.grade_to,
            unit=ev.unit,
            partition=part,
            decision_time=t,
            prediction_snapshot={
                "point_mfi": float(ctx.prediction.point_mfi),
                "lower_mfi": float(ctx.prediction.lower_mfi),
                "upper_mfi": float(ctx.prediction.upper_mfi),
                "nominal_coverage": float(ctx.prediction.nominal_coverage),
                "prob_bad_PROVISIONAL": float(ctx.prediction.prob_bad),
            },
            model_version=gbm.model_version,
            calibration_version=f"{calib.calibration_version}:{calib.method}",
            policy_version=C.POLICY.version,
            economics_version=E.ECONOMICS_VERSION,
            material_window_summary=dict(ctx.material_window_summary),
            health_state=disp.health_state or "NORMAL",
            applicability_state=disp.applicability_state or "NORMAL",
            disposition_action=disp.action,
            reason_codes=tuple(disp.reason_codes),
            approval_state={"required_role": disp.approver_role, "authorized_by": None},
            process_context={
                "phase": "ACTIVE_TRANSITION",
                "duration_min": (end_ts - ev.started_at).total_seconds() / 60.0,
                "initial_mfi": float(m_vals[0]) if m_vals else 0.0,
                "final_mfi": float(m_vals[-1]) if m_vals else 0.0,
            },
            feature_summary={
                k: float(ctx.features.get(k, 0.0))
                for k in (
                    "MFI_online_last",
                    "H2_ratio_mean_30",
                    "bed_temp_mean_30",
                    "mw_mean_age_min",
                    "mw_mapped_mass_tonnes",
                )
                if ctx.features and k in ctx.features
            },
        )
        reconciled = rec.reconcile(
            lab_outcome={
                "revealed_mfi": truth.get("revealed_mfi"),
                "was_in_spec": was_good,
            },
            actual_route=str(truth.get("actual_route", "SILO-DOWNGRADE")),
            economic_ledger=econ.to_ledger(),
            realized_value=float(econ.value_split.realized_value_currency),
            counterfactual_value=float(econ.value_split.counterfactual_opportunity_currency),
            reconciled_at=t + timedelta(minutes=45),
        )
        store.add(reconciled)
    return store


_GLOBAL_CONTEXT: Optional[RuntimeContext] = None


def load_runtime_context(
    artifacts_dir: Optional[Path] = None,
    force_reload: bool = False,
) -> RuntimeContext:
    """Load or return the singleton RuntimeContext from persisted Phase 5–13 artifacts."""
    global _GLOBAL_CONTEXT
    if _GLOBAL_CONTEXT is not None and not force_reload and artifacts_dir is None:
        return _GLOBAL_CONTEXT

    adir = Path(artifacts_dir) if artifacts_dir else ARTIFACTS_DIR
    gbm_path = adir / "phase5" / "gbm_mfi.joblib"
    calib_path = adir / "phase6" / "calibrator_gbm.joblib"
    det_path = adir / "phase7" / "applicability_detector.joblib"

    corpus = default_corpus(n_per_dir=3)
    events_by_id = {ev.event_id: ev for ev in corpus}
    parts = chronological_split(corpus)
    map_params = MaterialMapParams()

    if gbm_path.exists():
        gbm = GBMQualityEstimator.load(str(gbm_path))
    else:
        raise FileNotFoundError(f"Missing persisted GBM estimator at {gbm_path}")

    if calib_path.exists():
        calibrator = SplitConformalCalibrator.load(str(calib_path))
    else:
        raise FileNotFoundError(f"Missing persisted conformal calibrator at {calib_path}")

    if det_path.exists():
        detector = ApplicabilityDetector.load(str(det_path))
    else:
        train_events = [ev for ev in corpus if parts[ev.event_id] is Partition.TRAIN]
        detector = ApplicabilityDetector.fit(train_events, map_params=map_params)

    final_val = _load_json(adir / "final_validation.json")
    p5_manifest = _load_json(adir / "phase5" / "manifest.json")
    p5_metrics = _load_json(adir / "phase5" / "metrics.json")
    p6_metrics = _load_json(adir / "phase6" / "phase6_metrics.json")
    p7_report = _load_json(adir / "phase7" / "phase7_report.json")
    p8_report = _load_json(adir / "phase8" / "phase8_report.json")
    p9_report = _load_json(adir / "phase9_report.json") or _load_json(
        adir / "phase9" / "phase9_report.json"
    )
    p10_report = _load_json(adir / "phase10" / "phase10_report.json")
    p11_report = _load_json(adir / "phase11" / "phase11_report.json")
    p12_report = _load_json(adir / "phase12" / "phase12_report.json")
    frozen_man = _load_json(adir / "manifests" / "frozen_validation_manifest.json")

    mem_store = _build_memory_store(corpus, parts, gbm, calibrator, detector, map_params)

    ctx = RuntimeContext(
        artifacts_dir=adir,
        gbm=gbm,
        calibrator=calibrator,
        detector=detector,
        map_params=map_params,
        corpus=corpus,
        events_by_id=events_by_id,
        partitions=parts,
        memory_store=mem_store,
        final_validation=final_val,
        phase5_manifest=p5_manifest,
        phase5_metrics=p5_metrics,
        phase6_metrics=p6_metrics,
        phase7_report=p7_report,
        phase8_report=p8_report,
        phase9_report=p9_report,
        phase10_report=p10_report,
        phase11_report=p11_report,
        phase12_report=p12_report,
        frozen_manifest=frozen_man,
    )
    if artifacts_dir is None:
        _GLOBAL_CONTEXT = ctx
    return ctx
