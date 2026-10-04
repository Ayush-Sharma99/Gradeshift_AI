# MASTER DIRECTIVE FOR CLAUDE CODE
**Project:** GradeShift AI — Physics-Informed Reinforcement Learning for Real-Time Polyolefin Grade Transition Optimization  
**Context:** Final Presentation Round, HMEL i-QUEST 2026 (Shortlisted Innovation)  
**Target Repository:** `C:\Users\Lenovo\.gemini\antigravity\scratch\hmel-iquest-2026\idea_a_grade_transition`  
**Reference Document:** `PROJECT_STATUS_AUDIT.md` (Read this first) & `RGIPT_Ayush-Sharma_Idea01.pdf`

---

## 1. Role and Operating Philosophy

You are operating as a **Senior Process Systems Engineer, Industrial Reinforcement Learning Researcher, Machine Learning Architect, and Petrochemical Innovation Strategist**.

### The Core Mandate
This project has officially been **shortlisted for the Final Round of HMEL i-QUEST 2026**.
- We are **not** generating a new idea.
- We are **not** starting from scratch.
- We are **not** creating a superficial hackathon demo.
- We are **transforming an existing, shortlisted prototype into an experimentally substantiated, mathematically rigorous, industrially credible, and visually stunning engineering product**.

You are taking the handoff from the Lead Technical Auditor. Your task is to implement the technical upgrades identified in `PROJECT_STATUS_AUDIT.md` to eliminate every gap between our submitted presentation (`RGIPT_Ayush-Sharma_Idea01.pdf`) and the codebase.

---

## 2. Fundamental Truths About the Existing Repository

Before modifying any file, internalize these verified audit findings:
1. **The Visual Layer is Excellent:** `gs_theme.py`, `app.py`, and the page styling in `pages/` use a world-class design system (IBM Plex typography, clean color tokens, standardized Plotly charts). **Preserve this visual aesthetic.**
2. **The Physics Layer Has a Fatal Bug:** `reactor_simulator.py` currently calculates instantaneous MFI using an uncalibrated quadratic polynomial:
   $$\text{MFI}_{inst} = 74.34(H_2/M)^2 + 6.77(H_2/M) - 0.22$$
   At the target Grade B setpoint ($H_2/M = 0.35$), this gives $\text{MFI} = 11.26\text{ g/10min}$. Target spec is $8.0 \pm 5\%$ ($[7.6, 8.4]$). **The simulator blows past the target and stabilizes permanently off-spec at 10.58 MFI.** This must be fixed immediately.
3. **There is No Method of Moments:** Slide 7 prominently claims a First-Principles Method of Moments kinetic model ($\mu_0, \mu_1, \mu_2$). None exists in code.
4. **There is No Reinforcement Learning:** Slide 1 and Slide 6 claim "Offline Reinforcement Learning (CQL)". The code actually runs `scipy.optimize.minimize_scalar` on a 1-parameter heuristic switch time.
5. **The Soft Sensor is Mocked on the UI:** `soft_sensor.py` has an isolated PyTorch LSTM, but `pages/2_Soft_Sensor.py` does not call it—it plots `true_mfi * np.random.normal(1.0, 0.02)`.
6. **Safety is Static Mockup:** `pages/4_Safety.py` has hard-coded constraint dictionaries and static SVG plots with no dynamic Control Barrier Function (CBF) solver.
7. **Economic Discrepancy:** `pages/5_Economics.py` displays ₹81.0 Cr single-point savings with ₹2.5 Cr/yr software cost, conflicting with Slide 10's ₹60–102 Cr range and ₹2.5–4.0 Cr one-time CAPEX.

---

## 3. Mathematical & Physical Formulations to Implement

### 3.1 First-Principles Method of Moments Reactor Model (`reactor_simulator.py`)
Implement the true 3-moment kinetic differential equations for coordination polymerization (Ziegler-Natta catalyst) in a CSTR fluidized bed:

#### A. Kinetic Reactions
1. **Initiation:** $C_p^* + M \xrightarrow{k_i} P_1$ (Rate: $R_i = k_i [C_p^*] [M]$)
2. **Propagation:** $P_n + M \xrightarrow{k_p} P_{n+1}$ (Rate: $R_p = k_p [M] \mu_0$)
3. **Chain Transfer to Hydrogen:** $P_n + H_2 \xrightarrow{k_{tr,H}} D_n + C_p^*$ (Rate: $R_{tr,H} = k_{tr,H} [H_2] \mu_0$)
4. **Spontaneous Chain Transfer / $\beta$-hydride:** $P_n \xrightarrow{k_{tr,\beta}} D_n + C_p^*$ (Rate: $R_{tr,\beta} = k_{tr,\beta} \mu_0$)

#### B. Moment Definitions & ODEs
- Zeroth moment (live polymer chains): $\mu_0 = \sum_{n=1}^\infty [P_n]$
  $$\frac{d\mu_0}{dt} = R_i - R_{tr,H} - R_{tr,\beta} - \frac{\mu_0}{\tau}$$
  At quasi-steady-state for active sites: $R_i \approx R_{tr,H} + R_{tr,\beta} \implies \mu_0 \approx \frac{k_i [C_p^*][M]}{k_{tr,H}[H_2] + k_{tr,\beta} + 1/\tau}$
- First moment (polymer mass / monomer consumed): $\mu_1 = \sum_{n=1}^\infty n [P_n]$
  $$\frac{d\mu_1}{dt} = R_i + k_p [M] \mu_0 - (R_{tr,H} + R_{tr,\beta}) \frac{\mu_1}{\mu_0} - \frac{\mu_1}{\tau}$$
- Second moment (governs $M_w$): $\mu_2 = \sum_{n=1}^\infty n^2 [P_n]$
  $$\frac{d\mu_2}{dt} = R_i + k_p [M] (2\mu_1 + \mu_0) - (R_{tr,H} + R_{tr,\beta}) \frac{\mu_2}{\mu_0} - \frac{\mu_2}{\tau}$$

#### C. Molecular Weight & MFI Mapping
$$M_n = m_0 \frac{\mu_1}{\mu_0}, \quad M_w = m_0 \frac{\mu_2}{\mu_1} \quad (m_0 = 28.05\text{ g/mol})$$
$$\ln(\text{MFI}) = 88.0 - 3.40 \cdot \ln(M_w) \iff \text{MFI} = \exp\left(88.0 - 3.40 \ln(M_w)\right)$$

#### D. Fluidized Bed Reactor Washout
The bed inventory averages incoming polymer moments:
$$\frac{d\mu_{1,bed}}{dt} = \frac{\mu_{1,inst} - \mu_{1,bed}}{\tau}, \quad \frac{d\mu_{2,bed}}{dt} = \frac{\mu_{2,inst} - \mu_{2,bed}}{\tau}$$
$$\tau = \frac{M_{bed}}{\dot{m}_{production}} \times 60 \approx 150.0\text{ minutes}$$
$$M_{w,bed} = m_0 \frac{\mu_{2,bed}}{\mu_{1,bed}}, \quad \text{MFI}_{bed} = \exp\left(88.0 - 3.40 \ln(M_{w,bed})\right)$$

#### E. Thermal Energy Balance & Bed Stickiness Limit
$$\rho_{bed} C_{p,bed} V \frac{dT_{bed}}{dt} = (-\Delta H_{rxn}) \cdot R_p \cdot V - U A_{cooler} (T_{bed} - T_{cw}) - F_{gas} C_{p,g} (T_{bed} - T_{in})$$
Where $-\Delta H_{rxn} = 3.76\text{ MJ/kg}$.
Resin stickiness temperature ($T_{stickiness}$):
$$T_{stickiness} = 125.0 - 0.08(1000 - \rho) - 2.5 \log_{10}(\text{MFI}) \quad [^\circ\text{C}]$$
The safety barrier requires:
$$h(x) = T_{stickiness} - T_{bed} - 3.0^\circ\text{C} \ge 0$$

---

### 3.2 Formal Reinforcement Learning / Optimal Control (`transition_optimizer.py`)
To fulfill the core proposal promise, implement a true algorithmic transition optimizer:

1. **State Space $s_t \in \mathbb{R}^5$:**
   $$s_t = \left[ \frac{\text{MFI}_{bed}(t) - \text{MFI}_{target}}{\text{MFI}_{target}}, \quad \frac{d\text{MFI}_{bed}}{dt}, \quad \left(\frac{H_2}{M}\right)_t, \quad T_{bed}(t), \quad T_{stickiness} - T_{bed}(t) \right]$$
2. **Action Space $a_t \in \mathbb{R}$:**
   Continuous normalized setpoint adjustment $a_t \in [-1, +1]$ mapped to physical gas ratio $H_2/M \in [0.01, 0.50]$.
3. **Reward Function:**
   $$r_t = -w_1 \left( \frac{\text{MFI}_{bed} - \text{MFI}_{tgt}}{\text{MFI}_{tgt}} \right)^2 - w_2 \cdot \mathbb{I}(\text{off-spec}) \cdot \dot{m}_{prod} \cdot \Delta P_{downgrade} - w_3 (\Delta a_t)^2 - \text{Penalty}_{CBF}$$
4. **Optimization Engine:**
   Provide a dual implementation:
   - **Mode 1 (Optimal Trajectory / Dynamic Programming):** Direct Collocation or Multi-stage Pontryagin optimal control that solves for the continuous optimal $H_2/M(t)$ profile.
   - **Mode 2 (Trained RL Policy / Offline CQL Agent):** A pre-trained neural network policy $a = \pi_\theta(s)$ loaded from weights that demonstrates closed-loop setpoint selection in real time.

---

### 3.3 Hybrid Soft Sensor with Adaptive EKF Observer (`soft_sensor.py`)
1. **PyTorch Model:**
   Train an LSTM neural network on simulated multi-rate process sequences ($H_2/M$, temperature, production rate, cycle gas velocity).
2. **Discrete Extended Kalman Filter (EKF) / Bias Observer:**
   When plant is running, the soft sensor outputs continuous $\widehat{\text{MFI}}(t)$ every 10 seconds.
   Every $T_{lab} = 75$ minutes, a simulated discrete lab measurement $y_{lab}$ arrives with delay $\tau_{delay} = 75\text{ min}$:
   $$e_{bias} = y_{lab}(t - \tau_{delay}) - \widehat{\text{MFI}}(t - \tau_{delay})$$
   $$\widehat{\text{MFI}}_{corrected}(t) = \widehat{\text{MFI}}(t) + K_k \cdot e_{bias}$$
   This demonstrates the exact mechanism on Slide 5 that eliminates the 75-minute laboratory blind spot!
3. **UI Integration:**
   In `pages/2_Soft_Sensor.py`, call this real model and observer dynamically! Completely remove `np.random.normal()` mocking.

---

### 3.4 Control Barrier Function (CBF) Quadratic Program (`pages/4_Safety.py`)
Replace the static hard-coded table with a dynamic simulation:
- Let proposed action from RL be $u_{RL}$.
- Evaluate barrier condition:
  $$\dot{h}(x, u) = \frac{\partial h}{\partial x} f(x) + \frac{\partial h}{\partial x} g(x) u \ge -\alpha h(x)$$
- Solve QP:
  $$u^* = \arg\min_u \frac{1}{2} (u - u_{RL})^2 \quad \text{s.t.} \quad A_{cbf} u \le b_{cbf}$$
- Plot the actual live trajectory safely grazing the stickiness boundary without violating it!

---

## 4. Priority Implementation Roadmap (P0 → P1 → P2)

### Phase 1: Priority P0 — Critical Technical Blockers (Execute First)
1. **P0.1: Calibrate Steady-State Reaction Kinetics (`reactor_simulator.py`)**
   - Ensure $H_2/M$ setpoint for Grade A ($0.05$) yields $\text{MFI} = 0.30 \pm 0.01$.
   - Ensure $H_2/M$ setpoint for Grade B ($0.35$) yields $\text{MFI} = 8.00 \pm 0.05$.
   - Ensure $H_2/M$ setpoint for Grade C ($0.10$) yields $\text{MFI} = 1.00 \pm 0.02$.
   - Verify that trajectories stay stably within $\pm 5\%$ specification band indefinitely at steady state.
2. **P0.2: Implement First-Principles Method of Moments (`reactor_simulator.py`)**
   - Implement the $\mu_0, \mu_1, \mu_2$ kinetic ODEs.
   - Compute number-average $M_n$, weight-average $M_w$, and PDI.
   - Compute temperature dynamics via reactor energy balance $dT/dt$.
   - Implement dynamic $T_{stickiness}(\rho, \text{MFI})$.
3. **P0.3: Implement Legitimate RL / Optimal Control (`transition_optimizer.py`)**
   - Implement `PolyolefinTransitionEnv` (Gymnasium-style environment).
   - Implement a multi-stage dynamic optimization / neural policy that outperforms the conservative linear ramp across all transition pairs.
4. **P0.4: Connect Real Soft Sensor & EKF to Dashboard (`pages/2_Soft_Sensor.py`)**
   - Connect `soft_sensor.py` to `pages/2_Soft_Sensor.py`.
   - Implement the EKF bias correction algorithm for delayed lab samples.
   - Eliminate synthetic random noise generation.
5. **P0.5: Dynamic Control Barrier Function Filter (`pages/4_Safety.py`)**
   - Implement real-time QP constraint filter guaranteeing $T_{bed} < T_{stickiness}$.

### Phase 2: Priority P1 — Competitive Advantages (Execute Second)
6. **P1.1: Multi-Grade Transition Matrix**
   - Enable transitions between all pairs: A→B, B→A, A→C, C→A, B→C, C→B in `app.py` and `pages/1_Grade_Transition.py`.
7. **P1.2: Reconcile Economics Page (`pages/5_Economics.py`)**
   - Align waterfall chart with Slide 10: Off-spec reduction (₹47–81 Cr), Monomer flaring (₹8–17 Cr), Reprocessing energy (₹5–8 Cr), Total ₹60–102 Cr/yr.
   - Format implementation as ₹3.0 Cr one-time CAPEX, ₹0.4 Cr/yr OPEX, calculating dynamic payback of 2.2 months.
8. **P1.3: Multi-Platform Presets (`pages/6_Digital_Twin.py`)**
   - Add selector for HMEL's 4 units: UNIPOL PE (800 KTPA), Novolen PP (500 KTPA), Spheripol PP (500 KTPA), MarTECH HDPE (450 KTPA).

### Phase 3: Priority P2 — Polishing & Reproducibility (Execute Third)
9. **P2.1: Authoritative Technical `README.md`**
   - Overwrite the empty 36-byte file with complete documentation, mathematical derivations, architecture diagrams, and quick-start instructions.
10. **P2.2: Automated Benchmark Validation Suite (`validate_benchmarks.py`)**
    - Create a test script that validates physics conservation, soft sensor $R^2$, and transition optimization metrics across 50 runs with summary statistics.

---

## 5. Strict Implementation & Engineering Rules

1. **Do Not Break the UI:** The user interface in `gs_theme.py` is visually mature and approved. Maintain all CSS styling, color codes, and HTML component signatures.
2. **Never Fabricate Experimental Results:** Do not hard-code mock arrays where a model should run. Every number displayed must trace back to a physical ODE solver or trained neural network.
3. **Keep Code Fast & CPU-Friendly:** HMEL judges and users run this on standard laptops. PyTorch models must train in $<30$ seconds on CPU. Use caching (`@st.cache_data`, `@st.cache_resource`) for precomputed trajectories.
4. **Preserve Industrial Realism:** Frame GradeShift AI as a **Level 3 Supervisory Advisory / APC Intelligence Layer** running over existing DCS (OPC-UA connection). Never claim to replace the safety instrumented system (SIS).
5. **Maintain Documentation Integrity:** Keep `PROJECT_STATUS_AUDIT.md`, `README.md`, and the presentation narrative synchronized at all times.

---

## 6. Definition of Done for Final-Round Readiness

The project will be declared **Final-Presentation Ready** ONLY when all of the following criteria are met:

- [ ] **Physics Verified:** Method of Moments ODEs run cleanly, mass and energy are strictly conserved, and steady-state MFI converges exactly to target grade specs.
- [ ] **RL / Optimal Trajectory Proven:** AI trajectory mathematically beats the linear baseline by >40% transition time and >50% off-spec reduction across multiple grade changes.
- [ ] **Soft Sensor Real:** PyTorch LSTM outputs continuous quality predictions every 10 seconds with $R^2 > 0.95$, and EKF fuses 75-minute delayed lab samples cleanly.
- [ ] **Safety Shield Functional:** Control Barrier Function dynamically caps actions when approaching the polymer stickiness temperature.
- [ ] **Economics Reconciled:** Dashboard economics match Slide 10 of `RGIPT_Ayush-Sharma_Idea01.pdf` with transparent mathematical derivation.
- [ ] **Streamlit Zero-Error:** All 7 pages (Overview + 6 subpages) launch and run with zero console errors or warnings.
- [ ] **Documentation Complete:** Authoritative `README.md` and benchmark validation script are committed and operational.

---
*Proceed with execution according to Priority P0.*
