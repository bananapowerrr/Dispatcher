# Push FROM G:\Мой диск\AgentBus (this folder) TO github.com/bananapowerrr/Dispatcher
# No D:\Workspace\Dispatcher. Git lives inside AgentBus on Google Drive.
#
# First time (once):
#   cd "G:\Мой диск\AgentBus"
#   powershell -ExecutionPolicy Bypass -File .\push_agentbus_to_git.ps1 -Init
#
# Every push after edits:
#   powershell -ExecutionPolicy Bypass -File .\push_agentbus_to_git.ps1
#   powershell -ExecutionPolicy Bypass -File .\push_agentbus_to_git.ps1 "commit message"

param(
    [switch]$Init,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CommitMessage
)

$ErrorActionPreference = "Stop"

# Always use this folder as repo root (where the script lives / AgentBus)
$Root = if ($env:AGENTBUS_DRIVE) { $env:AGENTBUS_DRIVE } else { Split-Path -Parent $MyInvocation.MyCommand.Path }
if (-not $Root) { $Root = "G:\Мой диск\AgentBus" }
$Branch = if ($env:DISPATCHER_BRANCH) { $env:DISPATCHER_BRANCH } else { "main" }
$RemoteUrl = "https://github.com/bananapowerrr/Dispatcher.git"

Set-Location -LiteralPath $Root
Write-Host "=== Git push AgentBus -> $RemoteUrl ===" -ForegroundColor Cyan
Write-Host "Repo root: $Root"

if (-not (Test-Path -LiteralPath (Join-Path $Root "dispatcher.py"))) {
    throw "dispatcher.py not found in $Root"
}
if (-not (Test-Path -LiteralPath (Join-Path $Root "core\runtime.py"))) {
    throw "core\runtime.py not found - wait for Drive sync"
}

# Ensure .gitignore exists
$gi = Join-Path $Root ".gitignore"
if (-not (Test-Path -LiteralPath $gi)) {
    @"
channels/
.env
credentials/
archive/
__pycache__/
*.pyc
*.log
rate_limit_until.json
cloud_usage.json
.pytest_cache/
.gemini/
GeminiProcessed/
"@ | Set-Content -LiteralPath $gi -Encoding UTF8
    Write-Host "created .gitignore"
}

if (-not (Test-Path -LiteralPath (Join-Path $Root ".git"))) {
    if (-not $Init) {
        Write-Host "No .git here. Run once with -Init:" -ForegroundColor Yellow
        Write-Host "  powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Init"
        exit 1
    }
    Write-Host "git init..." -ForegroundColor Yellow
    git init
    git branch -M $Branch
    git remote remove origin 2>$null
    git remote add origin $RemoteUrl
    Write-Host "remote origin = $RemoteUrl"
} else {
    # ensure remote
    $cur = git remote get-url origin 2>$null
    if (-not $cur) {
        git remote add origin $RemoteUrl
    } elseif ($cur -ne $RemoteUrl) {
        git remote set-url origin $RemoteUrl
        Write-Host "origin updated -> $RemoteUrl"
    }
}

# Stage only code (gitignore excludes channels/.env/...)
git add dispatcher.py README.md .gitignore push_agentbus_to_git.ps1 start_dispatcher.ps1 2>$null
git add core 2>$null
git add .gitignore

# show status
git status -sb

$porcelain = git status --porcelain
if (-not $porcelain) {
    Write-Host "No changes to commit." -ForegroundColor Green
    exit 0
}

if ($CommitMessage -and $CommitMessage.Count -gt 0) {
    $msg = ($CommitMessage -join " ")
} else {
    $msg = "AgentBus sync $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
}

git commit -m $msg

# First push may need --force if remote has old unrelated history
$pushOut = git push -u origin $Branch 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host $pushOut -ForegroundColor Yellow
    Write-Host ""
    Write-Host "If rejected (unrelated histories), one-time force push:" -ForegroundColor Yellow
    Write-Host "  git push -u origin $Branch --force"
    Write-Host "Only do this if you intend to REPLACE remote with AgentBus code." -ForegroundColor Yellow
    exit 1
}

Write-Host "OK https://github.com/bananapowerrr/Dispatcher" -ForegroundColor Green
