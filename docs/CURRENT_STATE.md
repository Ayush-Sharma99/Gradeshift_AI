# CURRENT_STATE — GradeShift PrimePath

**Authoritative live engineering status at the Phase-13 Checkpoint.**  
Pairs with [`PROJECT_HANDOFF.md`](../PROJECT_HANDOFF.md), [`AGENTS.md`](../AGENTS.md), [`FINAL_VALIDATION_REPORT.md`](FINAL_VALIDATION_REPORT.md), [`FINAL_BASELINE_AUDIT.md`](FINAL_BASELINE_AUDIT.md), and [`FINAL_PRODUCT_IMPLEMENTATION_PLAN.md`](FINAL_PRODUCT_IMPLEMENTATION_PLAN.md).

---

## 1. Checkpoint & Repository Identity

- **Date of Audit:** 2026-10-04
- **Project:** GradeShift PrimePath
- **Current Checkpoint:** Phase 13 — Final Validation Complete
- **GitHub Repository URL:** `https://github.com/Ayush-Sharma99/Gradeshift_AI.git`
- **Checkpoint Branch:** `primepath-phase13-complete`
- **Checkpoint Tag:** `v0.13.0-phase13-complete`
- **Commit SHA:** *(updated at checkpoint commit/tag step)*
- **Evidence Ceiling:** `E2` (synthetic simulation) / `E3` (controlled prototype). **Nothing is HMEL-validated (`E4`/`E5` = 0).**

---

## 2. Completed Capabilities (`src/gradeshift/` — 21 Modules)

All 13 domain phases are implemented, unit-tested, and verified end-to-end:

| Phase | Capability | Module(s) | Key Verified Properties |
|---:|---|---|---|
| **1** | Central Configuration & Typed Schemas | [`config.py`](../src/gradeshift/config.py), [`schemas.py`](../src/gradeshift/schemas.py), [`provenance.py`](../src/gradeshift/provenance.py) | Single source of truth for grades (`A`, `B`, `C`), economic scenarios (`LOW`, `BASE`, `HIGH`), and policy (`policy-v1`); UTC-enforced frozen dataclasses with `Provenance` enum. |
| **2** | Seeded Synthetic Episode Generator & Ingestion | [`simulate.py`](../src/gradeshift/simulate.py), [`ingestion.py`](../src/gradeshift/ingestion.py) | Calibrated CSTR/Erlang washout where steady state at target $H_2/M$ equals target MFI (`8.00 g/10min` for Grade B, fixing legacy defect D1); all records tagged `SIMULATED`. |
| **3** | Event Construction, Causal Firewall & Whole-Event Partitions | [`events.py`](../src/gradeshift/events.py), [`alignment.py`](../src/gradeshift/alignment.py), [`partition.py`](../src/gradeshift/partition.py), [`dataset.py`](../src/gradeshift/dataset.py) | Separates sample `collected_at` from `result_at`; `as_of(event, t)` prevents future truth leakage; chronological whole-event split (`10 TRAIN`, `3 CALIBRATION`, `5 LOCKED_TEST`). |
| **4** | Residence-Time & Material Identity Mapping | [`material_identity.py`](../src/gradeshift/material_identity.py) | Maps decision time $t$ through transport lag (`25 min`) and mean residence time (`150 min`) to downstream production window, mass (`tonnes`), and age dispersion. |
| **5** | Causal Features & Point Quality Estimation | [`features.py`](../src/gradeshift/features.py), [`estimator.py`](../src/gradeshift/estimator.py), [`pipeline.py`](../src/gradeshift/pipeline.py) | `37` causal features (`feat-v1`); `GBMQualityEstimator` (`gbm-mfi-v1`) + `LastLabBaseline`, `DeterministicProcessBaseline`, and `LinearProcessBaseline`. |
| **6** | Calibrated Uncertainty (Split-Conformal) | [`calibrator.py`](../src/gradeshift/calibrator.py), [`pipeline.py`](../src/gradeshift/pipeline.py) | `SplitConformalCalibrator` (`split-conformal-v1`) fitted strictly on `CALIBRATION` (`141` rows across `3` events); subgroup conditioning gated when `<5` events. |
| **7** | Sensor Health, Fault Fixtures & OOD Applicability | [`health.py`](../src/gradeshift/health.py), [`faults.py`](../src/gradeshift/faults.py), [`applicability.py`](../src/gradeshift/applicability.py), [`assurance.py`](../src/gradeshift/assurance.py) | Detects missing, stale, frozen, out-of-range, rate-spike, gap, and timestamp-disorder faults; train-only `ApplicabilityDetector` flags unseen directions/units and feature shifts. |
| **8** | Operational Material Service | [`material_service.py`](../src/gradeshift/material_service.py), [`pipeline.py`](../src/gradeshift/pipeline.py) | Produces `MaterialResolution`, `MaterialEligibilityResult`, `MaterialQualityLineage`, and mass conservation reconciliation across boundary cases `A–G`. |
| **9** | Disposition Decision Engine | [`disposition.py`](../src/gradeshift/disposition.py), [`pipeline.py`](../src/gradeshift/pipeline.py) | Pure `evaluate_disposition` engine; evaluates **13 hard policy gates FIRST**; outputs `HOLD`, `SAMPLE_NOW`, `PRIME_RELEASE_CANDIDATE`, `ABSTAIN`, or `FOLLOW_SOP` on expiry. |
| **10** | Expected Loss, Discrete VOI & Economic Ledger | [`economics.py`](../src/gradeshift/economics.py), [`pipeline.py`](../src/gradeshift/pipeline.py) | Ranks **permitted actions only** (never overrides a hard gate); separates realized vs counterfactual value; provides `scale_up_annual` scenario function. |
| **11** | Immutable Transition Memory & Analog Retrieval | [`memory.py`](../src/gradeshift/memory.py), [`pipeline.py`](../src/gradeshift/pipeline.py) | Append-only `TransitionMemoryStore`; post-truth reconciliation; directional (`A->B` only), partition-isolated (`TRAIN` only), self-excluding top-$k$ analog retrieval; zero online retraining. |
| **12** | Counterfactual Replay Engine | [`replay.py`](../src/gradeshift/replay.py), [`pipeline.py`](../src/gradeshift/pipeline.py) | Replays `SOP_FIXTURE`, `POINT_THRESHOLD`, `PRIMEPATH`, and `ORACLE_DIAGNOSTIC_ONLY` under strict `as_of_event` firewall; provides separate `demo_fixture`. |
| **13** | Final Validation & Claim Governance | [`validation.py`](../src/gradeshift/validation.py), [`pipeline.py`](../src/gradeshift/pipeline.py) | Locked validation metrics, abstention decomposition, 11-scenario robustness matrix, diagnostic sensitivity, economic sanity, determinism proof, and `E0–E5` claim ledger. |

---

## 3. Actual Test Count & Execution Runtime

- **Test Suite Location:** [`tests/`](../tests/) (`20` test modules + [`conftest.py`](../conftest.py))
- **Verified Test Result:** **`266 passed, 0 failed`**
- **Verified Full-Suite Runtime:** **`394.07 seconds` (`6 min 34 sec`)** on Python `3.10.0` (Windows CPU).
- **Why full-suite runtime is ~6.5 minutes:** End-to-end verification tests (`test_final_validation.py::test_phase13_package` `130.35s`, `test_calibrator.py::test_calibration_reproducible` `69.31s`, `test_calibrator.py::test_insufficient_data_handling` `37.55s`, `test_replay.py::test_A_future_lab_no_effect` `34.21s`, `test_estimator.py::test_reproducible_pipeline` `31.06s`) rebuild and verify the entire 18-episode corpus, feature matrices, GBM training, conformal calibration, and multi-policy replay from scratch.

---

## 4. Actual Validation Artifact Locations

| Artifact Path | Size | Contents |
|---|---:|---|
| [`artifacts/final_validation.json`](../artifacts/final_validation.json) | `40.7 KB` | Primary Phase-13 final validation JSON package (manifest, fingerprints, Level A/B/C metrics, abstention decomposition, zero-candidate diagnostic, robustness matrix, sensitivity, sample VOI, economic sanity, determinism, `illustrative_demo_fixture`, claim ledger, pass/fail criteria). |
| [`artifacts/final_validation/final_validation.json`](../artifacts/final_validation/final_validation.json) | `40.7 KB` | Structured copy of `final_validation.json`. |
| [`docs/FINAL_VALIDATION_REPORT.md`](FINAL_VALIDATION_REPORT.md) | `18.2 KB` | Human-readable Phase-13 validation report rendered from `final_validation.json`. |
| [`artifacts/manifests/frozen_validation_manifest.json`](../artifacts/manifests/frozen_validation_manifest.json) | `1.8 KB` | Frozen Phase-13 validation manifest and reproducibility fingerprints (`manifest:5abc0eb1ad93f56c`, `calib:3cf275c76727911a`, `policy:a2555a4d9431c288`, `econ:6cbd173e21b7b79a`). |
| [`artifacts/manifests/phase5_manifest.json`](../artifacts/manifests/phase5_manifest.json) | `11.9 KB` | Copy of the Phase-5 dataset and 37-feature schema manifest. |
| [`artifacts/phase5/gbm_mfi.joblib`](../artifacts/phase5/gbm_mfi.joblib) | `287.2 KB` | Persisted `GBMQualityEstimator` (`gbm-mfi-v1`, seed `42`). |
| [`artifacts/phase5/manifest.json`](../artifacts/phase5/manifest.json) | `11.9 KB` | Dataset version (`ds-v1`), feature schema (`feat-v1`), and partition membership. |
| [`artifacts/phase5/metrics.json`](../artifacts/phase5/metrics.json) | `15.2 KB` | Point estimator metrics (`last_lab`, `deterministic_online`, `linear_process`, `gbm`) on `CALIBRATION` and `LOCKED_TEST`. |
| [`artifacts/phase6/calibrator_gbm.joblib`](../artifacts/phase6/calibrator_gbm.joblib) | `0.4 KB` | Persisted `SplitConformalCalibrator` for GBM (`split-conformal-v1:marginal_symmetric`, half-width `0.2369 g/10min`). |
| [`artifacts/phase6/calibrator_linear_process.joblib`](../artifacts/phase6/calibrator_linear_process.joblib) | `0.4 KB` | Persisted `SplitConformalCalibrator` for linear baseline (`half-width 0.3729 g/10min`). |
| [`artifacts/phase6/phase6_metrics.json`](../artifacts/phase6/phase6_metrics.json) | `16.5 KB` | Conformal coverage and interval width metrics across partitions, phases, and directions. |
| [`artifacts/phase7/applicability_detector.joblib`](../artifacts/phase7/applicability_detector.joblib) | `1.3 KB` | Persisted train-only `ApplicabilityDetector` (`applicability-v1`). |
| [`artifacts/phase7/phase7_report.json`](../artifacts/phase7/phase7_report.json) | `14.5 KB` | Sensor health fault fixtures (`A–H`), OOD fixtures (`A–G`), and train-only isolation proof. |
| [`artifacts/phase8/phase8_report.json`](../artifacts/phase8/phase8_report.json) | `20.0 KB` | Material identity resolution, boundary cases (`A–G`), mass conservation, and causality proof. |
| [`artifacts/phase9_report.json`](../artifacts/phase9_report.json) & [`artifacts/phase9/phase9_report.json`](../artifacts/phase9/phase9_report.json) | `82.0 KB` | Phase-9 disposition decision engine report + 6 canonical disposition fixtures. |
| [`artifacts/phase10/phase10_report.json`](../artifacts/phase10/phase10_report.json) | `29.1 KB` | Expected loss, discrete VOI, episode economic ledger, and 5 canonical economic fixtures (`A–E`). |
| [`artifacts/phase11/phase11_report.json`](../artifacts/phase11/phase11_report.json) | `30.8 KB` | Reconciled transition memory store, 3-analog directional retrieval, and partition/self-exclusion proofs. |
| [`artifacts/phase12/phase12_report.json`](../artifacts/phase12/phase12_report.json) | `28.5 KB` | Counterfactual replay comparison (`SOP_FIXTURE`, `POINT_THRESHOLD`, `PRIMEPATH`, `ORACLE_DIAGNOSTIC_ONLY`), event trace, determinism check, and `canonical_demo_fixture`. |

---

## 5. Summary of Locked Validation Results (`SIMULATED` — `E2`/`E3`)

- **Point Accuracy (`LOCKED_TEST`, `235` rows, `5` events):** GBM `MAE = 0.2720 g/10min`, `RMSE = 0.4353 g/10min`, `bias = -0.2337 g/10min`.
- **Calibrated Interval Coverage (`LOCKED_TEST`):** Empirical coverage `0.6596` at nominal `0.90` (`mean_width = 0.4737 g/10min`), honestly reported alongside the fact that calibration used `141` correlated rows from only `3` independent events.
- **Decision Risk (`LOCKED_TEST`):**
  - `SOP_FIXTURE`: `1,356.0 t` false-prime mass (`₹8,13,60,000` false-prime exposure in `BASE`).
  - `POINT_THRESHOLD`: `588.0 t` false-prime mass (`₹3,52,80,000` false-prime exposure in `BASE`).
  - `PRIMEPATH`: **`0.0 t` false-prime mass** (`₹0` false-prime exposure), `984.0 t` false-hold mass (`₹1,96,80,000` false-hold opportunity cost in `BASE`), `100%` abstention rate (`235 / 235` decisions).
- **Why PrimePath Abstained 100% on `LOCKED_TEST`:** Whole-event chronological splitting assigned `B->C` and `C->B` episodes to `LOCKED_TEST`, whereas `TRAIN` contained only `A->B`, `A->C`, `B->A`, and `C->A`. The train-only `ApplicabilityDetector` flagged `B->C` and `C->B` as `UNSUPPORTED` (`ood` hard gate blocked all `235` rows; `material_mapping` also blocked `40` rows). Every abstention is gate-justified (`all_abstentions_gate_justified = true`).
- **Pass/Fail Criteria:** `10 / 10` criteria passed (`all_passed = true`).

---

## 6. Current UI Status

- **Runnable:** Yes (`streamlit.testing.v1.AppTest` executes `app.py` with `0` exceptions).
- **Important Gap:** Root [`app.py`](../app.py) and [`pages/1_Grade_Transition.py`](../pages/1_Grade_Transition.py) through [`pages/6_Digital_Twin.py`](../pages/6_Digital_Twin.py) still contain the **inherited pre-PrimePath prototype UI** (which calls legacy root scripts `reactor_simulator.py`, `soft_sensor.py`, `transition_optimizer.py` and contains the legacy defects D1–D7 documented in [`FINAL_BASELINE_AUDIT.md`](FINAL_BASELINE_AUDIT.md)).
- **Theme Status:** [`gs_theme.py`](../gs_theme.py) is high quality and ready to be reused by the Phase-14 PrimePath UI views.

---

## 7. Current Demo Status

- **Domain / CLI Demo:** Complete and verified (`gradeshift.replay.demo_fixture`, accessible via `.\scripts\generate_demo.ps1` or `python scripts/generate_demo.py`).
- **Sequence:** Demonstrates an in-domain `A->B` episode progressing through:
  - `T1`: `HOLD` (point estimate in-spec `7.92`, but 90% interval `[7.48, 8.36]` crosses lower spec `7.60`; no sample available).
  - `T2`: `SAMPLE_NOW` (interval still crosses `7.60`, confirmatory sample available within `45 min` latency, positive VOI).
  - `T3`: `PRIME_RELEASE_CANDIDATE` (interval `[7.72, 8.28]` fully inside `[7.60, 8.40]`, `30 min` dwell satisfied, material `WELL_SUPPORTED`, health & applicability `NORMAL`, requires `Shift Quality Approver (QC)`).
  - `T4` (Robustness / Fault Branch): `ABSTAIN` when online analyzer freezes (`ABSTAIN_SENSOR_HEALTH`).
- **Separation:** Kept strictly separate from `LOCKED_VALIDATION` (`zero_candidate_diagnostic.separation_note`).

---

## 8. Current Known Limitations

1. **Synthetic Data Only (`E2`/`E3`):** No HMEL historian, LIMS, or financial data is present.
2. **Correlated Calibration Residuals:** `141` calibration rows come from only `3` independent episodes.
3. **Chronological Direction Shift:** `LOCKED_TEST` directions (`B->C`, `C->B`) do not appear in `TRAIN`, causing 100% gate-justified abstention on the locked corpus.
4. **Single Analyte (`MFI`):** Density is carried as static grade metadata only.
5. **UI Not Yet Wired to Domain Engine:** Streamlit pages (`app.py`, `pages/1..6`) await Phase-14 refactoring.

---

## 9. Current Repository Health & Next Development Target

- **Repository Hygiene:** Secret-scanned (0 secrets in working tree or git history), `.gitignore` hardened, reproducible `requirements.txt` and `pyproject.toml` in place, CLI scripts (`scripts/`) verified, all 266 tests passing.
- **Next Development Target (Phase 14–17):**
  1. Create `src/gradeshift/ui/` presenter layer over the frozen Phase-13 domain stack.
  2. Refactor `app.py` (PrimePath Decision Cockpit) and `pages/1..6` (Transition Replay, Quality Evidence, Disposition Workbench, Transition Guardian, Economic Ledger, Transition Memory & Model Assurance).
  3. Add UI smoke tests and finalize competition presentation assets in `competition/`.
