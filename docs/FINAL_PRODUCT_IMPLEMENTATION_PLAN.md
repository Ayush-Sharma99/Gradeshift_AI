# FINAL PRODUCT IMPLEMENTATION PLAN — GradeShift PrimePath

**The implementation contract for this build.** Precedes major code (per the
master directive). Pairs with [`FINAL_BASELINE_AUDIT.md`](FINAL_BASELINE_AUDIT.md).

> **GradeShift PrimePath** — an uncertainty-aware, human-authorized
> commercial-disposition decision layer for polyolefin grade transitions.
> *Know when it is a prime-release candidate. Prove why. Learn every transition.*

PrimePath does **not** certify quality, replace the lab/DCS/APC/SIS, or write
setpoints. It recommends one of: **HOLD / SAMPLE NOW / PRIME-RELEASE CANDIDATE /
ABSTAIN**, with calibrated evidence, and requires human authorization.

---

## 1. Package architecture

Domain logic is pure Python (numpy/pandas/scikit-learn), fully decoupled from
Streamlit. UI calls services; UI never computes a decision.

```
src/gradeshift/
  config/         # grades, specs, economics, policy thresholds (single source of truth)
  schemas/        # typed dataclasses: ProvenancedObservation, LabSample, RoutingInterval,
                  #   GradeSpecification, TransitionEvent, MaterialWindow, PredictionBundle,
                  #   DecisionSnapshot, TransitionOutcome, TransitionMemoryRecord + provenance enum
  simulate/       # seeded synthetic episode generator (ex reactor_simulator), calibrated
  ingestion/      # provenance tagging + UTC time normalization
  events/         # TransitionEvent builder; collected_at vs result_at separation
  material/       # residence-time / transport mapper (CSTR + Erlang), mass integration
  features/       # deterministic, train-fitted feature pipeline (lags, slopes, rolling)
  estimation/     # baselines (last-lab, lag, linear) + GBM point estimator; versioned artifacts
  uncertainty/    # split-conformal / CQR calibrator; coverage reporting
  health/         # sensor health checks (missing/stale/frozen/range/rate/timestamp)
  ood/            # applicability: unseen grade-pair/unit, feature distance, IsolationForest
  decision/       # pure expected-loss policy engine + hard gates + VOI + reason codes
  economics/      # episode mass/value ledger, LOW/BASE/HIGH scenarios, provenance-tagged
  memory/         # immutable transition memory store + directional analog retrieval
  replay/         # deterministic counterfactual replay (SOP / last-lab / point / PrimePath / oracle)
  assurance/      # dataset/model/calibration/policy/economics versioning + manifest hashes
  validation/     # chronological whole-event splits, locked eval, metrics, robustness
  ui/             # presenter helpers shared by Streamlit pages
experiments/
  legacy_control_counterfactual.py   # ex transition_optimizer (no RL label)
scripts/          # generate-data, split, train, calibrate, fit-ood, evaluate, demo
tests/            # unit / integration / leakage / robustness / smoke
docs/             # all specification + evidence documents
```

**Dependency direction:** `ui → services → schemas/config`. Domain packages must
never import streamlit (enforced by an architecture test).

---

## 2. Data flow (the decision lineage)

```
SEEDED SYNTHETIC SOURCE (labelled SIMULATED)
  → provenance + UTC normalization
  → TransitionEvent (immutable; process series, lab samples w/ collected_at & result_at, routing)
  → MaterialWindow (residence-time map: what material is at the decision point, + mapping uncertainty)
  → feature pipeline (fitted on TRAIN only, frozen)
  → point quality estimate
  → calibrated prediction interval (conformal, fitted on CALIBRATION only)
  → sensor health + OOD/applicability states
  → POLICY GATES (hard) → expected-loss minimization over allowed actions → VOI for SAMPLE NOW
  → DecisionSnapshot (action, reasons, EL table, approver, expiry, fallback, all versions)
  → human authorization (recorded, not synthesized)
  → reveal later lab truth → OutcomeReconciliation
  → economic ledger (mass × price deltas; false-prime vs false-hold separated)
  → immutable TransitionMemoryRecord (eligible for analog retrieval only after reconciliation)
```

---

## 3. Key design decisions (and rationale)

1. **Single-property synthetic model, calibrated so steady state == target.**
   Fixes defect D1 at the source. The generator maps a hydrogen-ratio setpoint to
   an *instantaneous* MFI whose target setpoint yields exactly the target MFI, then
   applies first-order (CSTR) bed washout + transport delay. Erlang (tanks-in-series)
   offered as an option. This is enough physics to make residence time and material
   identity real; no Method-of-Moments fiction. Labelled SIMULATED everywhere.
2. **scikit-learn GradientBoosting as the estimator; torch stays optional.**
   CPU-friendly, deterministic with fixed seed, fast on a laptop (R7). A temporal
   model is added only if it beats the GBM on locked decision metrics.
3. **Split conformal regression for intervals.** Simple, distribution-free marginal
   coverage; CQR as an upgrade if width is poor. Coverage reported by grade
   direction and transition phase; limitations under shift documented.
4. **Expected-loss decision engine is a pure function.** `decide(context) ->
   DecisionSnapshot`. Hard gates run before minimization; any gate failure → ABSTAIN.
   Fully unit-tested across all branches. No numbers hard-coded — all from config.
5. **Whole-event chronological splitting.** Train = earliest episodes, Calibration =
   middle, Locked Test = newest. A leakage test asserts no event_id spans partitions
   and that calibration/holdout never touch model fitting or analog retrieval.
6. **Everything versioned + hashed.** `assurance` stamps every DecisionSnapshot with
   data/feature/model/calibration/ood/policy/economics versions.

---

## 4. Canonical demo (computed, never scripted)

One seeded Grade A→B transition. The HOLD→SAMPLE NOW→PRIME-RELEASE CANDIDATE→
(reveal)→counterfactual value→memory→ABSTAIN sequence must *emerge* from the
decision engine on the frozen episode. If it does not emerge, we transparently
re-tune the **generator** before locking — never the outcome or the engine.

---

## 5. Validation plan

- Partition by whole transition event, chronological. Freeze seeds + manifest
  hashes + specs + economics before opening the locked test.
- **Baselines:** SOP timing fixture · last-lab carry-forward · point-estimate
  threshold (no uncertainty) · PrimePath · oracle (diagnostic only).
- **Metrics:** MAE/RMSE/bias; 90% empirical coverage + width (overall + subgroup);
  false-prime rate & mass; false-hold rate/duration/mass; sample rate & useful
  fraction; abstention rate; risk-coverage; expected vs realized regret; net value.
- **Robustness fixtures:** missing/stale/frozen/biased sensor; late/missing lab;
  unseen grade pair; OOD regime; changed residence time; routing gaps; missing spec.
- **Acceptance gates:** reproducible from one command; no leakage; honest coverage;
  PrimePath false-prime ≤ SOP baseline on locked replay; positive net value after
  all costs; OOD/critical-sensor force ABSTAIN in tests.

---

## 6. Phase plan & exit criteria

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **0** | Baseline audit + this plan | Committed ✔ |
| **1** | `config` + `schemas` (typed, validated) | Schema round-trip + invalid-data tests pass |
| **2** | Seeded synthetic generator (calibrated on-spec) + ingestion/provenance + UTC | Steady state == target; provenance labels propagate |
| **3** | TransitionEvent builder + time alignment (collected_at vs result_at) | Alignment + leakage-structure tests pass |
| **4** | Material identity mapper (CSTR/Erlang + mass integration) | Mass-conservation + window-provenance tests pass |
| **5** | Feature pipeline + baselines + GBM estimator (persisted) | Event-level validation report generated |
| **6** | Conformal uncertainty calibrator | Coverage/width artifact + tests pass |
| **7** | Sensor health + OOD states + hard gates | Fault fixtures force expected states/actions |
| **8** | Decision engine (actions, EL, VOI, reasons, expiry, fallback) | Decision-table tests cover all branches |
| **9** | Economic ledger (LOW/BASE/HIGH, provenance) | Unit-consistent accounting tests pass |
| **10** | Transition memory + directional retrieval | Retrieval + holdout-isolation tests pass |
| **11** | Counterfactual replay engine | Deterministic replay artifact |
| **12** | Validation suite + locked eval + robustness | Machine- + human-readable reports exist |
| **13** | PrimePath Cockpit (app.py) | Smoke test + screenshot checklist |
| **14** | Replay / Quality Evidence / Workbench / Guardian pages | No disconnected values; smoke passes |
| **15** | Economic Ledger + Transition Memory/Assurance pages | Every number traces to input+formula |
| **16** | One-command demo + abstention branch | Clean-run demo, no manual edits |
| **17** | Evidence package: README, data/model/policy cards, claim ledger, assumption + limitation registers, jury defense, demo scripts | Artifact index links every claim to evidence |

Each phase ends with a report: WHAT CHANGED · WHY · FILES · TESTS · RESULTS ·
EVIDENCE · LIMITATIONS · NEXT · RISKS.

---

## 7. Documentation set (to be produced)

`README.md`, `docs/FINAL_PRODUCT_SPEC.md`, `docs/DATA_CONTRACT.md`,
`docs/DECISION_ENGINE.md`, `docs/UNCERTAINTY_METHOD.md`,
`docs/VALIDATION_PROTOCOL.md`, `docs/ECONOMIC_MODEL.md`, `docs/FAILURE_MODES.md`,
`docs/CLAIM_EVIDENCE_MATRIX.md`, `docs/ASSUMPTION_REGISTER.md`,
`docs/LIMITATIONS.md`, `docs/FINAL_DEMO_SCRIPT.md`, `docs/ARCHITECTURE.md`,
`docs/TRANSITION_MEMORY.md`, `docs/JURY_DEFENSE.md`.

---

## 8. Explicit non-goals / prohibitions (enforced)

No fabricated HMEL data; no "live/validated/safety-certified" claims; no fixed
savings (44%/55%/R²>0.95/₹60–102 Cr) presented as measured; no random noise shown
as inference; no hard-coded KPI/safety values; no RL in the core; point estimate
alone never triggers prime candidacy; OOD/critical failure never yields a
confident action; no row-level train/test split; no silent mock fallback.
