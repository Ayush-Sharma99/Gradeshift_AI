param(
    [switch]$UI
)
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
if ($UI) {
    python scripts/demo.py --ui
} else {
    python scripts/demo.py
}
