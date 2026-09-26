# Run the AgentBus test suite with the right interpreter and PYTHONPATH.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1 tests/test_providers.py
#   powershell -NoProfile -ExecutionPolicy Bypass -File run-tests.ps1 -k budget
#
# The virtualenv may live outside the repo (a cloud-backed working copy is too
# slow to hold 11k venv files), so it is looked up rather than assumed.

param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path

# candidate interpreters, first match wins
$candidates = @(
    (Join-Path $Repo '.venv\Scripts\python.exe'),
    'D:\Workspace\.venv\Scripts\python.exe',
    "$env:USERPROFILE\Workspace\.venv\Scripts\python.exe"
)
$py = $null
foreach ($c in $candidates) {
    if (Test-Path -LiteralPath $c) { $py = $c; break }
}
if (-not $py) {
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) { $py = $found.Source }
}
if (-not $py) {
    Write-Error "no python interpreter found (looked for .venv next to the repo and in D:\Workspace)"
    exit 1
}

# pytest has to be importable, otherwise fall through to the next candidate
& $py -c "import pytest" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "interpreter without pytest: $py" -ForegroundColor Yellow
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found -and $found.Source -ne $py) { $py = $found.Source }
}

$env:PYTHONPATH = "$Repo\src;$Repo"
Write-Host "python : $py"
& $py -c "import sys; print('version:', sys.version.split()[0])"
Write-Host "repo   : $Repo"
Write-Host ""

Push-Location $Repo
try {
    & $py -m pytest @Rest
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
