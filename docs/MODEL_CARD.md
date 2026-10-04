# MODEL_CARD — GradeShift PrimePath Estimation, Uncertainty & OOD Models

---

## 1. Model Inventory

| Component | Version | Implementation | Fitted On | Artifact Location |
|---|---|---|---|---|
| **Point Quality Estimator** | `gbm-mfi-v1` | `GBMQualityEstimator` (`scikit-learn` `GradientBoostingRegressor`, `n_estimators=120`, `max_depth=3`, `learning_rate=0.06`, `random_state=42`) | `TRAIN` only (`470` rows, `10` events) | [`artifacts/phase5/gbm_mfi.joblib`](../artifacts/phase5/gbm_mfi.joblib) |
| **Baseline Estimators** | `last-lab-v1`, `det-online-v1`, `linreg-mfi-v1` | `LastLabBaseline`, `DeterministicProcessBaseline`, `LinearProcessBaseline` (`Ridge(alpha=1.0)`) | `TRAIN` only (for `linreg-mfi-v1`) | [`src/gradeshift/estimator.py`](../src/gradeshift/estimator.py) |
| **Uncertainty Calibrator** | `split-conformal-v1:marginal_symmetric` | `SplitConformalCalibrator` (distribution-free split conformal prediction with finite-sample quantile $\lceil (n+1)(1-\alpha) \rceil / n$) | `CALIBRATION` only (`141` rows, `3` events) | [`artifacts/phase6/calibrator_gbm.joblib`](../artifacts/phase6/calibrator_gbm.joblib) |
| **OOD / Applicability Detector** | `applicability-v1` | `ApplicabilityDetector` (known unit + known direction check + feature range support + `IsolationForest(n_estimators=100, contamination=0.05, random_state=42)`) | `TRAIN` only (`10` events) | [`artifacts/phase7/applicability_detector.joblib`](../artifacts/phase7/applicability_detector.joblib) |

---

## 2. Intended Use & Authority Boundary

- **Intended Use:** Provide a causal point estimate and calibrated 90% prediction interval `[lower_mfi, upper_mfi]` for the Melt Flow Index (`MFI`, g/10min) of the polymer material window mapped at decision time $t$, together with an independent domain-applicability assessment (`NORMAL`, `LOW_SUPPORT`, `OOD`, `UNSUPPORTED`, `UNAVAILABLE`).
- **Non-Intended Use:** Never use point estimates alone to trigger commercial prime disposition; never treat model outputs as laboratory certification or closed-loop APC control signals.

---

## 3. Quantitative Performance (`SIMULATED` — `E2`)

### 3.1 Point Estimation (`artifacts/phase5/metrics.json`)

| Model | `CALIBRATION` MAE | `CALIBRATION` RMSE | `LOCKED_TEST` MAE | `LOCKED_TEST` RMSE | `LOCKED_TEST` Bias |
|---|---:|---:|---:|---:|---:|
| `last_lab` | `1.1328` | `1.8350` | `1.6525` | `2.4191` | `-0.3510` |
| `deterministic_online` | `0.6251` | `1.1795` | `0.9038` | `1.6216` | `-0.1930` |
| `linear_process` | `0.2189` | `0.2750` | `0.3400` | `0.4839` | `-0.0984` |
| **`gbm` (`gbm-mfi-v1`)** | **`0.1303`** | **`0.2073`** | **`0.2720`** | **`0.4353`** | **`-0.2337`** |

### 3.2 Split-Conformal Calibration (`artifacts/phase6/phase6_metrics.json`)

- **Nominal Coverage:** `0.90`
- **Selected Method (on `CALIBRATION` only):** `marginal_symmetric` (conditioning gated because `calibration_events = 3 < 5`).
- **Half-Width (`q_hat`):** `0.2369 g/10min` (`mean_width = 0.4737 g/10min`).
- **Calibration Coverage:** `0.9078` (`141` rows, `3` events).
- **Locked Test Empirical Coverage:**
  - Overall: `0.6596` (`235` rows, `5` events)
  - `PRE_BASELINE` phase: `1.0000` (`10` rows)
  - `POST_STABILIZATION` phase: `1.0000` (`54` rows)
  - `ACTIVE_TRANSITION` phase: `0.5322` (`171` rows)

---

## 4. Limitations & Failure Modes

1. **Correlated Calibration Residuals:** The `141` calibration rows come from only `3` independent transition events (`EP-BC-00`, `EP-CA-01`, `EP-CA-02`), violating row-level exchangeability across unseen transition directions and lowering active-transition empirical coverage on `LOCKED_TEST`.
2. **Unseen Transition Directions:** `ApplicabilityDetector` refuses (`UNSUPPORTED` $\to$ `ABSTAIN`) any grade transition direction not present in `TRAIN` (such as `B->C` and `C->B` in the chronological split).
3. **CPU-Only Deterministic Runtime:** Models are intentionally lightweight (`scikit-learn`) for deterministic CPU execution (`Python 3.10.0`, `numpy 1.26.4`, `scikit-learn 1.6.1`).
