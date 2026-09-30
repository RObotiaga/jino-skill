param(
    [string]$Source = (Split-Path -Parent $PSScriptRoot)
)
$ErrorActionPreference = 'Stop'
$sourcePath = (Resolve-Path -LiteralPath $Source).Path
if (-not (Test-Path -LiteralPath (Join-Path $sourcePath 'pyproject.toml'))) {
    throw 'Source must point to the jino-domains-sdk project.'
}
$skillRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $skillRoot 'runtime'
$python = Join-Path $runtime 'Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & py -3 -m venv $runtime
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Jino Python environment.' }
}
& $python -m pip install --disable-pip-version-check $sourcePath
if ($LASTEXITCODE -ne 0) { throw 'Could not install the Jino SDK.' }
& $python -B -m jino_domains_sdk status
if ($LASTEXITCODE -ne 0) { throw 'Installed CLI failed to start.' }
