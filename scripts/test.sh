#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH:-}"

if [[ "${1:-}" == "--fast" ]]; then
    echo "[GradeShift PrimePath] Running fast unit test subset..."
    python -m pytest -v -k "not test_final_validation and not test_calibration_reproducible and not test_reproducible_pipeline"
else
    echo "[GradeShift PrimePath] Running complete 266-test suite (expected runtime ~6.5 min on CPU)..."
    python -m pytest -v --durations=10
fi
