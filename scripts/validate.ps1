param(
    [switch]$Regenerate
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot
try {
    $env:PYTHONPATH = "$RepoRoot\src"
    if ($Regenerate) {
        python scripts\validate.py --regenerate
    } else {
        python scripts\validate.py
    }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
