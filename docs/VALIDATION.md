# VALIDATION — GradeShift PrimePath Validation Protocol & Summary

> **Complete Machine & Human Validation Outputs:**  
> - JSON package: [`artifacts/final_validation.json`](../artifacts/final_validation.json)  
> - Rendered report: [`docs/FINAL_VALIDATION_REPORT.md`](FINAL_VALIDATION_REPORT.md)

---

## 1. Validation Design Principles

1. **Whole-Event Chronological Split (`partition.py`):**
   - Total synthetic corpus: `18` transition events (`3` episodes per direction across `6` directions: `A->B`, `B->A`, `A->C`, `C->A`, `B->C`, `C->B`, seed `42`).
   - `TRAIN`: `10` earliest events (`470` labeled rows) — `EP-AB-00..02`, `EP-AC-00..02`, `EP-BA-00..02`, `EP-CA-00`.
   - `CALIBRATION`: `3` middle events (`141` labeled rows) — `EP-BC-00`, `EP-CA-01`, `EP-CA-02`.
   - `LOCKED_TEST`: `5` latest events (`235` labeled rows) — `EP-BC-01`, `EP-BC-02`, `EP-CB-00`, `EP-CB-01`, `EP-CB-02`.
2. **Strict Partition Isolation:**
   - `GBMQualityEstimator` and `LinearProcessBaseline` fit on `TRAIN` only.
   - `ApplicabilityDetector` fits on `TRAIN` only.
   - `SplitConformalCalibrator` fits and selects its method (`marginal_symmetric`) on `CALIBRATION` only.
   - `TransitionMemoryStore` retrieval is scoped to `Partition.TRAIN` only (`LOCKED_TEST` and self-event IDs are structurally excluded).
   - `LOCKED_TEST` is evaluated once with frozen artifacts; no hyperparameter, threshold, or gate is tuned on `LOCKED_TEST`.
3. **Strict Separation of `LOCKED_VALIDATION` vs `ILLUSTRATIVE_DEMO`:**
   - `LOCKED_VALIDATION` evaluates the frozen `5` locked test events without intervention.
   - `ILLUSTRATIVE_DEMO` (`replay.demo_fixture`) is a separate, explicitly labeled fixture illustrating the `HOLD` $\to$ `SAMPLE_NOW` $\to$ `PRIME_RELEASE_CANDIDATE` sequence on an in-domain `A->B` episode. Their metrics are never combined.

---

## 2. Three-Level Evaluation Hierarchy

### Level A — Quality Estimation & Uncertainty (`LOCKED_TEST`)
- **Point Metrics (`235` rows, `5` events):**
  - `gbm` (`gbm-mfi-v1`): `MAE = 0.2720 g/10min`, `RMSE = 0.4353 g/10min`, `bias = -0.2337 g/10min`
  - `linear_process`: `MAE = 0.3400 g/10min`, `RMSE = 0.4839 g/10min`
  - `deterministic_online`: `MAE = 0.9038 g/10min`, `RMSE = 1.6216 g/10min`
  - `last_lab`: `MAE = 1.6525 g/10min`, `RMSE = 2.4191 g/10min`
- **Uncertainty Calibration (`split-conformal-v1:marginal_symmetric`):**
  - Nominal coverage: `0.90`
  - Calibration empirical coverage: `0.9078` (`141` rows across `3` calibration events)
  - Locked empirical coverage: `0.6596` (`235` rows across `5` locked events), mean interval width `0.4737 g/10min`.
  - Subgroup conditioning was gated (`conditioning_gated = true`) because `calibration_events = 3 < 5` (`MIN_EVENTS_FOR_CONDITIONING`).

### Level B — Decision Risk (`LOCKED_TEST` Counterfactual Replay)
- Compares four policies at identical decision timestamps under the `as_of_event` future-truth firewall:
  1. `SOP_FIXTURE` (time-based switching fixture): `1,356.0 t` false-prime mass, `0.0 t` false-hold mass.
  2. `POINT_THRESHOLD` (switches when point estimate enters spec, ignoring interval/gates): `588.0 t` false-prime mass, `0.0 t` false-hold mass.
  3. `PRIMEPATH` (full Phase-9/10 stack): **`0.0 t` false-prime mass**, `984.0 t` false-hold mass (`82` false-hold decisions), `1.00` abstention rate (`235 / 235` decisions).
  4. `ORACLE_DIAGNOSTIC_ONLY` (uses future lab truth as an unachievable diagnostic bound): `0.0 t` false-prime mass, `0.0 t` false-hold mass.

### Level C — Episode Economic Accounting (`LOCKED_TEST`, `BASE` Scenario)
- `SOP_FIXTURE`: `₹8,13,60,000` false-prime exposure, `₹8,29,20,000` gross avoidable loss.
- `POINT_THRESHOLD`: `₹3,52,80,000` false-prime exposure, `₹3,63,28,000` gross avoidable loss.
- `PRIMEPATH`: **`₹0` false-prime exposure**, `₹1,96,80,000` false-hold opportunity cost, `₹20,85,00,000` realized downgrade-route value, `₹1,96,80,000` counterfactual opportunity value.

---

## 3. Abstention Decomposition & Fail-Safe Verification

- **Locked Corpus Abstention Decomposition:**
  - `total_decisions`: `235`
  - `abstained_decisions`: `235` (`100%`)
  - `blocking_by_category`: `{"material_mapping": 40, "ood": 235}` (`40` multi-gate decisions blocked by both `material_mapping` and `ood`).
  - `all_abstentions_gate_justified`: `true`.
- **11-Scenario Robustness Matrix (`all_match = true`):**
  - Verifies deterministic fail-safe behavior across `normal_evidence` (`PRIME_RELEASE_CANDIDATE`), `missing_sensor` (`ABSTAIN`), `frozen_sensor` (`ABSTAIN`), `stale_data` (`ABSTAIN`), `timestamp_disorder` (`ABSTAIN`), `ood_shift` (`ABSTAIN`), `unknown_grade_pair` (`ABSTAIN`), `ambiguous_routing` (`ABSTAIN`), `incomplete_material_mapping` (`ABSTAIN`), `unavailable_calibration` (`ABSTAIN`), and `expired_recommendation` (`FOLLOW_SOP`).

---

## 4. Reproducibility Fingerprints & Acceptance Gates

| Artifact / Component | Fingerprint |
|---|---|
| Frozen Manifest | `manifest:5abc0eb1ad93f56c` |
| Conformal Calibrator | `calib:3cf275c76727911a` |
| Disposition Policy | `policy:a2555a4d9431c288` |
| Economic Scenarios | `econ:6cbd173e21b7b79a` |
| Replay Determinism (`A == B`) | `13acf6841c4621b6` (`identical = true`) |

All 10 pass/fail acceptance criteria in `final_validation.json#pass_fail_criteria` evaluate to `true`.
