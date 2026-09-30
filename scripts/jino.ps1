# Pass CLI arguments unchanged, including --flags and file paths with spaces.
$ErrorActionPreference = 'Stop'
$skillRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $skillRoot 'runtime/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    Write-Error 'Jino runtime is missing. Run scripts/install.ps1 -Source <SDK directory>.'
    exit 2
}
& $python -B -m jino_domains_sdk @args
exit $LASTEXITCODE
