param(
    [switch]$Fast
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    $env:PYTHONPATH = "$RepoRoot\src"
    if ($Fast) {
        Write-Host "[GradeShift PrimePath] Running fast unit test subset..." -ForegroundColor Cyan
        python -m pytest -v -k "not test_final_validation and not test_calibration_reproducible and not test_reproducible_pipeline"
    } else {
        Write-Host "[GradeShift PrimePath] Running complete 266-test suite (expected runtime ~6.5 min on CPU)..." -ForegroundColor Cyan
        python -m pytest -v --durations=10
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
