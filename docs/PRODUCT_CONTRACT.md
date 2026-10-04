# PRODUCT_CONTRACT — GradeShift PrimePath

> **Authoritative Product Contract Summary.**  
> Full specification: [`GradeShift_Product_Freeze_Engineering_Handoff.md`](../GradeShift_Product_Freeze_Engineering_Handoff.md).

---

## 1. Product Statement

**GradeShift PrimePath** is **an uncertainty-aware, human-authorized commercial-disposition decision layer for polyolefin grade transitions**.

- **Tagline:** *Know when it is a prime-release candidate. Prove why. Learn every transition.*
- **Core Premise:** During a polyolefin grade transition, large economic loss can occur *after* the reactor has already approached specification because quality laboratory truth (`ASTM D1238 MFI`) arrives with a `35–75 min` delay, forcing operators to conservatively hold polymer in downgrade/wide-spec routing—or, conversely, switching too early exposes prime silos to off-spec contamination.

---

## 2. Frozen Product Rules

1. **Single Primary Decision:** Commercial disposition recommendation at timestamp $t$ during a polyolefin grade transition.
2. **Primary Users:** Shift board operator and `Shift Quality Approver (QC)`.
3. **Action Vocabulary (`src/gradeshift/disposition.py`):**
   - `HOLD` (`HOLD / FOLLOW CURRENT ROUTING`)
   - `SAMPLE_NOW` (`SAMPLE NOW`)
   - `PRIME_RELEASE_CANDIDATE` (`PRIME-RELEASE CANDIDATE`)
   - `ABSTAIN` (`ABSTAIN / FOLLOW SOP`, with `FOLLOW_SOP` fallback on recommendation expiry)
4. **Distinction of "Prime" States:**
   - *Estimated reactor quality in specification:* model point estimate inside `[spec_low, spec_high]`.
   - *Associated material window likely in specification:* mapped residence-time production window inside `[spec_low, spec_high]`.
   - *Prime-release candidate (`PRIME_RELEASE_CANDIDATE`):* all 13 hard policy gates pass, full 90% calibrated interval is inside `[spec_low, spec_high]`, dwell (`30 min`) is satisfied, and human QC authorization is configured.
   - *Commercially released/certified material:* human QC / LIMS outcome under plant SOP. **PrimePath records this outcome during post-hoc reconciliation (`TransitionMemoryStore`), but never creates or certifies it.**
5. **Hard Gates Preceding Economics:** All 13 hard policy gates are evaluated before any expected-loss or VOI calculation. Any failed blocking gate forces `ABSTAIN`. Economics rank **permitted actions only** and can never resurrect a blocked action.
6. **No Silent Retraining:** `TransitionMemoryStore` stores immutable reconciled episodes for directional analog retrieval; it never performs online weight updates or silent model promotion.
7. **Strict Evidence Labeling:** Every observation, parameter, prediction, and economic value carries a `Provenance` tag (`SIMULATED`, `ASSUMPTION`, `ILLUSTRATIVE`, `MEASURED`, `PUBLICLY_VERIFIED`, `INDUSTRY_BENCHMARK`) and obeys [`CLAIMS.md`](CLAIMS.md).

---

## 3. Explicit Non-Goals & Prohibitions

PrimePath does **NOT**:
- certify polymer quality or bypass laboratory QC;
- replace DCS, APC, LIMS, or SIS;
- write reactor setpoints ($H_2/M$, temperature, pressure, catalyst feed);
- actuate plant valves or silo diverters;
- claim process-safety certification or autonomous control;
- blend `LOCKED_VALIDATION` metrics with `ILLUSTRATIVE_DEMO` outputs;
- weaken validation gates to manufacture prime candidates on synthetic data.
