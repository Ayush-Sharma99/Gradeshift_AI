# Streamlit Production Deployment Incident Report — GradeShift PrimePath

- **Incident Date:** 2026-10-04
- **Product:** GradeShift PrimePath (`v0.17.0-competition-ready`)
- **Severity:** SEV-1 (Application initialization failure on Streamlit Community Cloud)
- **Status:** RESOLVED & VERIFIED

---

## 1. Exact Original Production Error

When deployed to Streamlit Community Cloud, the container provisioned **Python 3.14** (`/home/adminuser/venv/lib/python3.14/site-packages/`) and failed during initial page load with a `ModuleNotFoundError` inside `joblib/numpy_pickle.py`:

```text
app.py
    rt = get_cached_runtime()
gs_theme.py
    return _load()
src/gradeshift/ui/context.py
    gbm = GBMQualityEstimator.load(str(gbm_path))
src/gradeshift/estimator.py
    blob = joblib.load(path)
/home/adminuser/venv/lib/python3.14/site-packages/joblib/numpy_pickle.py
    ModuleNotFoundError: No module named '_loss'
```

---

## 2. Root Cause Analysis

Forensic inspection of the persisted `.joblib` pickle opcode streams (`pickletools.genops` and `NumpyUnpickler.find_class` tracing) and the deployment configuration identified a **two-part root cause**:

### Root Cause A — Cython `_loss.CyHalfSquaredError` Module Path Change in `scikit-learn >= 1.7` (Python 3.14)
1. The frozen Phase-5 estimator artifact (`artifacts/phase5/gbm_mfi.joblib`, `287,168` bytes) was serialized under the canonical validation environment:
   - `python==3.10.0`
   - `numpy==1.26.4`
   - `scipy==1.15.2`
   - `pandas==2.2.3`
   - `scikit-learn==1.6.1`
   - `joblib==1.4.2`
2. In `scikit-learn==1.6.1`, `HistGradientBoostingRegressor`'s internal Cython loss object (`HalfSquaredError.closs`) was compiled from `sklearn/_loss/_loss.pyx` with `CyHalfSquaredError.__module__ = '_loss'` (a top-level module name, rather than `'sklearn._loss._loss'`). Importing `sklearn._loss._loss` in `scikit-learn 1.6.1` registered `'_loss'` in `sys.modules['_loss']`.
3. In `scikit-learn >= 1.7` / `1.8` (installed on Python 3.14), scikit-learn changed `CyHalfSquaredError.__module__` to `'sklearn._loss._loss'` and stopped registering top-level `'_loss'` in `sys.modules`.
4. When `joblib.load("artifacts/phase5/gbm_mfi.joblib")` executed pickle opcode `STACK_GLOBAL ('_loss', 'CyHalfSquaredError')` on Python 3.14, `NumpyUnpickler.find_class('_loss', 'CyHalfSquaredError')` called `__import__('_loss')`, raising `ModuleNotFoundError: No module named '_loss'`.
5. Additionally, `gbm_mfi.joblib` pickles `numpy.core.multiarray.scalar` and `numpy.random._pickle.__bit_generator_ctor('PCG64')`, which require NumPy 1.x $\leftrightarrow$ 2.x compatibility shims when unpickled on Python 3.13/3.14 (`numpy >= 2.1`).

### Root Cause B — Missing Python Runtime Pin and Unsatisfiable `numpy<2.0.0` / Unused `torch` in `requirements.txt`
1. Neither `.python-version` nor `runtime.txt` existed in the repository root, causing Streamlit Community Cloud to default to its newest container runtime (**Python 3.14**).
2. `requirements.txt` previously specified `numpy>=1.24.0,<2.0.0` (which has no wheels for Python $\ge 3.13$ and cannot compile on Python 3.14) and included `torch>=2.0.0` (which is never imported by `src/gradeshift/`, `app.py`, or `pages/1..6`).

---

## 3. Why All Pages Appeared to Fail

All 7 Streamlit entry points (`app.py` and `pages/1_Grade_Transition.py` through `pages/6_Digital_Twin.py`) share a single cached initialization path:

```text
app.py / pages/1..6
  └── gs_theme.get_cached_runtime()          [@st.cache_resource]
        └── gradeshift.ui.context.load_runtime_context()
              ├── GBMQualityEstimator.load("artifacts/phase5/gbm_mfi.joblib")
              ├── SplitConformalCalibrator.load("artifacts/phase6/calibrator_gbm.joblib")
              └── ApplicabilityDetector.load("artifacts/phase7/applicability_detector.joblib")
```

Because `GBMQualityEstimator.load()` is the very first artifact deserialization step inside `load_runtime_context()`, its `ModuleNotFoundError` halted `get_cached_runtime()` before any page could render. No individual page logic was broken.

---

## 4. Why Local Tests Did Not Initially Catch It

Local pytest execution (`295 passed`) ran inside the canonical Python `3.10.0` environment (`scikit-learn==1.6.1`, `numpy==1.26.4`), where importing `sklearn._loss._loss` automatically populates `sys.modules['_loss']`. Until `sys.modules['_loss']` was explicitly removed in a regression test (`monkeypatch.delitem(sys.modules, "_loss")`), the `scikit-learn >= 1.7` unpickling failure did not trigger on Python 3.10.

---

## 5. Exact Fix Implemented

1. **Cross-Version Unpickling Compatibility Shims (`src/gradeshift/estimator.py`, `src/gradeshift/applicability.py`, `src/gradeshift/calibrator.py`, `src/gradeshift/ui/context.py`):**
   - Added `ensure_pickle_compat_shims()` in `src/gradeshift/estimator.py` and invoked it prior to every `joblib.load()` call:
     - Aliases `sys.modules["_loss"] = importlib.import_module("sklearn._loss._loss")` when `'_loss'` is absent from `sys.modules`, resolving `STACK_GLOBAL ('_loss', 'CyHalfSquaredError')` across `scikit-learn 1.6.x`, `1.7.x`, and `1.8.x`.
     - Aliases `numpy.core.*` to `numpy._core.*` when running on NumPy 2.x.
     - Shims `numpy.random._pickle.__bit_generator_ctor` to accept both string names (`'PCG64'`) and `BitGenerator` classes across NumPy 1.26 and 2.x.
   - Added a post-unpickle 1-row Cython prediction probe in `GBMQualityEstimator.load()` and `ApplicabilityDetector.load()`, with a deterministic canonical `TRAIN`-split refit fallback if a future Python/Cython binary struct layout change occurs across major Python versions.
   - Added explicit artifact path existence checks and runtime version diagnostics (`runtime_versions()`) in `load_runtime_context()`.
2. **Python Runtime Pinning (`.python-version` & `runtime.txt`):**
   - Added `.python-version` (`3.10`) and `runtime.txt` (`python-3.10`) so new cloud deployments provision Python 3.10.
3. **Dependency Hardening (`requirements.txt` & `pyproject.toml`):**
   - Used PEP 508 environment markers to pin exact canonical versions (`numpy==1.26.4`, `scipy==1.15.2`, `pandas==2.2.3`, `scikit-learn==1.6.1`) on `python_version < "3.13"` while allowing compatible `numpy>=2.1.0,<3.0.0` and `scikit-learn>=1.6.1,<2.0.0` wheels on `python_version >= "3.13"` (so existing Python 3.14 containers also build and run cleanly).
   - Removed unused `torch>=2.0.0` from `requirements.txt`.

---

## 6. Artifact & Runtime Compatibility Requirements

| Artifact | Path | Serialized Structure | Compatibility Mechanism |
|---|---|---|---|
| Phase-5 GBM Estimator | `artifacts/phase5/gbm_mfi.joblib` | `dict` with `HistGradientBoostingRegressor` (`_loss.CyHalfSquaredError`, `TreePredictor`, `PCG64`) | `ensure_pickle_compat_shims()` (`sys.modules["_loss"]`, `numpy.core`, `PCG64` shim) + 1-row Cython probe |
| Phase-6 Conformal Calibrator | `artifacts/phase6/calibrator_gbm.joblib` | Pure Python `dict` of primitives (`float`, `int`, `str`, `list`, `dict`) | Version-independent pure Python dictionary |
| Phase-7 Applicability Detector | `artifacts/phase7/applicability_detector.joblib` | `dict` with JSON-serializable `manifest`, `ndarray` `train_std_matrix`, and auxiliary `IsolationForest` | `ensure_pickle_compat_shims()` + `IsolationForest` decision probe |

---

## 7. Artifact Preservation vs Regeneration

- **Frozen `.joblib` and `.json` artifacts were NOT regenerated or modified.**
- Every byte of `artifacts/phase5/gbm_mfi.joblib`, `artifacts/phase6/calibrator_gbm.joblib`, `artifacts/phase7/applicability_detector.joblib`, and `artifacts/final_validation.json` remains identical to the frozen Phase-13 checkpoint.

---

## 8. Validation Fingerprint Check

All four frozen Phase-13 SHA-256 reproducibility fingerprints remain **100% unchanged**:

| Fingerprint Key | Expected / Verified SHA-256 Prefix | Status |
|---|---|---|
| `dataset_manifest` | `5abc0eb1ad93f56c` | PASS (unchanged) |
| `calibration_summary` | `3cf275c76727911a` | PASS (unchanged) |
| `locked_policy_metrics` | `a2555a4d9431c288` | PASS (unchanged) |
| `locked_economic_totals` | `6cbd173e21b7b79a` | PASS (unchanged) |

---

## 9. Deployment Smoke Test Results

| Test # | Component | Verification Target | Result |
|---|---|---|---|
| Test 1 | `RuntimeContext` | `load_runtime_context(force_reload=True)` | PASS |
| Test 2 | `GBMQualityEstimator` | `GBMQualityEstimator.load("artifacts/phase5/gbm_mfi.joblib")` (with `_loss` removed from `sys.modules`) | PASS |
| Test 3 | `SplitConformalCalibrator` | `SplitConformalCalibrator.load("artifacts/phase6/calibrator_gbm.joblib")` | PASS |
| Test 4 | `ApplicabilityDetector` | `ApplicabilityDetector.load("artifacts/phase7/applicability_detector.joblib")` | PASS |
| Test 5 | Decision Cockpit | `app.py` via headless `AppTest` | PASS |
| Test 6 | Page 1 — Transition Replay | `pages/1_Grade_Transition.py` via headless `AppTest` | PASS |
| Test 7 | Page 2 — Quality Evidence | `pages/2_Soft_Sensor.py` via headless `AppTest` | PASS |
| Test 8 | Page 3 — Disposition Workbench | `pages/3_AI_Optimizer.py` via headless `AppTest` | PASS |
| Test 9 | Page 4 — Transition Guardian | `pages/4_Safety.py` via headless `AppTest` | PASS |
| Test 10 | Page 5 — Economic Ledger | `pages/5_Economics.py` via headless `AppTest` | PASS |
| Test 11 | Page 6 — Transition Memory & Assurance | `pages/6_Digital_Twin.py` via headless `AppTest` | PASS |
| Test 12 | Interactive Controls | Mode switching (`ILLUSTRATIVE_DEMO`, `SYNTHETIC_REPLAY`, `LOCKED_VALIDATION`), `T1`–`T6` stepper, scenarios (`LOW`/`BASE`/`HIGH`), fault presets, human QC authorization | PASS |

---

## 10. Prevention Measures

1. **Automated Regression Test (`test_deployment_artifacts_and_cross_version_pickle_shims`):** Explicitly deletes `sys.modules["_loss"]` before loading `gbm_mfi.joblib` to simulate `scikit-learn >= 1.7` / Python 3.14 unpickling on every test run.
2. **Configuration Audit Test (`test_deployment_runtime_pinning_files`):** Asserts that `.python-version`, `runtime.txt`, and `requirements.txt` remain pinned and free of unused heavy dependencies (`torch`).
3. **Headless Multi-Page `AppTest` Suite (`test_ui_smoke.py`):** Exercises `app.py` and all 6 pages (`pages/1..6`) plus interactive mode/stepper transitions on every CI/test run.
