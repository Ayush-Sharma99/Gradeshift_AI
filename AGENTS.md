# AGENTS.md — GradeShift PrimePath Agent Handoff & Operating Rules

> **CRITICAL DIRECTIVE FOR CODING AGENTS (PromptQL / Claude Code / Antigravity / Cursor):**
> **DO NOT RESTART THE PROJECT.**
> **DO NOT REWRITE THE DOMAIN STACK.**
> **DO NOT WEAKEN VALIDATION GATES TO MANUFACTURE PRIME CANDIDATES.**
>
> This repository contains the completed, tested, and frozen **GradeShift PrimePath** domain stack through **Phase 13 (Final Validation)**. Read this file, [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md), and [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) before modifying any file.

---

## 1. PROJECT IDENTITY

- **Project:** GradeShift PrimePath
- **Current Checkpoint:** Phase 13 / Final Validation complete (`v0.13.0-phase13-complete`, branch `primepath-phase13-complete`)
- **Product Definition:**
  > *"An uncertainty-aware, human-authorized commercial-disposition decision layer for polyolefin grade transitions."*
- **Tagline:** *Know when it is a prime-release candidate. Prove why. Learn every transition.*

### Core Actions (Decision Vocabulary)

PrimePath evaluates an active grade transition at decision time $t$ and recommends one of four actions (defined in `src/gradeshift/disposition.py`):

1. **`HOLD`** (*HOLD / FOLLOW CURRENT ROUTING*) — Keep routing transitional polymer to the current downgrade/wide-spec silo when specification, calibrated interval, or dwell requirements are not yet satisfied and sampling is unavailable or not justified.
2. **`SAMPLE_NOW`** (*SAMPLE NOW*) — Request a confirmatory laboratory grab sample when the calibrated prediction interval crosses a specification limit, a sample result can return within the decision horizon (`45 min` latency vs `240 min` horizon), and Value of Information ($\text{VOI}$) is positive.
3. **`PRIME_RELEASE_CANDIDATE`** (*PRIME-RELEASE CANDIDATE*) — Flag the mapped downstream material window as a candidate for prime commercial disposition when **all 13 hard policy gates pass**, the entire 90% calibrated interval lies within target grade specification limits, required dwell (`30 min`) is met, and human approval (`Shift Quality Approver (QC)`) is configured.
4. **`ABSTAIN`** (*ABSTAIN / FOLLOW SOP*) — Refuse to issue an active disposition recommendation whenever any hard gate fails (sensor health fault, out-of-domain/unsupported grade pair, ambiguous or unsupported material window mapping, missing calibration/model artifact, or timestamp disorder). Expired recommendations trigger `FOLLOW_SOP`.

### Non-Product Boundaries (What PrimePath Does NOT Do)

PrimePath is strictly **read-only and advisory**. It does **NOT**:
- certify polymer quality or commercially release product;
- replace laboratory quality authority (LIMS / ASTM D1238 QC testing);
- replace DCS, APC, or SIS;
- write reactor setpoints ($H_2/M$, temperature, pressure, catalyst feed);
- actuate plant valves, diverters, or silo routing equipment;
- claim process-safety certification or autonomous closed-loop control.

---

## 2. CURRENT ARCHITECTURE

All domain logic lives in `src/gradeshift/` (pure Python, `numpy`/`scipy`/`pandas`/`scikit-learn`). Domain modules **never** import `streamlit` (enforced by `tests/test_architecture.py`).

### End-to-End Decision Lineage

```text
data/provenance (simulate.py, ingestion.py, provenance.py, schemas.py)
  → event alignment & causal as-of firewall (events.py, alignment.py, partition.py, dataset.py)
  → material identity & residence-time mapping (material_identity.py, material_service.py)
  → causal feature engineering (features.py)
  → point quality estimation (estimator.py — GBM + last-lab / linear / deterministic baselines)
  → calibrated uncertainty (calibrator.py — split-conformal intervals on CALIBRATION only)
  → sensor health & OOD / applicability assurance (health.py, faults.py, applicability.py, assurance.py)
  → disposition decision engine (disposition.py — 13 hard gates FIRST, then action selection)
  → expected loss, discrete VOI & economic ledger (economics.py — ranks PERMITTED actions only)
  → immutable transition memory & analog retrieval (memory.py — directional, partition-isolated)
  → counterfactual replay under future-truth firewall (replay.py — SOP / Point / PrimePath / Oracle)
  → final validation & claim ledger (validation.py, pipeline.py)
  → UI presenter & Streamlit views (Next Phase: Phase 14+)
```

---

## 3. IMPORTANT CURRENT TRUTH & EVIDENCE RULES

1. **Current validation is 100% synthetic (`E2` / `E3` ceiling):**
   - `E0`: Assumption
   - `E1`: Theory / formulation
   - `E2`: Synthetic simulation
   - `E3`: Controlled prototype
   - `E4`: Historical / public-data validation *(not yet performed)*
   - `E5`: Industrial plant validation *(not yet performed)*
2. **No HMEL plant data:** No operating historian tags, LIMS logs, or financial ledgers from HMEL Bathinda were used.
3. **No industrial validation, safety certification, or autonomous control:** Never claim PrimePath is "plant-proven", "HMEL-validated", "safety-certified", or an "autonomous RL/NMPC controller".
4. **No verified HMEL savings:** Economic figures (`LOW` / `BASE` / `HIGH` scenarios in `src/gradeshift/config.py`) are explicit `ASSUMPTION` / `SIMULATED` scenario calculations, never measured plant savings.
5. **Locked evaluation must remain frozen:**
   - The locked corpus (`5` locked test events, `235` labeled decision rows) yields **100% PrimePath abstention (`235 / 235` decisions) and `0` natural prime candidates** because the chronological `TRAIN` split (`10` events) covers directions `A->B`, `A->C`, `B->A`, `C->A`, whereas the chronological `LOCKED_TEST` split (`5` events) comprises `B->C` and `C->B`, which the train-only `ApplicabilityDetector` rightly flags as `UNSUPPORTED` (`ood` hard gate blocks all `235` rows; `material_mapping` additionally blocks `40` rows).
   - **Result:** PrimePath achieves **`0.0 t` false-prime mass** vs `1356.0 t` for `SOP_FIXTURE` and `588.0 t` for `POINT_THRESHOLD`, at an explicit false-hold opportunity cost of `984.0 t` (`₹1.968 Cr` in `BASE` scenario).
   - **This conservative abstention is a verified validation finding, NOT a bug to "fix" or hide.**
6. **Illustrative demo must remain strictly separate:**
   - The canonical `A->B` walkthrough (`HOLD` → `SAMPLE_NOW` → `PRIME_RELEASE_CANDIDATE`, plus fault-triggered `ABSTAIN`) is generated by `gradeshift.replay.demo_fixture` (`ILLUSTRATIVE_DEMO`).
   - **Never blend `LOCKED_VALIDATION` metrics with `ILLUSTRATIVE_DEMO` outputs.**

### Mandatory Engineering Rule

> **DO NOT weaken validation gates, relax OOD direction checks, alter partition boundaries, or tune thresholds on locked test events merely to inflate candidate rates or demo metrics.**

---

## 4. CURRENT REMAINING DEVELOPMENT (PHASE 14–17)

The domain stack (Phases 0–13) is complete. Remaining work for future coding agents is strictly in the presentation, UI integration, and competition packaging layer:

1. **UI Service & Presenter Layer (`src/gradeshift/ui/`):**
   - Build a clean presenter layer that loads/caches frozen artifacts and exposes UI-ready objects from `src/gradeshift/` without putting business logic inside Streamlit pages.
2. **Operator UI (`app.py` + `pages/`):**
   - Refactor root `app.py` into the **PrimePath Decision Cockpit** (current recommendation, point + conformal interval vs spec band, mapped material window, sensor health & OOD assurance, 13 hard policy gates table, expected-loss & VOI table, human QC approval card, provenance badge).
   - Repurpose `pages/1..6` (using the visual design tokens in `gs_theme.py`) into:
     1. *Transition Replay* (timeline, material window, laboratory blind window, policy comparison)
     2. *Quality Evidence* (real GBM estimator + split-conformal intervals + delayed lab reconciliation; remove the legacy `np.random.normal` mock)
     3. *Disposition Workbench* (actions, expected loss, VOI, reason codes, human approval workflow)
     4. *Transition Guardian* (sensor health checks, OOD applicability, hard gates, abstention decomposition)
     5. *Economic Ledger* (`LOW`/`BASE`/`HIGH` episode mass/value accounting, realized vs counterfactual separation, scenario scale-up calculator)
     6. *Transition Memory & Model Assurance* (immutable reconciled episodes, 3-analog directional retrieval, frozen validation report & claim ledger)
   - Archive the legacy root scripts (`reactor_simulator.py`, `soft_sensor.py`, `transition_optimizer.py`) once the UI pages no longer import them (copies are already preserved in `historical/legacy_prototype/` and `experiments/legacy_control_counterfactual.py`).
3. **Executive Value View & Final Demo (`scripts/`):**
   - One-command canonical demo walkthrough (`HOLD` → `SAMPLE_NOW` → `PRIME_RELEASE_CANDIDATE` + frozen-sensor `ABSTAIN` branch) and UI smoke tests.
4. **Competition Presentation Assets (`competition/`):**
   - Final jury defense brief, slide alignment notes, and screenshot/demo package grounded strictly in `docs/CLAIMS.md`.

---

## 5. KEY DIRECTORIES & ARTIFACT LOCATIONS

| Path | Role |
|---|---|
| `src/gradeshift/` | Authoritative PrimePath domain package (21 modules, Phases 1–13) |
| `tests/` | 20 pytest modules (266 unit, integration, causal-firewall, leakage, and validation tests) |
| `artifacts/final_validation.json` | Canonical Phase-13 final validation JSON output (also archived in `artifacts/final_validation/final_validation.json`) |
| `artifacts/manifests/` | Frozen validation manifest (`frozen_validation_manifest.json`) & Phase-5 dataset/feature manifest (`phase5_manifest.json`) |
| `artifacts/phase5/` | Persisted GBM estimator (`gbm_mfi.joblib`), `manifest.json`, `metrics.json` |
| `artifacts/phase6/` | Persisted conformal calibrators (`calibrator_gbm.joblib`, `calibrator_linear_process.joblib`) & `phase6_metrics.json` |
| `artifacts/phase7/` | Persisted OOD detector (`applicability_detector.joblib`) & `phase7_report.json` |
| `artifacts/phase8/` | Material identity & residence-time resolution report (`phase8_report.json`) |
| `artifacts/phase9/` | Disposition decision engine report (`phase9_report.json`, also at `artifacts/phase9_report.json`) |
| `artifacts/phase10/` | Expected loss, VOI, and economic ledger report (`phase10_report.json`) |
| `artifacts/phase11/` | Transition memory & analog retrieval report (`phase11_report.json`) |
| `artifacts/phase12/` | Counterfactual replay report (`phase12_report.json`) |
| `docs/` | Product contract, architecture, current state, final validation report, claims ledger, data/model/policy cards, limitations |
| `scripts/` | CLI entry points for testing, validation regeneration, demo inspection, and launching the Streamlit app |
| `experiments/` | Non-core counterfactual control experiments (`legacy_control_counterfactual.py`) |
| `historical/` | Historical submission PDF, forensic audit, deprecated controller prompt, and legacy prototype snapshot |
| `competition/` | Directory reserved for future competition presentation and demo assets |

---

## 6. MAJOR ENTRY POINTS & COMMANDS

### Run the Test Suite

```powershell
# PowerShell (Windows)
.\scripts\test.ps1

# Or directly via Python:
python -m pytest -v
```

```bash
# Bash (Linux / macOS / Git Bash)
bash scripts/test.sh
```

> **Runtime Note:** The full 266-test suite runs end-to-end pipeline training, conformal calibration, replay, and Phase-13 validation fixtures. Real runtime on a standard CPU laptop is **~6.5 minutes (`394s`)**. Do not mistake a 60-second CLI tool timeout for a test failure. For a fast unit test run excluding the heavy pipeline regeneration fixtures, run:
> ```powershell
> python -m pytest -k "not test_final_validation and not test_calibration_reproducible and not test_reproducible_pipeline"
> ```

### Regenerate / Verify Phase-13 Validation Package

```powershell
.\scripts\validate.ps1
# Or directly:
python scripts/validate.py
```

### Run Canonical Illustrative Demo (CLI)

```powershell
.\scripts\generate_demo.ps1
# Or directly:
python scripts/generate_demo.py
```

### Launch the Streamlit Application

```powershell
.\scripts\run_app.ps1
# Or directly:
python -m streamlit run app.py
```
*(Note: Until Phase 14 UI refactoring is executed, `app.py` and `pages/1..6` render the inherited legacy dashboard surface. `gs_theme.py` provides the reusable styling system for the Phase 14 PrimePath views.)*

---

## 7. KNOWN LIMITATIONS

1. **Synthetic Corpus Only (`E2`/`E3`):** All process trajectories, analyzer lags, and laboratory results are generated by the seeded CSTR/Erlang synthetic generator (`src/gradeshift/simulate.py`).
2. **Small Calibration Event Count:** Conformal calibration uses `141` rows drawn from only `3` independent calibration events (`EP-BC-00`, `EP-CA-01`, `EP-CA-02`), resulting in correlated residuals and empirical locked coverage of `0.6596` at nominal `0.90`.
3. **Direction Shift Across Chronological Partitions:** Because the 18-event corpus is split chronologically by whole event, `LOCKED_TEST` contains `B->C` and `C->B` transitions not present in `TRAIN`, causing the `ApplicabilityDetector` to block all `235` locked decisions (`ABSTAIN`).
4. **Single-Property Scope:** The POC models Melt Flow Index (`MFI`, g/10min) only; density (`g/cm³`) is carried as grade context only.
5. **Advisory Scope:** PrimePath does not interface with live OPC/DCS tags or LIMS databases in this repository.
