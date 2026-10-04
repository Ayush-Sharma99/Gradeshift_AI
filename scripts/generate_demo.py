"""CLI entry point for the GradeShift PrimePath canonical illustrative demo.

Demonstrates the in-domain Grade A -> B transition walkthrough from `replay.demo_fixture`:
  T1: HOLD (point in-spec, interval crosses limit)
  T2: SAMPLE_NOW (sample would resolve material uncertainty)
  T3: PRIME_RELEASE_CANDIDATE (interval in-spec, dwell ok, supported, normal)
  T4: Post-horizon laboratory truth revealed & reconciled
  T5: Episode economic ledger (realized vs counterfactual value)
  FAULT_BRANCH: Frozen online sensor -> ABSTAIN (from robustness_matrix)

IMPORTANT: This output is ILLUSTRATIVE_DEMO (SIMULATED/ASSUMPTION) and is strictly
separate from LOCKED_VALIDATION.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gradeshift import config as C
from gradeshift import replay as RP
from gradeshift import validation as V


def main() -> int:
    scenario = C.get_scenario(C.DEFAULT_SCENARIO)
    demo = RP.demo_fixture(scenario)
    rm = V.robustness_matrix()
    frozen_row = next(r for r in rm["rows"] if r["scenario"] == "frozen_sensor")

    print("=" * 76)
    print("GRADESHIFT PRIMEPATH - CANONICAL ILLUSTRATIVE DEMO (SIMULATED / ASSUMPTION)")
    print("NOTE: Kept strictly separate from LOCKED_VALIDATION.")
    print("=" * 76)
    print(f"Label      : {demo.get('label')}")
    print(f"Event ID   : {demo.get('event_id')} (seed={demo.get('frozen_seed')})")
    print(f"Scenario   : {scenario.name} (Prime INR {scenario.prime_price:,.0f}/t, Downgrade INR {scenario.downgrade_price:,.0f}/t)")
    print("-" * 76)
    for step in demo["steps"]:
        t = step.get("t")
        narrative = step.get("narrative", "")
        if "action" in step:
            print(f"[{t}] {narrative}")
            print(f"     Action   : {step['action']} (Expected: {step.get('expected')})")
            print(f"     Reasons  : {', '.join(step.get('reason_codes', []))}")
        elif "revealed_mfi" in step:
            print(f"[{t}] {narrative}")
            print(f"     Lab Truth: {step['revealed_mfi']:.2f} g/10min (was_in_spec={step['was_in_spec']})")
        elif "ledger" in step:
            led = step["ledger"]
            print(f"[{t}] {narrative}")
            print(f"     Realized Value          : INR {led.get('realized_value_currency', 0):,.0f}")
            print(f"     Counterfactual Value    : INR {led.get('counterfactual_opportunity_currency', 0):,.0f}")
    print("-" * 76)
    print(f"[FAULT_BRANCH] Scenario: {frozen_row['scenario']}")
    print(f"     Action   : {frozen_row['observed_action']} (Expected: {frozen_row['expected_forced_action']})")
    print(f"     Reasons  : {', '.join(frozen_row['reason_codes'])}")
    print("=" * 76)
    if "--json" in sys.argv:
        print(json.dumps({"demo_fixture": demo, "fault_branch": frozen_row}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
