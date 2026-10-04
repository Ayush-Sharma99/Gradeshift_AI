# DEMO — GradeShift PrimePath Canonical Demo Guide

> **CRITICAL RULE:**  
> The **Illustrative Demo (`ILLUSTRATIVE_DEMO`)** and **Locked Validation (`LOCKED_VALIDATION`)** are strictly separate artifacts. Their metrics are never blended.

---

## 1. Running the Demo

### Command-Line Walkthrough

```powershell
# PowerShell (Windows)
.\scripts\generate_demo.ps1

# Or directly via Python:
python scripts/generate_demo.py
```

```bash
# Bash
bash scripts/generate_demo.sh
```

---

## 2. Canonical Illustrative Sequence (`replay.demo_fixture`)

The illustrative demo traces one seeded Grade `A -> B` (`HDPE Pipe 0.30` $\to$ `HDPE Blow Moulding 8.00`, target spec `[7.60, 8.40] g/10min`, dwell `30.0 min`, mapped window `50.0 tonnes`) across three decision timestamps plus a sensor-fault abstention branch:

### Step `T1` — Point Estimate In-Spec, Interval Crosses Limit $\to$ `HOLD`
- **State:** Point estimate `MFI = 7.92 g/10min` is inside `[7.60, 8.40]`, **but** the 90% calibrated interval `[7.48, 8.36]` crosses the lower specification limit (`7.60`), dwell (`10.0 min < 30.0 min`) is not yet satisfied, and no confirmatory sample path is active (`sample_available = False`).
- **PrimePath Action:** **`HOLD`** (`HOLD_INTERVAL_CROSSES_SPEC`, `HOLD_DWELL_INCOMPLETE`).
- **Jury Insight:** A naive point-threshold system would switch early here and risk false-prime contamination; PrimePath holds because uncertainty crosses the spec boundary.

### Step `T2` — Borderline Interval + Confirmatory Lab Sample Available $\to$ `SAMPLE_NOW`
- **State:** Point estimate `MFI = 7.95 g/10min`, 90% interval `[7.55, 8.35]` still slightly straddles the lower spec limit `7.60`, dwell (`35.0 min >= 30.0 min`) is satisfied, and a confirmatory sample can return within `45.0 min` (`<= 240.0 min` horizon).
- **PrimePath Action:** **`SAMPLE_NOW`** (`SAMPLE_INTERVAL_BORDERLINE`, `SAMPLE_WITHIN_HORIZON`).
- **Jury Insight:** PrimePath requests a targeted sample when resolving uncertainty can unlock prime candidacy within the decision horizon.

### Step `T3` — Full Interval In-Spec + Dwell + Support + Health Pass $\to$ `PRIME_RELEASE_CANDIDATE`
- **State:** Point estimate `MFI = 8.00 g/10min`, 90% interval `[7.72, 8.28]` lies **entirely inside** `[7.60, 8.40]`, dwell (`60.0 min >= 30.0 min`) is satisfied, material window (`50.0 t`) is `WELL_SUPPORTED`, sensor health is `NORMAL`, and applicability is `NORMAL`.
- **PrimePath Action:** **`PRIME_RELEASE_CANDIDATE`** (`PRIME_INTERVAL_PASS`, `PRIME_DWELL_PASS`, `PRIME_HEALTH_PASS`, `PRIME_APPLICABILITY_PASS`, `PRIME_MATERIAL_SUPPORTED`, `PRIME_CANDIDATE_REQUIRES_AUTHORIZATION`).
- **Required Approver:** `Shift Quality Approver (QC)` (valid for `30.0 min`; fallback `FOLLOW_SOP`).
- **Post-Truth Reconciliation (`BASE` scenario):** Revealed lab truth confirms `in_spec = True`; counterfactual opportunity on the `50.0 t` window is `₹10,00,000` (`50 t × ₹20,000/t` spread).

### Step `T4` (Fault / Robustness Branch) — Frozen Online Analyzer $\to$ `ABSTAIN`
- **State:** Same operating window, but `MFI_online` freezes (`SensorHealthReport.overall_state = ABNORMAL`).
- **PrimePath Action:** **`ABSTAIN`** (`ABSTAIN_SENSOR_HEALTH`), fallback `FOLLOW_SOP`.
- **Jury Insight:** Hard gates run before economics—when critical sensor health or domain support fails, PrimePath refuses to guess.

---

## 3. Why `LOCKED_VALIDATION` and `ILLUSTRATIVE_DEMO` Are Kept Separate

- In **`LOCKED_VALIDATION`** (`5` newest episodes in the chronological split: `EP-BC-01..02`, `EP-CB-00..02`), the transition directions (`B->C` and `C->B`) were never seen in `TRAIN` (`A->B`, `A->C`, `B->A`, `C->A`). The train-only `ApplicabilityDetector` therefore blocks all `235` locked decisions (`ABSTAIN`), resulting in **`0.0 t` false-prime mass** and **`0` natural prime candidates**.
- Rather than weakening the OOD gate or tampering with the chronological split to force prime candidates on the locked set, PrimePath preserves the conservative `LOCKED_VALIDATION` outcome intact and demonstrates the in-domain `A->B` candidate workflow via the explicitly labeled `ILLUSTRATIVE_DEMO` fixture.
