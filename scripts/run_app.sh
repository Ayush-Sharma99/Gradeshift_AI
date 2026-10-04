#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
export PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH:-}"

PORT="${1:-8501}"
echo "[GradeShift PrimePath] Launching Streamlit application on port $PORT..."
python -m streamlit run app.py --server.port "$PORT"
