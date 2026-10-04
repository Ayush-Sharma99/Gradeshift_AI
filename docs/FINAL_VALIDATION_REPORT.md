# GradeShift PrimePath — FINAL VALIDATION REPORT

**SIMULATION / ASSUMPTION — not HMEL-validated.** All quantitative results are at most E2 (synthetic) / E3 (controlled prototype). A PRIME-RELEASE CANDIDATE is advisory and always requires human/QC authorization.

## A. Frozen manifest
```json
{
  "seed": 42,
  "n_per_dir": 3,
  "feature_version": "feat-v1",
  "partitions": {
    "TRAIN": [
      "EP-AB-00",
      "EP-AB-01",
      "EP-AB-02",
      "EP-AC-00",
      "EP-AC-01",
      "EP-AC-02",
      "EP-BA-00",
      "EP-BA-01",
      "EP-BA-02",
      "EP-CA-00"
    ],
    "CALIBRATION": [
      "EP-BC-00",
      "EP-CA-01",
      "EP-CA-02"
    ],
    "LOCKED_TEST": [
      "EP-BC-01",
      "EP-BC-02",
      "EP-CB-00",
      "EP-CB-01",
      "EP-CB-02"
    ]
  },
  "versions": {
    "replay": "replay-v1",
    "model": "gbm-mfi-v1",
    "calibration": "split-conformal-v1:marginal_symmetric",
    "policy": "policy-v1",
    "economics": "economics-v1",
    "scenario": "BASE"
  },
  "scenario": "BASE",
  "disposition_policy": {
    "base_policy_version": "policy-v1",
    "nominal_coverage": 0.9,
    "decision_horizon_min": 240.0,
    "sample_result_latency_min": 45.0,
    "recommendation_expiry_min": 30.0,
    "required_approver": "Shift Quality Approver (QC)",
    "ambiguous_route_action": "ABSTAIN",
    "require_well_supported_for_prime": true,
    "max_residence_uncertainty_min": 180.0,
    "expected_model_version": null,
    "expected_calibration_version": null,
    "disposition_version": "disposition-v1",
    "provenance": "ASSUMPTION \u2014 POLICY values, not HMEL operating limits"
  },
  "runtime_versions": {
    "python": "3.10.0",
    "numpy": "1.26.4",
    "sklearn": "1.6.1"
  }
}
```

Reproducibility fingerprints:
```json
{
  "manifest": "manifest:5abc0eb1ad93f56c",
  "calibrator": "calib:3cf275c76727911a",
  "policy": "policy:a2555a4d9431c288",
  "economics": "econ:6cbd173e21b7b79a"
}
```

## B–E. Level A — quality (point + uncertainty)
- MAE: 0.2720  RMSE: 0.4353  bias: -0.2337 (locked, 235 rows, 5 events)
- Empirical coverage: 0.6595744680851063 (nominal split-conformal-v1:marginal_symmetric), mean width: 0.47373459385948885
- Calibration used 141 rows from only 3 INDEPENDENT events — rows are correlated, not independent samples.

## Level B — decision risk (locked replay)
```json
{
  "SOP_FIXTURE": {
    "mean_time_to_candidate_min": 160.0,
    "false_prime_mass_tonnes": 1356.0,
    "false_hold_mass_tonnes": 0,
    "false_hold_decisions": 0,
    "total_samples": 0,
    "useful_sample_fraction": null,
    "mean_abstention_rate": 0.0
  },
  "POINT_THRESHOLD": {
    "mean_time_to_candidate_min": 416.0,
    "false_prime_mass_tonnes": 588.0,
    "false_hold_mass_tonnes": 0,
    "false_hold_decisions": 0,
    "total_samples": 0,
    "useful_sample_fraction": null,
    "mean_abstention_rate": 0.0
  },
  "PRIMEPATH": {
    "mean_time_to_candidate_min": null,
    "false_prime_mass_tonnes": 0,
    "false_hold_mass_tonnes": 984.0,
    "false_hold_decisions": 82,
    "total_samples": 0,
    "useful_sample_fraction": null,
    "mean_abstention_rate": 1.0
  },
  "ORACLE_DIAGNOSTIC_ONLY": {
    "mean_time_to_candidate_min": 612.0,
    "false_prime_mass_tonnes": 0,
    "false_hold_mass_tonnes": 0,
    "false_hold_decisions": 0,
    "total_samples": 0,
    "useful_sample_fraction": null,
    "mean_abstention_rate": 0.0
  }
}
```

## Level C — economic value (SIMULATED)
```json
{
  "SOP_FIXTURE": {
    "false_prime_exposure_currency": 81360000.0,
    "false_hold_opportunity_currency": 0.0,
    "sample_cost_currency": 0.0,
    "workflow_cost_currency": 1560000.0,
    "gross_avoidable_loss_currency": 82920000.0,
    "realized_value_currency": 228180000.0,
    "counterfactual_value_currency": 19680000.0
  },
  "POINT_THRESHOLD": {
    "false_prime_exposure_currency": 35280000.0,
    "false_hold_opportunity_currency": 0.0,
    "sample_cost_currency": 0.0,
    "workflow_cost_currency": 1048000.0,
    "gross_avoidable_loss_currency": 36328000.0,
    "realized_value_currency": 228180000.0,
    "counterfactual_value_currency": 19680000.0
  },
  "PRIMEPATH": {
    "false_prime_exposure_currency": 0.0,
    "false_hold_opportunity_currency": 19680000.0,
    "sample_cost_currency": 0.0,
    "workflow_cost_currency": 0.0,
    "gross_avoidable_loss_currency": 19680000.0,
    "realized_value_currency": 208500000.0,
    "counterfactual_value_currency": 19680000.0
  },
  "ORACLE_DIAGNOSTIC_ONLY": {
    "false_prime_exposure_currency": 0.0,
    "false_hold_opportunity_currency": 0.0,
    "sample_cost_currency": 0.0,
    "workflow_cost_currency": 656000.0,
    "gross_avoidable_loss_currency": 656000.0,
    "realized_value_currency": 228180000.0,
    "counterfactual_value_currency": 19680000.0
  }
}
```

## Abstention decomposition
```json
{
  "total_decisions": 235,
  "abstained_decisions": 235,
  "blocking_by_category": {
    "material_mapping": 40,
    "ood": 235
  },
  "multi_gate_decisions": 40,
  "note": "A decision counts once per blocking category; multi_gate decisions were blocked by >1 hard gate simultaneously."
}
```
Every abstention is traced to a blocking hard gate (correct abstention). No 'optimal threshold' was invented to reduce it.

## Zero-candidate diagnostic (LOCKED vs ILLUSTRATIVE DEMO — kept separate)
```json
{
  "locked_prime_candidates": 0,
  "locked_conclusion": "no natural prime candidate on the locked corpus",
  "illustrative_demo_prime_candidate": true,
  "separation_note": "LOCKED_VALIDATION and ILLUSTRATIVE_DEMO are SEPARATE artifacts; their metrics are never blended."
}
```

## Robustness matrix
```json
{
  "rows": [
    {
      "scenario": "normal_evidence",
      "expected_forced_action": "PRIME_RELEASE_CANDIDATE",
      "observed_action": "PRIME_RELEASE_CANDIDATE",
      "match": true,
      "reason_codes": [
        "PRIME_INTERVAL_PASS",
        "PRIME_DWELL_PASS",
        "PRIME_HEALTH_PASS",
        "PRIME_APPLICABILITY_PASS",
        "PRIME_MATERIAL_SUPPORTED",
        "PRIME_CANDIDATE_REQUIRES_AUTHORIZATION"
      ]
    },
    {
      "scenario": "missing_sensor",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_SENSOR_HEALTH"
      ]
    },
    {
      "scenario": "frozen_sensor",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_SENSOR_HEALTH"
      ]
    },
    {
      "scenario": "stale_data",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_SENSOR_HEALTH"
      ]
    },
    {
      "scenario": "timestamp_disorder",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_TIMESTAMP_ALIGNMENT"
      ]
    },
    {
      "scenario": "ood_shift",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_OOD"
      ]
    },
    {
      "scenario": "unknown_grade_pair",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_OOD"
      ]
    },
    {
      "scenario": "ambiguous_routing",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_ROUTE_AMBIGUOUS"
      ]
    },
    {
      "scenario": "incomplete_material_mapping",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_MATERIAL_MAPPING"
      ]
    },
    {
      "scenario": "unavailable_calibration",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "ABSTAIN_NO_CALIBRATION"
      ]
    },
    {
      "scenario": "expired_recommendation",
      "expected_forced_action": "ABSTAIN",
      "observed_action": "ABSTAIN",
      "match": true,
      "reason_codes": [
        "RECOMMENDATION_EXPIRED"
      ]
    }
  ],
  "all_match": true,
  "note": "Controlled fail-safe fixtures (NOT the locked set). SIMULATION/ASSUMPTION."
}
```

## Diagnostic sensitivity (NOT validated policy)
```json
{
  "label": "DIAGNOSTIC SENSITIVITY \u2014 NOT VALIDATED POLICY",
  "interval_width_sweep": [
    {
      "half_width": 0.2,
      "interval": [
        7.8,
        8.2
      ],
      "action": "PRIME_RELEASE_CANDIDATE"
    },
    {
      "half_width": 0.4,
      "interval": [
        7.6,
        8.4
      ],
      "action": "PRIME_RELEASE_CANDIDATE"
    },
    {
      "half_width": 0.6,
      "interval": [
        7.4,
        8.6
      ],
      "action": "HOLD"
    },
    {
      "half_width": 0.8,
      "interval": [
        7.2,
        8.8
      ],
      "action": "HOLD"
    }
  ],
  "sample_cost_sweep": [
    {
      "sample_cost": 5000,
      "voi_currency": 800000.0000000006,
      "recommend_sample": true
    },
    {
      "sample_cost": 20000,
      "voi_currency": 785000.0000000006,
      "recommend_sample": true
    },
    {
      "sample_cost": 60000,
      "voi_currency": 745000.0000000006,
      "recommend_sample": true
    },
    {
      "sample_cost": 150000,
      "voi_currency": 655000.0000000006,
      "recommend_sample": true
    }
  ],
  "false_prime_consequence_sweep": [
    {
      "false_prime_consequence": 20000,
      "economic_preferred_action": "PRIME_RELEASE_CANDIDATE"
    },
    {
      "false_prime_consequence": 60000,
      "economic_preferred_action": "PRIME_RELEASE_CANDIDATE"
    },
    {
      "false_prime_consequence": 120000,
      "economic_preferred_action": "HOLD"
    }
  ],
  "note": "Offline diagnostics on controlled fixtures; production policy parameters are unchanged. SIMULATION/ASSUMPTION."
}
```

## Sample-value analysis (illustrative demo only)
```json
{
  "source": "ILLUSTRATIVE DEMO FIXTURE (not plant-wide)",
  "voi_detail": {
    "voi_currency": 0.0,
    "el_min_now_currency": 8000.0,
    "expected_el_post_sample_currency": 68000.0,
    "sample_cost_currency": 28000.0,
    "applicable": false,
    "recommend_sample": false,
    "min_voi_threshold_currency": 0.0,
    "bins": [
      {
        "name": "GOOD",
        "probability": 1.0,
        "posterior_p_bad_PROXY": 0.02,
        "actions_available": [
          "PRIME_RELEASE_CANDIDATE",
          "HOLD",
          "ABSTAIN"
        ],
        "min_loss_action": "PRIME_RELEASE_CANDIDATE",
        "min_loss_currency": 68000.0
      },
      {
        "name": "BAD",
        "probability": 0.0,
        "posterior_p_bad_PROXY": 0.98,
        "actions_available": [
          "HOLD",
          "ABSTAIN"
        ],
        "min_loss_action": "HOLD",
        "min_loss_currency": 20000.00000000002
      }
    ],
    "reason": "sampling cannot change the permissible action set",
    "provenance": "SIMULATED",
    "voi_model_version": "voi-discrete-v1",
    "note": "Deterministic discrete-outcome VOI approximation (SIMULATED). Not a validated information value."
  },
  "resulting_recommendation": "SAMPLE_NOW"
}
```

## Economic sanity
```json
{
  "no_double_counting": true,
  "mass_non_negative": true,
  "recoverable_bounded": true,
  "realized_value_present": true,
  "counterfactual_labelled": true,
  "realized_separate_from_counterfactual": true,
  "all_passed": true
}
```

## Determinism evidence
```json
{
  "fingerprint_a": "13acf6841c4621b6",
  "fingerprint_b": "13acf6841c4621b6",
  "identical": true
}
```

## Evidence ladder
```json
{
  "E0": "assumption",
  "E1": "theory / formulation",
  "E2": "synthetic simulation",
  "E3": "controlled prototype",
  "E4": "historical / public-data validation",
  "E5": "industrial validation"
}
```

## Claim ledger
```json
[
  {
    "topic": "quality_accuracy",
    "claim": "The GBM point estimator achieves a measurable MAE/RMSE on the frozen synthetic locked set.",
    "evidence": "locked point metrics",
    "source_artifact": "final_validation.json#quality",
    "evidence_level": "E2",
    "allowed_wording": "on simulated data the estimator shows MAE=\u2026",
    "prohibited_wording": "proven accurate / R2>0.95 on plant data"
  },
  {
    "topic": "uncertainty",
    "claim": "Split-conformal intervals report empirical coverage near nominal on the locked set, from only a few INDEPENDENT events.",
    "evidence": "locked coverage/width + n_events",
    "source_artifact": "final_validation.json#quality",
    "evidence_level": "E2",
    "allowed_wording": "intervals are calibrated on simulated data (3 independent cal events)",
    "prohibited_wording": "141 independent validation points / field-calibrated"
  },
  {
    "topic": "ood",
    "claim": "The applicability layer forces ABSTAIN on OOD / unsupported grade pairs.",
    "evidence": "robustness matrix",
    "source_artifact": "final_validation.json#robustness",
    "evidence_level": "E3",
    "allowed_wording": "OOD inputs are refused by design",
    "prohibited_wording": "detects all real plant anomalies"
  },
  {
    "topic": "material_mapping",
    "claim": "Residence-time material mapping ties a decision to a downstream window with explicit uncertainty.",
    "evidence": "material window summary",
    "source_artifact": "replay/material_service",
    "evidence_level": "E2",
    "allowed_wording": "simulated residence mapping with surfaced uncertainty",
    "prohibited_wording": "digital-twin / plant-calibrated / exact material tracking"
  },
  {
    "topic": "false_prime_protection",
    "claim": "On the locked set PrimePath produced 0 t false-prime mass vs the baselines.",
    "evidence": "replay comparison",
    "source_artifact": "final_validation.json#decision",
    "evidence_level": "E2",
    "allowed_wording": "on this synthetic corpus PrimePath avoided false-prime mass",
    "prohibited_wording": "guarantees zero bad releases / safety-certified"
  },
  {
    "topic": "false_hold_value",
    "claim": "PrimePath's conservatism carries a false-hold/opportunity cost, reported explicitly.",
    "evidence": "replay + economics",
    "source_artifact": "final_validation.json#economic",
    "evidence_level": "E2",
    "allowed_wording": "conservatism has a quantified opportunity cost on simulated data",
    "prohibited_wording": "net savings proven / realized plant value"
  },
  {
    "topic": "sampling",
    "claim": "VOI recommends SAMPLE NOW only when it can change the permissible action and VOI>threshold.",
    "evidence": "demo VOI",
    "source_artifact": "final_validation.json#sample_value",
    "evidence_level": "E3",
    "allowed_wording": "sampling value illustrated on a controlled fixture",
    "prohibited_wording": "plant-wide sampling savings"
  },
  {
    "topic": "annual_value",
    "claim": "Annual value is a SCENARIO function of explicit inputs.",
    "evidence": "scale-up function",
    "source_artifact": "economics.scale_up_annual",
    "evidence_level": "E0",
    "allowed_wording": "illustrative scenario: value = transitions\u00d7episode\u00d7availability\u00d7adoption",
    "prohibited_wording": "\u20b9X Cr/year savings / fixed annual benefit"
  },
  {
    "topic": "hmel_applicability",
    "claim": "The approach is framed for polyolefin grade transitions; no HMEL data was used.",
    "evidence": "design docs",
    "source_artifact": "FINAL_VALIDATION_REPORT.md",
    "evidence_level": "E1",
    "allowed_wording": "conceptually applicable to grade transitions",
    "prohibited_wording": "validated on HMEL / HMEL-approved / plant-proven"
  },
  {
    "topic": "scalability",
    "claim": "The architecture is modular and deterministic.",
    "evidence": "module layout + tests",
    "source_artifact": "test suite",
    "evidence_level": "E3",
    "allowed_wording": "prototype is modular and reproducible",
    "prohibited_wording": "production-ready / deployed at scale"
  },
  {
    "topic": "safety_authority",
    "claim": "PrimePath is ADVISORY; PRIME-RELEASE CANDIDATE always requires human/QC authorization.",
    "evidence": "disposition engine",
    "source_artifact": "disposition.py",
    "evidence_level": "E1",
    "allowed_wording": "advisory decision support requiring human authorization",
    "prohibited_wording": "autonomous release / certifies material / writes setpoints"
  }
]
```

## Limitations
- Synthetic corpus; 141 calibration rows from only 3 independent events.
- Locked corpus yields 0 natural PRIME candidates; prime behaviour is shown only via the labelled illustrative demo.
- Economics are SIMULATED/ILLUSTRATIVE; no HMEL cost or saving is implied.
- Oracle is DIAGNOSTIC ONLY, not achievable in deployment.
- No historical/industrial (E4/E5) validation has been performed.

## Pass/Fail criteria (success is NOT 'lowest metric')
```json
{
  "no_leakage": true,
  "deterministic_replay": true,
  "correct_hard_gate_behavior": true,
  "uncertainty_reported_honestly": true,
  "economic_accounting_reconciles": true,
  "counterfactual_realized_separated": true,
  "every_claim_traceable": true,
  "limitations_exposed": true,
  "decision_behavior_understandable": true,
  "no_unsupported_hmel_claim": true,
  "all_passed": true
}
```

**All criteria passed: True**

## Recommendation before Phase 14
Phase 14 (UI) may proceed. Before it, surface the abstention decomposition and the LOCKED-vs-DEMO separation prominently so the jury sees PrimePath's conservatism is gate-justified, not a defect. Do NOT weaken gates to raise candidate rate on this synthetic corpus.
