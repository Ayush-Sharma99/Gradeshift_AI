# Technical UI State Audit — Pre-Phase 14 Baseline

> **Audit Date:** 2026-10-04  
> **Checkpoint:** `v0.13.0-phase13-complete` (`a0ce7af32535700b3e951cf87ac9e490a2e6aac9`)

---

## 1. Current UI File Inventory & Status

| File | Lines | Legacy Imports | Domain Imports (`src/gradeshift/`) | Status |
|---|---|---|---|---|
| `app.py` | 209 | `from transition_optimizer import TransitionOptimizer` | **None** | Legacy Overview Dashboard — must be replaced by **PrimePath Decision Cockpit** |
| `pages/1_Grade_Transition.py` | 184 | `from transition_optimizer import TransitionOptimizer` | **None** | Legacy ramp vs bang-bang chart — must be replaced by **Transition Replay** |
| `pages/2_Soft_Sensor.py` | 146 | `from soft_sensor import SoftSensorManager`, `TransitionOptimizer` | **None** | Legacy Gaussian mock (`np.random.normal`) — must be replaced by **Quality Evidence** |
| `pages/3_AI_Optimizer.py` | 185 | `from transition_optimizer import TransitionOptimizer` | **None** | Legacy RL/NMPC control claims — must be replaced by **Disposition Workbench** |
| `pages/4_Safety.py` | 180 | Hardcoded static numbers | **None** | Legacy CBF/actuator claims — must be replaced by **Transition Guardian** |
| `pages/5_Economics.py` | 110 | Hardcoded ₹81 Cr waterfall | **None** | Legacy static financial numbers — must be replaced by **Economic Ledger** |
| `pages/6_Digital_Twin.py` | 150 | Hardcoded 2D contour + EKF claims | **None** | Legacy contour plot — must be replaced by **Transition Memory & Model Assurance** |
| `gs_theme.py` | 388 | None (pure CSS/HTML/Plotly helpers) | **None** | High-quality design system — **preserve and extend** with PrimePath badges, action cards, and updated page navigation |
| `.streamlit/config.toml` | 8 | None | **None** | Light theme matching `gs_theme.py` — **preserve as-is** |

---

## 2. Identified Technical Gaps & Legacy Defects in UI

1. **Zero Domain Coupling:** None of the 7 Streamlit files (`app.py` + 6 pages) import or invoke any module from `src/gradeshift/`.
2. **Legacy Defect D1 (Controller Framing):** `app.py`, `pages/1`, and `pages/3` present GradeShift as an RL/NMPC closed-loop setpoint controller (`optimize_bang_bang()`), contradicting the frozen PrimePath product contract (*read-only commercial-disposition decision layer*).
3. **Legacy Defect D2 (Fake Uncertainty):** `pages/2_Soft_Sensor.py` fabricates predictions and 95% confidence bands using `true_mfi * np.random.normal(1.0, 0.02)` instead of the trained `GBMQualityEstimator` (`gbm-mfi-v1`) and `SplitConformalCalibrator` (`split-conformal-v1`).
4. **Legacy Defect D3 (Static Safety Mock):** `pages/4_Safety.py` displays hardcoded progress bars and claims Control Barrier Function (CBF) projection onto DCS setpoints instead of the 7 sensor health checks (`health.py`), train-only OOD applicability (`applicability.py`), and 13 hard policy gates (`disposition.py`).
5. **Legacy Defect D4 (Ungrounded Financials):** `pages/5_Economics.py` hardcodes a ₹60–102 Cr banner and ₹81 Cr waterfall with no connection to `economics.py` (`LOW`/`BASE`/`HIGH` scenarios, permitted-action expected loss, discrete VOI, or realized vs counterfactual split).
6. **Legacy Defect D5 (Synthetic Digital Twin Mock):** `pages/6_Digital_Twin.py` renders an analytical 2D temperature contour claiming Extended Kalman Filter synchronization instead of `TransitionMemoryStore` (`memory.py`) and the Phase-13 validation/claim ledger (`validation.py`).
7. **No Mode Separation:** The legacy UI has no distinction between `ILLUSTRATIVE_DEMO` (`DEMO-A2B`), `SYNTHETIC_REPLAY` (18-event corpus replay), and `LOCKED_VALIDATION` (`final_validation.json`).

---

## 3. Domain Services & Artifacts Ready for Integration

All required backend services and frozen artifacts are already implemented and verified (266 passing tests):

- **Persisted Model Artifacts:**
  - `artifacts/phase5/gbm_mfi.joblib` (`GBMQualityEstimator`, `gbm-mfi-v1`, 41 causal features)
  - `artifacts/phase6/calibrator_gbm.joblib` (`SplitConformalCalibrator`, `split-conformal-v1:marginal_symmetric`, half-width `±0.2369 g/10min`)
  - `artifacts/phase7/applicability_detector.joblib` (`ApplicabilityDetector`, `ood-v1`)
- **Precomputed Phase Reports & Validation Package:**
  - `artifacts/final_validation.json` (Phase 13 master validation package + fingerprints + claim ledger)
  - `artifacts/phase5/manifest.json` & `metrics.json`
  - `artifacts/phase6/phase6_metrics.json`
  - `artifacts/phase7/phase7_report.json`
  - `artifacts/phase8/phase8_report.json`
  - `artifacts/phase9/phase9_report.json`
  - `artifacts/phase10/phase10_report.json`
  - `artifacts/phase11/phase11_report.json`
  - `artifacts/phase12/phase12_report.json`
- **Live Domain Engines:**
  - `gradeshift.replay.ReplayEngine` & `demo_fixture`
  - `gradeshift.disposition.evaluate_disposition` (13 hard gates + 5 candidacy gates)
  - `gradeshift.economics.evaluate_economics` & `scale_up_annual`
  - `gradeshift.memory.TransitionMemoryStore` & `retrieve_transition_memory`
  - `gradeshift.health.assess_sensor_health` & `gradeshift.faults`
  - `gradeshift.validation.robustness_matrix` & `claim_ledger`

---

## 4. Technical Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Re-running full 18-event training inside Streamlit on every page load (~60s+) | Load persisted `.joblib` models (`gbm_mfi.joblib`, `calibrator_gbm.joblib`, `applicability_detector.joblib`) and precomputed JSON reports in `RuntimeContext` (loads in `<0.5s`). |
| Mixing `ILLUSTRATIVE_DEMO` with `LOCKED_VALIDATION` | Enforce explicit `ExecutionMode` enum (`ILLUSTRATIVE_DEMO`, `SYNTHETIC_REPLAY`, `LOCKED_VALIDATION`) in `src/gradeshift/ui/context.py` with prominent provenance banners on every view. |
| Domain modules importing `streamlit` | Keep all domain logic in `src/gradeshift/*.py` untouched; build `src/gradeshift/ui/` as a pure-Python presenter package tested independently of Streamlit. |
| Breaking existing page filenames or tests | Keep `pages/1..6` filenames or clean replacements with matching sidebar navigation in `gs_theme.py`; keep root legacy scripts only if needed for historical reference, removing all imports of legacy scripts from active UI files. |

---

## 5. Implementation Sequence

1. **Presenter Layer (`src/gradeshift/ui/`):**
   - `context.py` — `RuntimeContext` singleton/loader for artifacts, models, corpus, memory store, and replay episodes.
   - `presenters.py` — Pure-Python view models for Cockpit, Replay, Quality, Disposition, Guardian, Economics, Memory/Assurance, Executive Value, Demo Walkthrough, and Locked Validation.
2. **Theme & Shared Components (`gs_theme.py`):**
   - Add PrimePath mode banner, action badge styling (`HOLD`, `SAMPLE_NOW`, `PRIME_RELEASE_CANDIDATE`, `ABSTAIN`), gate table renderer, and updated `sidebar_nav()`.
3. **PrimePath Decision Cockpit (`app.py`):**
   - Full operator decision cockpit + Executive Value View tab + Demo Walkthrough controller + Locked Validation inspector.
4. **Six Repurposed Product Pages (`pages/1..6`):**
   - `pages/1_Grade_Transition.py` → **Transition Replay**
   - `pages/2_Soft_Sensor.py` → **Quality Evidence**
   - `pages/3_AI_Optimizer.py` → **Disposition Workbench**
   - `pages/4_Safety.py` → **Transition Guardian**
   - `pages/5_Economics.py` → **Economic Ledger**
   - `pages/6_Digital_Twin.py` → **Transition Memory & Model Assurance**
5. **CLI Demo Launcher (`scripts/demo.py`, `scripts/demo.ps1`, `scripts/demo.sh`):**
   - Reproducible CLI + Streamlit demo runner verifying all steps T1–T5 + fault-injected `ABSTAIN`.
6. **Testing & Verification (`tests/test_ui_presenters.py`, `tests/test_ui_smoke.py`):**
   - Unit tests for presenter layer + headless Streamlit `AppTest` across `app.py` and all 6 pages.
