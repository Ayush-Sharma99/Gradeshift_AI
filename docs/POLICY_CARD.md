# POLICY_CARD — GradeShift PrimePath Disposition Policy (`policy-v1` / `disposition-v1`)

---

## 1. Policy Identity

- **Base Policy Version:** `policy-v1` ([`src/gradeshift/config.py`](../src/gradeshift/config.py))
- **Disposition Engine Version:** `disposition-v1` ([`src/gradeshift/disposition.py`](../src/gradeshift/disposition.py))
- **Policy Fingerprint:** `policy:a2555a4d9431c288`
- **Provenance:** `ASSUMPTION — POLICY values, not HMEL operating limits`

---

## 2. Action Vocabulary

| Action Constant | Display Label | Operational Meaning |
|---|---|---|
| `HOLD` | `HOLD / FOLLOW CURRENT ROUTING` | Maintain current downgrade/wide-spec routing; do not switch to prime. |
| `SAMPLE_NOW` | `SAMPLE NOW` | Request a confirmatory laboratory grab sample and hold current routing until the result arrives. |
| `PRIME_RELEASE_CANDIDATE` | `PRIME-RELEASE CANDIDATE` | Flag the mapped material window for human QC review (`Shift Quality Approver (QC)`) as a candidate for prime commercial disposition. |
| `ABSTAIN` | `ABSTAIN / FOLLOW SOP` | Refuse to issue an active disposition recommendation because a hard gate failed; follow standard plant SOP. |
| `FOLLOW_SOP` | `FOLLOW_SOP` | Fallback action triggered automatically when a recommendation exceeds its validity window (`30.0 min`). |

---

## 3. The 13 Hard Policy Gates (Evaluated FIRST)

In [`disposition.evaluate_hard_gates`](../src/gradeshift/disposition.py), all 13 hard gates are evaluated before any action selection or economic ranking. Any failed `Severity.BLOCK` gate forces `ABSTAIN`:

| Order | Gate ID | Category | Pass Condition | Failure Reason Code |
|---:|---|---|---|---|
| 1 | `valid_transition` | `transition_identity` | Event has valid `event_id` and `grade_from != grade_to` | `ABSTAIN_INVALID_TRANSITION` |
| 2 | `timestamp_alignment` | `timestamp` | `decision_time >= event.started_at` and no timestamp disorder | `ABSTAIN_TIMESTAMP_ALIGNMENT` |
| 3 | `specification_available` | `specification` | Target `GradeSpec` is present with `mfi_low < mfi_high` | `ABSTAIN_SPEC_UNAVAILABLE` |
| 4 | `prediction_available` | `calibration_prediction` | `PredictionBundle` is present with finite `point_mfi` | `ABSTAIN_PREDICTION_UNAVAILABLE` |
| 5 | `calibrated_interval` | `calibration_prediction` | Valid `calibration_version`, finite `lower_mfi <= upper_mfi`, `nominal_coverage >= 0.90` | `ABSTAIN_UNCALIBRATED_INTERVAL` |
| 6 | `model_version` | `calibration_prediction` | Non-empty `model_version` (and matches `expected_model_version` if pinned) | `ABSTAIN_VERSION_MISMATCH` |
| 7 | `material_window_available` | `material_mapping` | `MaterialEligibilityResult.available` is `True` and `mapped_mass_tonnes > 0` | `ABSTAIN_MATERIAL_UNAVAILABLE` |
| 8 | `material_support_sufficient` | `material_mapping` | `mapping_quality` is `WELL_SUPPORTED` (or `PARTIAL` if policy allows) with no blocking codes | `ABSTAIN_MATERIAL_SUPPORT` |
| 9 | `route_known` | `material_mapping` | `route_known` is `True` and `mapping_quality != AMBIGUOUS` | `ABSTAIN_ROUTE_AMBIGUOUS` |
| 10 | `mapping_uncertainty` | `material_mapping` | `residence_uncertainty_min <= 180.0 min` | `ABSTAIN_RESIDENCE_UNCERTAINTY` |
| 11 | `sensor_health` | `sensor_health` | `SensorHealthReport.overall_state` is `NORMAL` (or `DEGRADED` non-critical) | `ABSTAIN_SENSOR_HEALTH` |
| 12 | `applicability` | `ood` | `ApplicabilityResult.state` is `NORMAL` (not `OOD`, `UNSUPPORTED`, or `UNAVAILABLE`) | `ABSTAIN_APPLICABILITY` |
| 13 | `approval_path_configured` | `approval` | `ApprovalConfig.configured` is `True` with non-empty `required_approver` | `ABSTAIN_NO_APPROVAL_PATH` |

---

## 4. Decision Selection Rules (When All 13 Hard Gates Pass)

1. **Recommendation Expiry Check:**
   - If `current_time - decision_time > recommendation_expiry_min (30.0 min)`, return `FOLLOW_SOP` (`EXPIRED_RECOMMENDATION_FOLLOW_SOP`).
2. **Two-Sided Calibrated Interval & Dwell Check (`PRIME_RELEASE_CANDIDATE`):**
   - If `lower_mfi >= spec.mfi_low` **and** `upper_mfi <= spec.mfi_high` **and** `dwell_status.satisfied` (`>= 30.0 min`), return `PRIME_RELEASE_CANDIDATE` (`permitted_actions = (PRIME_RELEASE_CANDIDATE, HOLD, ABSTAIN)`).
3. **Confirmatory Sampling Check (`SAMPLE_NOW`):**
   - If the interval crosses a spec boundary (`point_mfi` near or inside spec, or interval straddles `mfi_low` / `mfi_high`), `sample_available` is `True`, and `sample_result_latency_min (45.0) <= decision_horizon_min (240.0)`, return `SAMPLE_NOW` (`permitted_actions = (SAMPLE_NOW, HOLD, ABSTAIN)`).
4. **Default Safe Routing (`HOLD`):**
   - Otherwise, return `HOLD` (`permitted_actions = (HOLD, ABSTAIN)`).
