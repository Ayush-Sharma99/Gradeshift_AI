"""Central configuration — the single source of truth for grades, specifications,
economic assumptions, and policy thresholds.

No page or module may redefine grade/spec/economic numbers locally (fixes the
inherited duplication defect). Every economic value carries a Provenance label.
All values here are SIMULATED/ASSUMPTION for the POC unless marked otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .provenance import Provenance

# ──────────────────────────────────────────────────────────────────────────
# GRADES & SPECIFICATIONS
# Analyte of record for the POC: Melt Flow Index (MFI, g/10min, ASTM D1238).
# Spec band is two-sided fractional around target. Dwell = minutes the material
# window must satisfy the interval policy before PRIME-RELEASE CANDIDATE.
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GradeSpec:
    grade_id: str
    name: str
    short: str
    target_mfi: float          # g/10min
    spec_frac: float           # ± fractional band (0.05 = ±5%)
    density: float             # g/cm3 (context only in POC)
    dwell_min: float           # minutes the window must hold before candidacy
    version: str = "spec-v1"

    @property
    def mfi_low(self) -> float:
        return self.target_mfi * (1.0 - self.spec_frac)

    @property
    def mfi_high(self) -> float:
        return self.target_mfi * (1.0 + self.spec_frac)

    def in_spec(self, mfi: float) -> bool:
        return self.mfi_low <= mfi <= self.mfi_high


GRADES: dict[str, GradeSpec] = {
    "A": GradeSpec("A", "HDPE Pipe (PE100)", "HDPE-P", target_mfi=0.30, spec_frac=0.20,
                   density=0.949, dwell_min=30.0),
    "B": GradeSpec("B", "HDPE Blow Moulding", "HDPE-BM", target_mfi=8.00, spec_frac=0.05,
                   density=0.954, dwell_min=30.0),
    "C": GradeSpec("C", "LLDPE Film Grade", "LLDPE-F", target_mfi=1.00, spec_frac=0.10,
                   density=0.918, dwell_min=30.0),
}

CANONICAL_GRADE_FROM = "A"
CANONICAL_GRADE_TO = "B"


# ──────────────────────────────────────────────────────────────────────────
# ECONOMICS  (episode-level; LOW / BASE / HIGH scenarios)
# Physical quantity, accounting price, and consequence assumptions kept separate.
# All ASSUMPTION/ILLUSTRATIVE for the POC — never presented as measured HMEL value.
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EconScenario:
    name: str
    prime_price: float          # ₹/tonne for prime material
    downgrade_price: float      # ₹/tonne for off-spec/wide-spec routing
    false_prime_consequence: float  # ₹/tonne penalty if bad material released as candidate
    sample_cost: float          # ₹ per additional lab sample (workflow+analysis)
    workflow_cost: float        # ₹ fixed per disposition action
    provenance: Provenance = Provenance.ASSUMPTION

    @property
    def downgrade_spread(self) -> float:
        """₹/tonne lost when prime-eligible material is routed to downgrade."""
        return self.prime_price - self.downgrade_price


ECON_SCENARIOS: dict[str, EconScenario] = {
    # Prices in ₹/tonne. Spread values are illustrative, consistent with a
    # ₹15–25/kg prime-vs-downgrade gap discussed in the submitted deck (ASSUMPTION).
    "LOW":  EconScenario("LOW",  prime_price=90_000, downgrade_price=78_000,
                         false_prime_consequence=40_000, sample_cost=15_000, workflow_cost=5_000),
    "BASE": EconScenario("BASE", prime_price=95_000, downgrade_price=75_000,
                         false_prime_consequence=60_000, sample_cost=20_000, workflow_cost=8_000),
    "HIGH": EconScenario("HIGH", prime_price=98_000, downgrade_price=73_000,
                         false_prime_consequence=90_000, sample_cost=25_000, workflow_cost=10_000),
}
DEFAULT_SCENARIO = "BASE"


# ──────────────────────────────────────────────────────────────────────────
# POLICY  (gates & thresholds for the decision engine)
# ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Policy:
    version: str = "policy-v1"
    nominal_coverage: float = 0.90        # conformal interval nominal level
    # Candidate requires the WHOLE prediction interval inside spec (two-sided).
    # p(bad) must be below this to even consider candidacy.
    max_bad_prob_for_candidate: float = 0.05
    # VOI must exceed this (₹) to recommend SAMPLE NOW.
    voi_threshold: float = 0.0
    # Sampling only useful if a result can arrive within this horizon (min)
    # before the decision becomes irrelevant.
    sample_result_latency_min: float = 45.0
    decision_horizon_min: float = 240.0
    # OOD / applicability
    max_ood_score: float = 0.0            # IsolationForest decision_function >= this is in-support
    # Recommendation validity
    recommendation_expiry_min: float = 30.0
    required_approver: str = "Shift Quality Approver (QC)"


POLICY = Policy()


# Convenience accessors ----------------------------------------------------

def get_grade(grade_id: str) -> GradeSpec:
    if grade_id not in GRADES:
        raise KeyError(f"Unknown grade '{grade_id}'. Known: {sorted(GRADES)}")
    return GRADES[grade_id]


def get_scenario(name: str = DEFAULT_SCENARIO) -> EconScenario:
    if name not in ECON_SCENARIOS:
        raise KeyError(f"Unknown economic scenario '{name}'. Known: {sorted(ECON_SCENARIOS)}")
    return ECON_SCENARIOS[name]
