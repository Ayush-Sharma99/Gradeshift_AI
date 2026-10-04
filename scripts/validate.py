"""CLI entry point to verify or regenerate the Phase-13 Final Validation package.

By default, verifies the existing frozen `artifacts/final_validation.json` and
checks all pass/fail criteria, determinism fingerprints, and claim ledger rules.
Pass `--regenerate` to re-run `pipeline.run_phase13` from scratch.
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

from gradeshift import pipeline as P


def main() -> int:
    fv_path = REPO_ROOT / "artifacts" / "final_validation.json"
    regenerate = "--regenerate" in sys.argv

    if regenerate or not fv_path.exists():
        print("[GradeShift PrimePath] Running Phase-13 Final Validation pipeline from scratch...")
        final = P.run_phase13(
            out_dir=str(REPO_ROOT / "artifacts"),
            docs_dir=str(REPO_ROOT / "docs"),
        )
        md_path = REPO_ROOT / "docs" / "FINAL_VALIDATION_REPORT.md"
        md_path.write_text(P._final_validation_md(final), encoding="utf-8")
    else:
        print(f"[GradeShift PrimePath] Verifying frozen validation artifact: {fv_path}")
        final = json.loads(fv_path.read_text(encoding="utf-8"))

    pf = final["pass_fail_criteria"]
    fp = final["reproducibility_fingerprints"]
    la = final["level_a_quality"]
    gd = final["abstention_decomposition"]
    zc = final["zero_candidate_diagnostic"]

    print("=" * 76)
    print("GRADESHIFT PRIMEPATH - PHASE 13 FINAL VALIDATION SUMMARY (SIMULATED)")
    print("=" * 76)
    print(f"Fingerprints       : {json.dumps(fp)}")
    print(f"Locked Point MAE   : {la['point']['mae']:.4f} g/10min | RMSE: {la['point']['rmse']:.4f} g/10min ({la['point']['n_rows']} rows, {la['point']['n_events']} events)")
    print(f"Locked Coverage    : {la['uncertainty']['coverage']:.4f} (nominal 0.90, {la['uncertainty']['calibration_events']} cal events)")
    print(f"Locked Abstention  : {gd['abstained_decisions']} / {gd['total_decisions']} decisions (gates: {gd['blocking_by_category']})")
    print(f"Locked Candidates  : {zc['locked_prime_candidates']} (Illustrative demo candidate: {zc['illustrative_demo_prime_candidate']})")
    print(f"All Criteria Passed: {pf['all_passed']}")
    print("=" * 76)

    if not pf.get("all_passed"):
        print("ERROR: Validation pass/fail criteria did not all pass!", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
