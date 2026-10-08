<#
.SYNOPSIS
    Run the AgentBus test suite with the project's real interpreter.

.DESCRIPTION
    Wraps pytest so the user never has to activate a venv or set PYTHONPATH by
    hand. Resolves the interpreter in this order:

      1. $env:AGENTBUS_PYTHON           (explicit override)
      2. D:\Workspace\.venv\Scripts\python.exe   (the shared venv, kept off Drive)
      3. .\.venv\Scripts\python.exe               (project-local fallback)
      4. python on PATH

    Exits with pytest's exit code so it can gate CI.

.PARAMETER PytestArgs
    Paths or pytest flags. Defaults to the whole suite.

.EXAMPLE
    .\scripts\run_tests.ps1
    Full suite.

.EXAMPLE
    .\scripts\run_tests.ps1 tests/test_bus_edge_cases.py -v
    One file, verbose.

.EXAMPLE
    .\scripts\run_tests.ps1 -k "health or bus" -x
    Keyword filter, stop at first failure.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $PytestArgs
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot

function Resolve-Python {
    $candidates = @()
    if ($env:AGENTBUS_PYTHON) { $candidates += $env:AGENTBUS_PYTHON }
    $candidates += 'D:\Workspace\.venv\Scripts\python.exe'
    $candidates += (Join-Path $Root '.venv\Scripts\python.exe')

    foreach ($c in $candidates) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }

    $onPath = Get-Command python -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }

    throw "Python not found. Set AGENTBUS_PYTHON to a python.exe, or create .venv."
}

$python = Resolve-Python

# pytest.ini sets pythonpath = . src, but only when pytest picks it up as the
# rootdir config. Exporting PYTHONPATH keeps imports working even when a stray
# pyproject.toml takes precedence (pytest 9 ignores pytest.ini in that case).
$env:PYTHONPATH = @("$Root\src", $Root, $env:PYTHONPATH) -ne $null -join [IO.Path]::PathSeparator
$env:PYTHONIOENCODING = 'utf-8'

$version = & $python -c "import sys; print(sys.version.split()[0])" 2>&1
Write-Host "Python : $version"
Write-Host "Runner : $python"
Write-Host "Root   : $Root"
Write-Host "Args   : $(if ($PytestArgs) { $PytestArgs -join ' ' } else { '<full suite>' })"
Write-Host ('-' * 62)

if (-not $PytestArgs) { $PytestArgs = @() }

& $python -m pytest -p no:cacheprovider @PytestArgs
$code = $LASTEXITCODE

Write-Host ('-' * 62)
switch ($code) {
    0       { Write-Host 'RESULT: GREEN - all tests passed' -ForegroundColor Green }
    1       { Write-Host 'RESULT: RED - failures present' -ForegroundColor Red }
    5       { Write-Host 'RESULT: NO TESTS COLLECTED' -ForegroundColor Yellow }
    default { Write-Host "RESULT: pytest exit code $code" -ForegroundColor Yellow }
}

exit $code