"""One-Command Competition Demo Runner for GradeShift PrimePath.

Executes the full UI Presenter Walkthrough (`build_demo_walkthrough` +
`build_locked_validation_view` + `build_executive_view`) to verify and print:
  1. Illustrative Demo Steps T1..T6 (`HOLD` -> `SAMPLE_NOW` -> `PRIME_RELEASE_CANDIDATE`
     -> Lab Truth Reconciled -> Economic Ledger -> Frozen Sensor `ABSTAIN`)
  2. Locked Validation Summary (100% OOD Abstention, 0.0 t False-Prime Mass)
  3. SHA-256 Reproducibility Fingerprints & Pass/Fail Verification

Pass `--ui` to launch the interactive Streamlit Decision Cockpit after verification.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gradeshift.ui import (
    build_demo_walkthrough,
    build_executive_view,
    build_locked_validation_view,
    load_runtime_context,
)


def main() -> int:
    rt = load_runtime_context()
    demo = build_demo_walkthrough(rt, scenario_name="BASE")
    lv = build_locked_validation_view(rt)
    ex = build_executive_view(rt, scenario_name="BASE")

    print("=" * 80)
    print("GRADESHIFT PRIMEPATH — PHASE 14–17 PRODUCT & DEMO VERIFICATION")
    print(f"Product : {ex['product_definition']}")
    print(f"Versions: {rt.versions}")
    print("=" * 80)
    print("\n[SECTION A] ILLUSTRATIVE DEMO WALKTHROUGH (DEMO-A2B — NOT VALIDATION EVIDENCE)")
    print("-" * 80)
    for s in demo["steps"]:
        pred = s["prediction"]
        print(f"  {s['step_id']:<20} | t={s['t_min']:>3}m | Action: {s['action']:<24}")
        print(
            f"    Interval: [{pred['lower_mfi']:.2f}, {pred['upper_mfi']:.2f}] g/10m "
            f"(Point {pred['point_mfi']:.2f}) vs Spec [{s['spec_band']['mfi_low']:.2f}, {s['spec_band']['mfi_high']:.2f}]"
        )
        print(
            f"    Gates   : Hard {s['hard_gates_passed']}/{s['hard_gates_total']} PASS | "
            f"Candidacy {s['candidacy_gates_passed']}/{s['candidacy_gates_total']} PASS | "
            f"Reasons: {', '.join(s['reason_codes'])}"
        )
        if s.get("revealed_mfi") is not None:
            print(
                f"    Truth   : Revealed Lab MFI = {s['revealed_mfi']:.2f} g/10m "
                f"(in_spec={s['was_in_spec']}) | Counterfactual Spread = INR {s['economics']['counterfactual_opportunity_currency']:,.0f}"
            )

    print("\n[SECTION B] LOCKED VALIDATION EVIDENCE (5 UNSEEN EPISODES, 235 DECISIONS)")
    print("-" * 80)
    lb = lv["level_b_decision"]
    lc = lv["level_c_economic"]
    for pol in ["SOP_FIXTURE", "POINT_THRESHOLD", "PRIMEPATH", "ORACLE_DIAGNOSTIC_ONLY"]:
        if pol in lb:
            fp_t = lb[pol].get("false_prime_mass_tonnes", 0.0)
            fh_t = lb[pol].get("false_hold_mass_tonnes", 0.0)
            abst = 100.0 * float(lb[pol].get("mean_abstention_rate", 0.0))
            fp_inr = float(lc.get(pol, {}).get("false_prime_exposure_currency", 0.0))
            print(
                f"  {pol:<24} | False-Prime: {fp_t:>6.1f} t (INR {fp_inr:>10,.0f}) | "
                f"False-Hold: {fh_t:>5.1f} t | Abstain: {abst:>5.1f}%"
            )

    print("\n[SECTION C] REPRODUCIBILITY FINGERPRINTS & PASS/FAIL CRITERIA")
    print("-" * 80)
    for k, v in lv["fingerprints"].items():
        print(f"  {k:<12}: {v}")
    all_ok = lv["pass_fail_criteria"].get("all_passed", False)
    print(f"  All 10 Phase-13 Validation Criteria Passed: {all_ok}")
    print("=" * 80)

    if "--ui" in sys.argv:
        print("Launching GradeShift PrimePath Streamlit Decision Cockpit...")
        return subprocess.call(
            [sys.executable, "-m", "streamlit", "run", str(REPO_ROOT / "app.py")]
        )
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
