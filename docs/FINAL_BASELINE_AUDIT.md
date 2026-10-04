# FINAL BASELINE AUDIT — GradeShift PrimePath

**Phase 0 deliverable.** Snapshot of the repository *as inherited*, the migration
decisions, and the risks. This is a forensic baseline, not a roadmap. The roadmap
is [`FINAL_PRODUCT_IMPLEMENTATION_PLAN.md`](FINAL_PRODUCT_IMPLEMENTATION_PLAN.md).

- **Date:** 2026-10-01
- **Branch:** `main` (single commit `5da04be` — "Initial GradeShift AI application")
- **Product contract:** [`GradeShift_Product_Freeze_Engineering_Handoff.md`](../GradeShift_Product_Freeze_Engineering_Handoff.md)
- **Deprecated contract:** `CLAUDE_CODE_MASTER_PROMPT.md` (historical only)

---

## 1. Runtime status (verified)

| Check | Result |
|---|---|
| Python | 3.10.0 |
| numpy / scipy / pandas / scikit-learn | 1.26.4 / 1.15.2 / 2.2.3 / 1.6.1 |
| streamlit | 1.62.0 |
| torch | 2.6.0+cpu |
| App imports | Clean (no syntax errors) |
| Simulator steady state at Grade-B setpoint | **DEFECT CONFIRMED** (see §4) |

The environment is adequate for a CPU-only laptop POC. No heavyweight infra needed.

---

## 2. Repository inventory

| File | Lines | Role (inherited) | Core defect |
|---|---:|---|---|
| `app.py` | 209 | Overview dashboard | KPIs derived from buggy simulator; "RL agent" language with no RL |
| `pages/1_Grade_Transition.py` | 184 | Baseline-vs-"AI" overshoot chart | Depends on buggy optimizer; off-spec curves |
| `pages/2_Soft_Sensor.py` | 146 | Soft-sensor demo | **Mocks AI with `true_mfi * np.random.normal(1.0,0.02)`** |
| `pages/3_AI_Optimizer.py` | 185 | Operator workstation | Text references NMPC/CBF never computed |
| `pages/4_Safety.py` | 180 | Safety/constraints | 100% hard-coded HTML bars; no dynamic gate |
| `pages/5_Economics.py` | 110 | ROI waterfall | Hard-coded ₹81 Cr; conflicts with deck ₹60–102 Cr |
| `pages/6_Digital_Twin.py` | 150 | P&ID / bed profile | Synthetic contour; hard-coded state strings |
| `reactor_simulator.py` | 79 | Reactor dynamics | Empirical polynomial; **steady state off-spec**; constant T |
| `soft_sensor.py` | 96 | LSTM soft sensor | Toy 1-layer LSTM on toy data; not wired to UI; MFI only |
| `transition_optimizer.py` | 100 | Bang-bang timing | SciPy `minimize_scalar` on 1 var; **not RL** |
| `gs_theme.py` | 388 | Design system | **High quality — keep** |
| `requirements.txt` | — | Deps | Clean; `torch` likely droppable from core |
| `README.md` | — | Docs | Effectively empty |

---

## 3. Current data flow (inherited)

```
GRADES dict (duplicated per page)
   -> TransitionOptimizer.simulate_linear_ramp()  (baseline)
   -> TransitionOptimizer.optimize_bang_bang()     ("AI")
        -> PolyolefinReactor.step()  (empirical MFI polynomial + Mw washout)
   -> first_on_spec() heuristic -> KPI cards (time, off-spec t, value @ ₹20/kg)
Soft Sensor page: ignores soft_sensor.py entirely -> random noise around truth
Safety page: static dictionaries -> HTML bars
Economics page: static constants -> waterfall
```

There is **no event model, no provenance, no time alignment, no uncertainty, no
material identity, no decision engine, no validation split, no persisted model**.
Every displayed number is either a direct function of the buggy simulator or a
hard-coded constant.

---

## 4. Confirmed defects (reproducible)

**D1 — Simulator steady state is off-spec (BLOCKER for any honest demo).**
Verified: at the Grade-B hydrogen setpoint `H2_M=0.35`, the instantaneous MFI
polynomial returns **11.26**, not the grade's declared target **8.0**. The bed
washout therefore converges to **11.26 MFI** and never enters the ±5% spec band.
```
instantaneous MFI at H2_M=0.35: 11.256
steady-state bed MFI after 2000 min: 11.256   (target 8.0)
```
Root cause: the grade table `H2_M` values and the kinetic polynomial were never
co-calibrated. Any "transition completes on-spec" claim built on this is false.

**D2 — Soft sensor is fabricated.** `pages/2_Soft_Sensor.py` displays
`true_mfi * np.random.normal(1.0, 0.02)` as "AI prediction". Prohibited by the
contract (random noise shown as inference).

**D3 — "RL optimizer" is not RL.** `transition_optimizer.py` is a bounded scalar
search over a single switch time. The submitted title claims CQL RL.

**D4 — Safety page is decorative.** No dynamic constraint is evaluated; the
"ALL CONSTRAINTS CLEAR" banner is static.

**D5 — Economics are hard-coded and internally inconsistent** (₹81 Cr code vs
₹60–102 Cr deck; flaring/energy lines overclaimed vs deck).

**D6 — No provenance / no SIMULATED labelling.** Synthetic output is presented
with "ONLINE" styling, risking the impression of live plant data.

**D7 — Config duplication.** `GRADES` is redefined in `app.py` and pages.

---

## 5. Old architecture → PrimePath architecture

**Old (deck intent):** 3-tier autonomy stack — Method-of-Moments + LSTM + EKF
soft sensor → offline-RL (CQL) optimizer → NMPC/CBF safety shield writing DCS
setpoints. Positioned as "AI that transitions the reactor faster and safer."

**PrimePath (frozen):** a read-only, advisory **commercial-disposition decision
layer** that sits *above* automation. It does not write setpoints. Center of
gravity moves from *controlling the reactor* to *deciding what the transitional
material is worth and when to act on it*, under calibrated uncertainty and human
authorization. Decision vocabulary: **HOLD / SAMPLE NOW / PRIME-RELEASE
CANDIDATE / ABSTAIN**.

---

## 6. Migration decision table

| Component | Decision | Instruction |
|---|---|---|
| `gs_theme.py` | **KEEP** | Reuse tokens/components; add provenance/uncertainty/status widgets |
| `app.py` | **REFACTOR** | Becomes PrimePath Decision Cockpit (thin UI over services) |
| `pages/1_Grade_Transition.py` | **REPURPOSE** | Transition Replay (timeline, material window, blind window) |
| `pages/2_Soft_Sensor.py` | **REPLACE LOGIC** | Quality Evidence (real estimator + conformal interval); delete random mock |
| `pages/3_AI_Optimizer.py` | **REPURPOSE** | Disposition Workbench (actions, expected-loss, VOI, reasons, approval) |
| `pages/4_Safety.py` | **REPURPOSE** | Transition Guardian (health, OOD, policy gates, abstention) |
| `pages/5_Economics.py` | **REBUILD** | Episode Economic Ledger (from explicit assumptions, LOW/BASE/HIGH) |
| `pages/6_Digital_Twin.py` | **REPURPOSE** | Transition Memory & Assurance (provenance, analogs, versions) |
| `reactor_simulator.py` | **REPURPOSE** | Seeded synthetic episode generator + residence-time fixture (calibrated so steady state = target) |
| `soft_sensor.py` | **REPLACE** | Clean estimator/calibrator/health/OOD interfaces under `src/gradeshift/` |
| `transition_optimizer.py` | **DEPRECATE AS CORE** | Move to `experiments/legacy_control_counterfactual.py`; drop RL label |
| Static safety dicts / ₹81 Cr waterfall / random "AI" line | **REMOVE** | Replace with computed, versioned artifacts |
| `README.md` | **REPLACE** | PrimePath docs, evidence labels, commands, limitations |
| `PROJECT_STATUS_AUDIT.md`, deck PDF, old prompt | **KEEP AS HISTORY** | Never edit; reconcile via claim ledger |

---

## 7. Major risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Rebuilding the fictional reactor consumes the whole budget | Keep physics minimal: a calibrated single-property generator whose steady state = target. Physics serves data generation + residence time only. |
| R2 | Over-claiming (E4/E5) with only synthetic evidence | Claim-evidence matrix; everything labelled SIMULATED/ILLUSTRATIVE; evidence ceiling E3 |
| R3 | Leakage inflating metrics | Whole-event chronological splits; leakage unit tests; freeze manifest before locked test |
| R4 | Conformal coverage mis-reported | Report empirical coverage + width honestly; never widen to force coverage |
| R5 | Demo "aha" (HOLD→SAMPLE→CANDIDATE) hard-coded | Generator tuned transparently *before* lock; decisions computed, never scripted |
| R6 | Scope sprawl across 7 UI pages | Build domain engine + tests first; UI is a thin presenter last |
| R7 | Torch dependency bloats laptop runtime | Core estimator = scikit-learn; torch optional/experimental only |

---

## 8. Migration strategy (summary)

Build **bottom-up and evidence-first**: domain packages under `src/gradeshift/`
with unit tests, a seeded synthetic generator calibrated to converge on-spec, the
full decision lineage (SOURCE → EVENT → MATERIAL WINDOW → ESTIMATE → INTERVAL →
HEALTH/OOD → POLICY → EXPECTED LOSS → ACTION → OUTCOME → VALUE → MEMORY), a locked
validation run, then wire the existing high-quality theme into seven PrimePath
pages. Legacy control code is preserved under `experiments/`, never deleted.
Phasing and exit criteria are in the implementation plan.
