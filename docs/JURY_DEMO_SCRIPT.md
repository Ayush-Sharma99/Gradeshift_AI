# JURY DEMO SCRIPT & DEFENSE GUIDE — GradeShift PrimePath

> **Target Audience:** HMEL Industrial AI Jury / Process Engineering / Quality Control / Commercial Operations  
> **Primary Entry Point:** `python -m streamlit run app.py` (Interactive UI) or `python scripts/demo.py` (CLI Backup)

---

## 1. 30-Second Elevator Pitch

> *"During polyolefin reactor grade transitions, pelletizer output flows at 50 tonnes per hour while laboratory Melt Flow Index confirmation lags by 45 to 75 minutes. Fixed-time SOP routing either downgrades good polymer or risks contaminating prime silos. A point-only soft sensor is unsafe because an in-spec point prediction can still have a wide uncertainty tail crossing the specification boundary or be out-of-domain.*
>
> *GradeShift PrimePath is a read-only, uncertainty-aware, human-authorized commercial-disposition decision layer. At every decision timestamp, it maps reactor residence time to the exact downstream pellet window, wraps a HistGBM point estimate in a 90% split-conformal interval, runs 7 sensor health checks and a train-only OOD detector, and evaluates 13 hard policy gates before economics. It recommends `HOLD`, `SAMPLE NOW`, `PRIME-RELEASE CANDIDATE` (for human QC sign-off), or `ABSTAIN / FOLLOW SOP`—and logs every reconciled outcome into an immutable Transition Memory."*

---

## 2. 90-Second Executive Pitch (Using Tab 2: `📊 Executive Value View`)

1. **Open `app.py`** — Point to the **5-Question Judge Strip** at the top of the screen:
   - Problem: `45–75 min` lab lag at `~50 t/h` production.
   - Consequence: `₹20,000/t` false-hold opportunity loss vs `₹60,000/t` false-prime contamination penalty (`BASE` scenario assumption).
   - Decision: 4 explicit actions governed by 13 hard gates first.
2. **Click Tab 2 (`📊 Executive Value View (30-Second Judge View)`)**:
   - **Left Panel (`ILLUSTRATIVE DEMO — DEMO-A2B`):** Walk through the 6 rows showing how an in-domain `A→B` transition moves from `HOLD` (`t+360m`) → `SAMPLE NOW` (`t+380m`) → `PRIME-RELEASE CANDIDATE` (`t+400m`) → `LAB TRUTH RECONCILED` (`7.95 g/10min` at `t+445m`, `₹10.0 Lakh` counterfactual spread on `50 t`) → `ABSTAIN` on a frozen analyzer fault.
   - **Right Panel (`LOCKED VALIDATION — 5 Unseen Test Episodes, 235 Decisions`):** Point out our honest headline:
     > *"100% abstention is not commercial success. It is evidence that the current model refuses unsupported transitions."*
     Show that because `LOCKED_TEST` contains unseen directions `B→C` and `C→B`, PrimePath's train-only OOD detector abstains on `235/235` rows, achieving **`0.0 tonnes` false-prime mass** vs `1,356.0 t` for `SOP_FIXTURE` and `588.0 t` for `POINT_THRESHOLD`.

---

## 3. Canonical 3-Minute Live Walkthrough (Exact Click Path)

### Step 1 — Start on `app.py` (`🎛️ Operator Decision Cockpit`, Mode: `Illustrative Demo (DEMO-A2B)`)
- **Click `T1 · HOLD` (`t = 360 min`):**
  - Point MFI is `7.92 g/10min` (inside Grade B spec `[7.60, 8.40]`).
  - **Why point-only fails:** A naive point threshold would declare prime here!
  - **Why PrimePath holds:** The 90% conformal interval `[7.48, 8.36]` crosses the lower spec bound `7.60`, and no confirmatory lab sample slot is available (`HOLD_INTERVAL_CROSSES_SPEC`, `SAMPLE_NOT_AVAILABLE`).
  - Point to **"What PrimePath Did NOT Know at t"**: future lab results (`result_at > t`) are strictly withheld (`revealed_mfi = None`).

### Step 2 — Click `T2 · SAMPLE NOW` (`t = 380 min`)
- The 90% interval `[7.55, 8.35]` still straddles `7.60`, `25 min` of dwell has accumulated, and the QC lab grab-sample slot is now available (`45 min` latency vs `240 min` decision horizon).
- Discrete Value of Information ($\text{VOI}$) is **`+₹95,000`** (`> ₹15,000` sample cost).
- **Why the action changed:** PrimePath switches from `HOLD` to **`SAMPLE NOW`** (`SAMPLE_SPEC_CROSSING`, `SAMPLE_VOI_POSITIVE`).

### Step 3 — Click `T3 · PRIME CANDIDATE` (`t = 400 min`)
- The entire 90% conformal interval `[7.72, 8.28]` now lies strictly inside `[7.60, 8.40]`.
- Required dwell (`35.0 min >= 30.0 min`), material mapping (`50.0 t`, `WELL_SUPPORTED`), sensor health (`NORMAL`), and applicability (`NORMAL`) all pass (`13/13` Hard Gates PASS, `5/5` Candidacy Gates PASS).
- **Action:** **`PRIME-RELEASE CANDIDATE`** with status **`PENDING_HUMAN_AUTHORIZATION`** (`Shift Quality Approver (QC)`).
- **Click `✅ Authorize (Demo QC)`** in the right-hand Human Quality Authority Sign-Off card to demonstrate human-in-the-loop governance (`HUMAN_AUTHORIZED_IN_DEMO`).

### Step 4 — Click `T4 · LAB TRUTH` (`t = 445 min`) & `T5 · ECON LEDGER` (`t = 445 min`)
- Delayed laboratory grab sample returns `45 minutes` after `T3` at **`7.95 g/10min`** (`was_in_spec = True`), plotted as a green star on the trajectory chart.
- The episode is reconciled in `TransitionMemoryStore` (`RECONCILED`), separating **`₹40,00,000` realized downgrade routing value** from **`₹10,00,000` (`₹10.0 Lakh`) counterfactual prime opportunity spread** (`BASE` scenario).

### Step 5 — Click `T6 · FAULT ABSTAIN` (Frozen Analyzer Fault Branch)
- Inject a frozen online MFI analyzer fault (`FROZEN_MFI` — constant reading for `35 min`).
- Even though the apparent MFI interval `[7.72, 8.28]` looks inside spec, `assess_sensor_health` flags `MFI_online = ABNORMAL`, tripping hard gate `sensor_health`.
- **Action:** Immediate **`ABSTAIN / FOLLOW SOP`** (`ABSTAIN_SENSOR_HEALTH`). Only `ABSTAIN` is permitted (`permitted_actions = ["ABSTAIN"]`).

---

## 4. 5-Minute Deep Technical Walkthrough (Specialist Pages `1..6`)

If the jury requests a deeper dive into any subsystem, click the corresponding page in the left sidebar:

1. **`1 · Transition Replay` (`pages/1_Grade_Transition.py`):**
   - Select any of the 18 corpus episodes (e.g., `EP-AB-00` in `TRAIN` or `EP-BC-01` in `LOCKED_TEST`).
   - Show the **Causal As-Of Firewall toggle** (`Reveal Future Lab Truth`): when unchecked, all future lab truth and counterfactual outcomes are masked (`None`).
   - Compare `SOP_FIXTURE`, `POINT_THRESHOLD`, `PRIMEPATH`, and `ORACLE_DIAGNOSTIC_ONLY` side-by-side.
2. **`2 · Quality Evidence` (`pages/2_Soft_Sensor.py`):**
   - Show the real `GBMQualityEstimator` (`gbm-mfi-v1`, 37 causal features) + `SplitConformalCalibrator` (`split-conformal-v1`, half-width `±0.2369 g/10min`).
   - Point out that we honestly report empirical locked coverage (`0.6596` vs `0.90` nominal) because calibration used `141` correlated rows from `3` episodes.
3. **`3 · Disposition Workbench` (`pages/3_AI_Optimizer.py`):**
   - Adjust the interactive sliders (`Lower MFI`, `Upper MFI`, `Dwell`, `Sensor Health`, `Applicability`) to prove live execution of `evaluate_disposition` and `evaluate_economics`.
4. **`4 · Transition Guardian` (`pages/4_Safety.py`):**
   - Inject any of the 6 deterministic sensor faults (`FROZEN_MFI`, `MISSING_MFI`, `STALE_MFI`, `SPIKE_MFI`, `GAP_H2`, `TIMESTAMP_DISORDER`).
   - Inspect the **11-Scenario Robustness Matrix (`11/11 PASS`)** and the **Locked Validation Abstention Decomposition (`235/235` blocked by `ood`, `40/235` by `material_mapping`)**.
5. **`5 · Economic Ledger` (`pages/5_Economics.py`):**
   - Show the **"How This Number Is Constructed"** formula table and the explicit badges: `Illustrative scenario` · `Assumption-based economics (E0/E2)` · `Not an HMEL savings claim`.
6. **`6 · Transition Memory & Assurance` (`pages/6_Digital_Twin.py`):**
   - Show top-3 directional analog retrieval (`EP-AB-00`, `EP-AB-01`, `EP-AB-02` for `DEMO-A2B`), the **Scope-Isolation Proof** (excluding self, opposite direction `B→A`, and `LOCKED_TEST`), and the **Frozen Phase-13 Claim Ledger (`E0`–`E5`)**.

---

## 5. Hostile / Jury Q&A Defense Guide

| Tough Jury Question | Exact, Honest Technical Answer |
|---|---|
| **"Why did PrimePath get 0 prime candidates (100% abstention) on your Locked Test set? Isn't that a failure?"** | *"100% abstention is not commercial success—it is verification that the model refuses to extrapolate into unsupported transition directions. Our 18-episode corpus was split chronologically by whole event: `TRAIN` (10 episodes) contained `A→B`, `B→A`, `A→C`, and `C→A`, while `LOCKED_TEST` (5 episodes, 235 rows) contained `B→C` and `C→B`. Our train-only `ApplicabilityDetector` flagged `B→C` and `C→B` as `UNSUPPORTED`, blocking all 235 rows via the `ood` hard gate. As a result, PrimePath incurred **0.0 tonnes of false-prime contamination** vs **1,356.0 tonnes** for fixed-time SOP and **588.0 tonnes** for a naive point threshold."* |
| **"How do we know you didn't leak future laboratory results into your predictions or replay?"** | *"Structural causal isolation is enforced in `alignment.py` (`as_of_event(event, t)`), which filters all process observations to `timestamp <= t` and all lab samples to `result_at <= t` (not `collected_at <= t`). This is verified by dedicated leakage tests (`tests/test_leakage_firewall.py` and `tests/test_replay.py::test_A_future_lab_no_effect`), which prove that mutating future lab truth after time $t$ produces bit-identical predictions and decisions at time $t$."* |
| **"Why is empirical conformal coverage on Locked Test 65.96% instead of 90%?"** | *"Split-conformal guarantees require exchangeability across independent calibration episodes. Our `CALIBRATION` partition has 141 decision rows drawn from only 3 episodes (`EP-BC-00`, `EP-CA-01`, `EP-CA-02`), and `LOCKED_TEST` shifts to `B→C` and `C→B`. Because within-episode residuals are temporally correlated and the test directions shift, empirical coverage drops to `0.6596`. That is precisely why our OOD applicability gate is mandatory: it blocks prime candidacy on those shifted episodes before under-covered intervals can cause a false-prime release."* |
| **"Are these ₹ Crore savings real HMEL Bathinda plant numbers?"** | *"No. Every currency figure is explicitly labeled `ASSUMPTION` (`E0`) or `SIMULATED` (`E2`) using the transparent `LOW` / `BASE` / `HIGH` parameter tables in `config.py`. We strictly separate realized routing value, counterfactual episode opportunity value, and parameterized annual scale-up projections, and never claim audited HMEL savings."* |
| **"Does PrimePath write setpoints to the DCS or switch diverter valves?"** | *"Never. PrimePath is strictly read-only and advisory. It sits above DCS/APC and alongside LIMS. Even when all 13 hard gates and 5 candidacy gates pass, its highest output is `PRIME-RELEASE CANDIDATE`, which requires human `Shift Quality Approver (QC)` sign-off under plant SOP."* |
