param(
    [int]$Port = 8501,
    [switch]$Headless
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    $env:PYTHONPATH = "$RepoRoot\src"
    Write-Host "[GradeShift PrimePath] Launching Streamlit application on port $Port..." -ForegroundColor Cyan
    if ($Headless) {
        python -m streamlit run app.py --server.port $Port --server.headless true
    } else {
        python -m streamlit run app.py --server.port $Port
    }
} finally {
    Pop-Location
}
