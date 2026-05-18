# ORUUN Market Radar — Weekly local refresh
# Run this every Monday morning. It runs all data fetchers from your local IP
# (which dodges the GHA rate-limits that have killed Trends and throttled
# autocomplete in cloud runs), generates blog drafts, then pushes to GitHub.
#
# Usage:
#   - Double-click run_weekly.bat   (simplest)
#   - OR right-click run_weekly.ps1 -> Run with PowerShell
#   - OR from a PowerShell prompt: .\run_weekly.ps1

$ErrorActionPreference = "Continue"   # let individual fetchers fail without aborting
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

$REPO_DIR = $PSScriptRoot

function Say-Header($t) { Write-Host ""; Write-Host "================================================" -ForegroundColor Cyan; Write-Host "  $t" -ForegroundColor Cyan; Write-Host "================================================" -ForegroundColor Cyan }
function Say-Step($t)   { Write-Host ""; Write-Host "--> $t" -ForegroundColor Cyan }
function Say-OK($t)     { Write-Host "[OK]   $t" -ForegroundColor Green }
function Say-Warn($t)   { Write-Host "[WARN] $t" -ForegroundColor Yellow }
function Say-Err($t)    { Write-Host "[ERR]  $t" -ForegroundColor Red }

Say-Header "ORUUN Market Radar - Weekly Refresh"
Write-Host "Working directory: $REPO_DIR"

if (-not (Test-Path (Join-Path $REPO_DIR "keywords.yaml"))) {
    Say-Err "keywords.yaml not found in $REPO_DIR"
    Say-Err "This script must live in the project root (next to keywords.yaml)."
    Read-Host "Press Enter to exit"
    exit 1
}
Set-Location $REPO_DIR

# --- 1. Python check ---
try {
    $pyVer = python --version 2>&1
    Say-OK "Python: $pyVer"
} catch {
    Say-Err "Python not installed. Install from https://www.python.org/downloads/"
    Read-Host "Press Enter to exit"
    exit 1
}

# --- 2. Venv setup (one-time) ---
$venv = Join-Path $REPO_DIR ".venv"
if (-not (Test-Path $venv)) {
    Say-Step "Creating Python venv (~30 seconds, one-time)"
    python -m venv $venv
    if ($LASTEXITCODE -ne 0) {
        Say-Err "venv creation failed"
        Read-Host "Press Enter to exit"
        exit 1
    }
}
$venvPy = Join-Path $venv "Scripts\python.exe"

Say-Step "Installing/updating dependencies"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -r requirements.txt --quiet
Say-OK "Dependencies ready"

# --- 3. Git pull so we don't drift from remote ---
Say-Step "Pulling latest from GitHub"
git pull --rebase 2>&1 | Write-Host
if ($LASTEXITCODE -ne 0) {
    Say-Warn "git pull had issues. If 'pull --rebase' is mid-conflict, run 'git rebase --abort' then re-run."
}

# --- 4. Set env vars for fetchers ---
$env:AUTOCOMPLETE_DEPTH = "rich"   # 11 variations locally
# ANTHROPIC_API_KEY can be exported beforehand. If unset, blog generation skips.

# --- 5. Run fetchers in order. Each runs even if previous failed. ---
Say-Header "Data collection (5-8 minutes)"

Say-Step "Fetching Google Autocomplete (11 variations x 63 keywords)"
& $venvPy scripts/fetch_autocomplete.py

Say-Step "Fetching Google Trends (may take a few minutes; OK if it fails)"
& $venvPy scripts/fetch_trends.py

# Optional bonus signals — uncomment to enable when running locally.
# These are skipped by default because we removed the brand-tracking sections.
#Say-Step "Fetching Wikipedia pageviews"
#& $venvPy scripts/fetch_wikipedia.py
#Say-Step "Fetching GDELT news mentions"
#& $venvPy scripts/fetch_gdelt.py
#Say-Step "Fetching Hacker News chatter"
#& $venvPy scripts/fetch_hackernews.py

# --- 6. Analyze + build dashboard ---
Say-Header "Analyze + build dashboard"
& $venvPy scripts/analyze.py
& $venvPy scripts/build_dashboard_data.py

# --- 7. Generate blog drafts ---
if ($env:ANTHROPIC_API_KEY) {
    Say-Header "Generate blog drafts (Claude API)"
    & $venvPy scripts/generate_blogs.py
} else {
    Say-Warn "ANTHROPIC_API_KEY not set in your environment - skipping blog generation."
    Say-Warn "To enable: \$env:ANTHROPIC_API_KEY = 'sk-ant-...' before running, OR set it permanently in System Environment Variables."
}

# --- 8. Show summary ---
Say-Header "Refresh summary"
$analyzed_path = Join-Path $REPO_DIR "data\analyzed.json"
if (Test-Path $analyzed_path) {
    $d = Get-Content $analyzed_path -Raw | ConvertFrom-Json
    Write-Host ("  Active sources       : " + ($d.data_sources_active -join ", "))
    Write-Host ("  Autocomplete seeds   : " + $d.autocomplete.Count)
    $total = 0
    foreach ($r in $d.autocomplete) { $total += $r.suggestions.Count }
    Write-Host ("  Total suggestions    : " + $total)
    Write-Host ("  Top buying-intent    : " + $d.top_buying_intent.Count)
    Write-Host ("  Long-tail discoveries: " + $d.long_tail.Count)
    if ($d.brand_sov_autocomplete) {
        Write-Host ("  Brand mentions       : " + $d.brand_sov_autocomplete.Count + " brands")
    }
    if ($d.blog_drafts -and $d.blog_drafts.drafts) {
        Write-Host ("  Blog drafts written  : " + $d.blog_drafts.drafts.Count)
    }
}

# --- 9. Ask before pushing ---
Write-Host ""
$answer = Read-Host "Push refreshed data to GitHub? (Y/n)"
if ($answer -eq "n" -or $answer -eq "N") {
    Say-Warn "Skipped push. Data is on your local machine only."
    Say-Warn "To push later: git add . ; git commit -m 'msg' ; git push"
    Read-Host "Press Enter to exit"
    exit 0
}

Say-Step "Committing and pushing"
git add docs/data.json data/*.json data/snapshots/*.json blogs/ 2>$null
$today = Get-Date -Format "yyyy-MM-dd"
git commit -m "chore(data): manual weekly refresh $today"
if ($LASTEXITCODE -ne 0) {
    Say-Warn "Nothing to commit (data unchanged) or commit failed."
}
git push
if ($LASTEXITCODE -eq 0) {
    Say-OK "Pushed successfully."
    Write-Host ""
    Write-Host "Dashboard will rebuild in ~1 minute. Visit:" -ForegroundColor Green
    Write-Host "  https://oruun.github.io/oruun-market-radar/" -ForegroundColor Green
} else {
    Say-Err "Push failed. Run 'git pull --rebase' then re-push manually."
}

Write-Host ""
Read-Host "Press Enter to close this window"
