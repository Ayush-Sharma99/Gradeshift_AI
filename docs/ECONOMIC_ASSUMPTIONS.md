# ECONOMIC_ASSUMPTIONS — GradeShift PrimePath Economic Model (`economics-v1`)

> **Provenance Warning (`ASSUMPTION` / `SIMULATED`):**  
> All economic parameters in this repository are explicit scenario assumptions (`E0`) or synthetic episode evaluations (`E2`/`E3`). **None of these numbers represent measured HMEL plant costs, margins, or realized savings.**

---

## 1. Scenario Parameter Table (`src/gradeshift/config.py`)

| Parameter | Unit | `LOW` Scenario | `BASE` Scenario (Default) | `HIGH` Scenario | Provenance |
|---|---|---:|---:|---:|---|
| **`prime_price`** | `₹ / tonne` | `90,000` | `95,000` | `98,000` | `ASSUMPTION` |
| **`downgrade_price`** | `₹ / tonne` | `78,000` | `75,000` | `73,000` | `ASSUMPTION` |
| **`downgrade_spread`** (`prime - downgrade`) | `₹ / tonne` | `12,000` | `20,000` | `25,000` | `ASSUMPTION` |
| **`false_prime_consequence`** | `₹ / tonne` | `40,000` | `60,000` | `90,000` | `ASSUMPTION` |
| **`sample_cost`** | `₹ / sample` | `15,000` | `20,000` | `25,000` | `ASSUMPTION` |
| **`workflow_cost`** | `₹ / action` | `5,000` | `8,000` | `10,000` | `ASSUMPTION` |

---

## 2. Expected Decision Loss Formulation (`src/gradeshift/economics.py`)

For each action $a$ in the **permitted action set** returned by `disposition.evaluate_disposition`:

$$\operatorname{EL}(a \mid x) = p_{\text{bad}} \cdot C_{\text{false-prime}}(a) + (1 - p_{\text{bad}}) \cdot C_{\text{false-hold}}(a) + C_{\text{sample}}(a) + C_{\text{workflow}}(a)$$

Where:
- **For `PRIME_RELEASE_CANDIDATE`:**
  - $C_{\text{false-prime}} = m_{\text{window}} \times \text{false\_prime\_consequence}$
  - $C_{\text{false-hold}} = 0$
  - $C_{\text{workflow}} = \text{workflow\_cost}$
- **For `HOLD` and `ABSTAIN`:**
  - $C_{\text{false-prime}} = 0$
  - $C_{\text{false-hold}} = m_{\text{recoverable}} \times \text{downgrade\_spread}$
  - $C_{\text{workflow}} = 0$
- **For `SAMPLE_NOW`:**
  - $C_{\text{false-hold}} = m_{\text{recoverable}} \times \text{downgrade\_spread}$
  - $C_{\text{sample}} = \text{sample\_cost}$
  - $C_{\text{workflow}} = \text{workflow\_cost}$

> **Governance Rule:** Economics sit strictly **behind** the 13 hard policy gates. If `PRIME_RELEASE_CANDIDATE` is blocked by any gate, it is excluded from `permitted_actions` and cannot be selected regardless of its hypothetical expected loss.

---

## 3. Discrete-Outcome Value of Information (`voi-discrete-v1`)

When a confirmatory sample is evaluated (`compute_voi`):

$$\operatorname{VOI} = \min_{a \in \mathcal{A}_{\text{now}}} \operatorname{EL}(a \mid x) - \mathbb{E}_{y \in \{\text{GOOD}, \text{BAD}\}}\left[\min_{a \in \mathcal{A}(y)} \operatorname{EL}(a \mid x, y)\right] - C_{\text{sample}}$$

`SAMPLE_NOW` has positive economic value only when:
1. A sample result can arrive within the decision horizon (`sample_latency_min <= decision_horizon_min`),
2. The sample outcome (`GOOD` vs `BAD`) can change the permissible action set, and
3. $\operatorname{VOI} > \text{voi\_threshold}$ (`0.0 ₹`).

---

## 4. Realized vs Counterfactual Value & Annual Scale-Up

1. **Realized vs Counterfactual Separation (`RealizedVsCounterfactual`):**
   - `realized_value_currency`: Value of the material window under the actual route (`m_window × actual_route_value_per_tonne`).
   - `counterfactual_opportunity_currency`: Potential incremental spread on prime-eligible material (`m_recoverable × downgrade_spread` when `realized_good` is `True`).
   - Verified by [`validation.economic_sanity`](../src/gradeshift/validation.py) (`no_double_counting = true`, `realized_separate_from_counterfactual = true`).
2. **Annual Scenario Scale-Up (`scale_up_annual`):**
   $$\text{Annual Scenario Value} = N_{\text{eligible\_transitions}} \times V_{\text{episode}} \times \text{availability} \times \text{adoption}$$
   Tagged `Provenance.ASSUMPTION` (`E0`). Never reported as a fixed plant headline.
