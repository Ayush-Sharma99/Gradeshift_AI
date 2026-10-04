# COMPETITION READINESS — GradeShift PrimePath (`v0.17.0-competition-ready`)

> **Product Definition:**  
> *"An uncertainty-aware, human-authorized commercial-disposition decision layer for polyolefin grade transitions."*
>
> **Tagline:**  
> *"Know when it is a prime-release candidate. Prove why. Learn every transition."*

---

## 1. Executive Competition Summary

**GradeShift PrimePath** is a complete, end-to-end, reproducible industrial decision-support software system built to solve a specific, high-consequence problem in continuous polyolefin manufacturing: **commercial polymer disposition during reactor grade transitions under laboratory measurement lag.**

Every element of the system is wired to real, deterministic Python domain logic (`src/gradeshift/`), backed by frozen validation artifacts (`artifacts/`), exposed through a clean presenter architecture (`src/gradeshift/ui/`), rendered in a seven-screen Streamlit Decision Cockpit (`app.py` + `pages/1..6`), and verified by **295 automated pytest tests** (`tests/`).

---

## 2. The Five Judge Questions Answered Immediately

When the PrimePath Decision Cockpit (`app.py`) opens, the top **30-Second Judge Strip** immediately answers the five questions an HMEL industrial jury asks first:

| # | Jury Question | PrimePath Answer |
|---:|---|---|
| **1** | **WHAT IS THE PROBLEM?** | During polyolefin grade transitions, laboratory MFI confirmation lags reactor production by **45–75 minutes** while pelletizer output flows at **~50 t/h** (`~37–62 t` per blind window). |
| **2** | **WHY DOES IT MATTER?** | Fixed-time SOP routing either downgrades good prime polymer (**false hold**: `₹20,000/t` spread in `BASE`) or risks shipping off-spec transition polymer as prime (**false prime**: `₹60,000/t` contamination penalty in `BASE`). |
| **3** | **WHAT DOES PRIMEPATH DECIDE?** | At each 10-minute decision timestamp $t$, PrimePath evaluates 13 hard policy gates first and recommends one of four actions: **`HOLD / FOLLOW CURRENT ROUTING`**, **`SAMPLE NOW`**, **`PRIME-RELEASE CANDIDATE`**, or **`ABSTAIN / FOLLOW SOP`**. |
| **4** | **WHAT EVIDENCE SUPPORTS THE DECISION?** | Causal as-of slice (`result_at <= t`), CSTR/Erlang residence-time material window (`50.0 t`), `HistGBM` point estimate + `90%` split-conformal interval, 7-check sensor health, and train-only OOD applicability. |
| **5** | **WHAT HAPPENS WHEN EVIDENCE IS BAD?** | Any failed hard gate (frozen/missing/stale analyzer, timestamp disorder, unseen transition direction `B→C` / `C→B`, or unsupported material mapping) immediately forces **`ABSTAIN / FOLLOW SOP`** regardless of economic upside. |

---

## 3. End-to-End 10-Stage Decision Lineage Chain

Every decision rendered in the UI and CLI follows the exact 10-stage auditable lineage chain:

```text
1. EVIDENCE (Causal As-Of Firewall, result_at <= t)
   → 2. UNCERTAINTY (HistGBM Point + 90% Split-Conformal Interval)
   → 3. MATERIAL IDENTITY (Residence-Time Window, Mass & Route Support)
   → 4. HEALTH / APPLICABILITY (7 Sensor Checks + Train-Only OOD Detector)
   → 5. POLICY GATES (13 Hard BLOCK Gates Evaluated FIRST + 5 Candidacy Gates)
   → 6. DISPOSITION (HOLD | SAMPLE_NOW | PRIME_RELEASE_CANDIDATE | ABSTAIN)
   → 7. HUMAN AUTHORIZATION (Shift Quality Approver (QC) Mandatory Sign-Off)
   → 8. ECONOMIC CONSEQUENCE (Expected Loss & Discrete VOI Over Permitted Actions Only)
   → 9. RECONCILIATION (Delayed Lab Truth Arrival Post-Decision)
   → 10. MEMORY (Immutable Append-Only Episode Store & 3-Analog Directional Retrieval)
```

---

## 4. Non-Negotiable Product Contract & Safety Boundaries

1. **Strictly Advisory & Read-Only:** PrimePath never writes reactor setpoints ($H_2/M$, temperature, pressure, catalyst feed), never actuates plant diverter valves or silo routing equipment, and never replaces DCS, APC, SIS, or LIMS laboratory authority.
2. **Human / QC Authorization Required:** `PRIME_RELEASE_CANDIDATE` is never presented as "certified", "approved", or "commercially released". It is an auditable candidate requiring explicit `Shift Quality Approver (QC)` sign-off.
3. **Hard Policy Gates Dominate Economics:** All 13 hard blocking gates (`disposition.py`) are evaluated before any economic calculation. When a hard gate fails, `permitted_actions == ("ABSTAIN",)`, and neither expected-loss ranking nor human authorization state can override `ABSTAIN`.
4. **Strict Separation of Operating Modes:**
   - `ILLUSTRATIVE_DEMO` (`DEMO-A2B`): Controlled in-domain `A→B` walkthrough demonstrating `HOLD` → `SAMPLE_NOW` → `PRIME_RELEASE_CANDIDATE` → `RECONCILED` → `ECONOMIC_LEDGER` → `FAULT_ABSTAIN`.
   - `SYNTHETIC_REPLAY`: Interactive counterfactual replay across all 18 seeded corpus episodes under the structural `as_of_event` temporal firewall.
   - `LOCKED_VALIDATION`: Read-only inspection of the frozen 5-episode `LOCKED_TEST` evaluation (`235` decisions, `100%` OOD-gated abstention, `0.0 t` false-prime mass).

---

## 5. One-Command Reproducibility & Verification

| Task | Command | Expected Output / Runtime |
|---|---|---|
| **Launch Interactive UI** | `python -m streamlit run app.py` (or `.\scripts\run_app.ps1`) | Opens PrimePath Decision Cockpit + 6 specialist pages |
| **Run CLI Jury Demo** | `python scripts/demo.py` (or `.\scripts\demo.ps1`) | Prints 6-step `DEMO-A2B` walkthrough + Locked Validation + SHA fingerprints (`< 3s`) |
| **Verify Frozen Validation** | `python scripts/validate.py --verify-only` | Verifies all 4 SHA-256 fingerprints & `10/10` pass/fail criteria (`< 2s`) |
| **Fast Unit + UI + Smoke Tests** | `python -m pytest -k "not test_final_validation and not test_calibration_reproducible and not test_reproducible_pipeline"` | `283 passed` in `~35s` |
| **Full End-to-End Test Suite** | `python -m pytest -v` (or `.\scripts\test.ps1`) | `295 passed, 0 failed` (`~7 min` including full pipeline rebuilds) |
