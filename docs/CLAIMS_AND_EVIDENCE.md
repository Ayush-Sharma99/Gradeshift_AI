# CLAIMS AND EVIDENCE LEDGER — GradeShift PrimePath (`v0.17.0-competition-ready`)

> **Mandatory Evidence Rule:**  
> Every technical, operational, and economic statement in GradeShift PrimePath is explicitly classified on the six-level **PrimePath Evidence Ladder (`E0`–`E5`)**. No statement in the UI, CLI, or documentation may exceed **`E2` (Synthetic Simulation)** or **`E3` (Controlled Prototype)**.

---

## 1. PrimePath Evidence Ladder (`E0` – `E5`)

| Evidence Level | Label | Definition | Present in This Repository? |
|---|---|---|---|
| **`E0`** | **`ASSUMPTION`** | Explicit parameterized economic scenarios (`LOW` / `BASE` / `HIGH` prices, penalties, sample costs, annual transition counts) and plant design assumptions. | **YES** (`src/gradeshift/config.py`) |
| **`E1`** | **`THEORY / FORMULATION`** | Mathematical formulation of CSTR/Erlang residence-time distribution, split-conformal prediction, discrete VOI, and 13-gate human-authorized governance contract. | **YES** (`src/gradeshift/*.py`, `docs/PRODUCT_CONTRACT.md`) |
| **`E2`** | **`SYNTHETIC SIMULATION`** | Quantitative metrics evaluated on the seeded 18-episode synthetic corpus (`10 TRAIN`, `3 CALIBRATION`, `5 LOCKED_TEST`, `235` locked decisions). | **YES** (`artifacts/final_validation.json`) |
| **`E3`** | **`CONTROLLED PROTOTYPE`** | Deterministic software verification on controlled sensor-fault (`A–H`), OOD (`A–G`), sensitivity, VOI, and demo (`DEMO-A2B`) fixtures (`295` pytest tests). | **YES** (`tests/`, `artifacts/phase7..12/`) |
| **`E4`** | **`HISTORICAL / PUBLIC DATA`** | Retrospective replay on de-identified historical historian/LIMS plant logs. | **NO — Not claimed** |
| **`E5`** | **`INDUSTRIAL VALIDATION`** | Shadow-mode or live field deployment on an operating polyolefin unit (e.g., HMEL Bathinda). | **NO — Not claimed** |

---

## 2. Three-Way Separation of Evidence Types in UI & Reports

PrimePath strictly separates three categories of evidence so they are never conflated:

1. **Observed / Frozen Validation Evidence (`LOCKED_VALIDATION` — `E2`/`E3`):**
   - Evaluated on the 5 unseen chronological `LOCKED_TEST` episodes (`EP-BC-01`, `EP-BC-02`, `EP-CB-00`, `EP-CB-01`, `EP-CB-02`, `235` decision rows).
   - Locked with immutable SHA-256 fingerprints (`manifest:5abc0eb1ad93f56c`, `calib:3cf275c76727911a`, `policy:a2555a4d9431c288`, `econ:6cbd173e21b7b79a`).
2. **Diagnostic Oracle Benchmark (`ORACLE_DIAGNOSTIC_ONLY` — `E2` Non-Causal Hindsight):**
   - Uses future laboratory truth (`result_at > t`) solely to bound hindsight opportunity (`984.0 t` in-spec mass across `LOCKED_TEST`).
   - Explicitly labeled non-causal and never deployable as a live policy.
3. **Simulated / Illustrative Demo Evidence (`ILLUSTRATIVE_DEMO` — `E3` Controlled Walkthrough):**
   - Controlled in-domain `A→B` fixture (`DEMO-A2B`) demonstrating the full action progression (`HOLD` → `SAMPLE_NOW` → `PRIME_RELEASE_CANDIDATE` → `RECONCILED` → `ECONOMIC_LEDGER` → `FAULT_ABSTAIN`).
   - Explicitly labeled `"NOT VALIDATION EVIDENCE"` on every screen and report.

---

## 3. Master Claim Ledger (Synchronized with `artifacts/final_validation.json`)

| # | Topic | Evidence Level | Source Artifact | Allowed Wording | Prohibited Wording |
|---:|---|---|---|---|---|
| **1** | **Corpus & Data Provenance** | `E2` | `artifacts/manifests/frozen_validation_manifest.json` | *"Evaluated on a seeded 18-episode synthetic CSTR/Erlang polyolefin transition corpus (`SIMULATED`)."* | *"Validated on HMEL Bathinda plant historian or LIMS data."* |
| **2** | **Point MFI Estimation** | `E2` | `artifacts/phase5/metrics.json` | *"On the synthetic `LOCKED_TEST` split (235 rows), `GBMQualityEstimator` (`gbm-mfi-v1`) achieves `MAE = 0.2720 g/10min` (`RMSE = 0.4353 g/10min`)."* | *"Achieves 99% accuracy on industrial reactor transitions."* |
| **3** | **Conformal Uncertainty Calibration** | `E2` | `artifacts/phase6/phase6_metrics.json` | *"Split-conformal calibrator (`split-conformal-v1`, half-width `±0.2369 g/10min` from 141 calibration rows across 3 events) achieves `0.9007` calibration coverage and `0.6596` empirical coverage on direction-shifted `LOCKED_TEST`."* | *"Guarantees 90% finite-sample coverage under arbitrary distribution shift."* |
| **4** | **Sensor Health & Fault Abstention** | `E3` | `artifacts/phase7/phase7_report.json` | *"Across all 11 controlled robustness fixtures (`robustness_matrix`), critical sensor faults (`FROZEN_MFI`, `MISSING_MFI`, `STALE_MFI`, `SPIKE_MFI`, `TIMESTAMP_DISORDER`) deterministically force `ABSTAIN / FOLLOW SOP`."* | *"SIL-certified process safety system."* |
| **5** | **Locked Test OOD Abstention & False-Prime Prevention** | `E2` | `artifacts/final_validation.json` | *"100% abstention on `LOCKED_TEST` (`235/235` rows) is not commercial success; it is evidence that the train-only `ApplicabilityDetector` refuses unseen transition directions (`B→C`, `C→B`), yielding `0.0 t` false-prime mass vs `1,356.0 t` (`SOP_FIXTURE`) and `588.0 t` (`POINT_THRESHOLD`)."* | *"PrimePath automatically releases prime polymer on all transitions."* |
| **6** | **Human-Authorized Advisory Boundary** | `E1` / `E3` | `src/gradeshift/disposition.py` | *"`PRIME_RELEASE_CANDIDATE` is a read-only advisory recommendation requiring `Shift Quality Approver (QC)` sign-off; PrimePath never writes setpoints or actuates equipment."* | *"Autonomous closed-loop RL/NMPC controller or automatic silo diverter."* |
| **7** | **Episode & Annual Scenario Economics** | `E0` / `E2` | `artifacts/phase10/phase10_report.json` | *"Under explicit `BASE` scenario assumptions (`₹20,000/t` spread, `₹60,000/t` false-prime penalty), a reconciled `50.0 t` in-spec window represents `₹10.0 Lakh` in simulated counterfactual opportunity value (Not an HMEL savings claim)."* | *"Verified ₹ Crore savings delivered at HMEL Bathinda."* |
| **8** | **Transition Memory & Scope Isolation** | `E3` | `artifacts/phase11/phase11_report.json` | *"`TransitionMemoryStore` retrieves top-3 directional `TRAIN` analogs with verified self, opposite-direction, and `LOCKED_TEST` exclusion; historical context is retrieved for auditability and never silently retrains the locked evaluation."* | *"Continuous online self-learning AI that updates production thresholds automatically."* |
| **9** | **End-to-End Reproducibility** | `E3` | `artifacts/final_validation.json` | *"Bit-identical replay and validation verified across 295 pytest tests and 4 SHA-256 fingerprints (`10/10` pass/fail criteria passed)."* | *"Production-deployed enterprise software."* |
