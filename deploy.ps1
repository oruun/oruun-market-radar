# ORUUN Market Radar - One-shot deploy script for Windows
# Run via deploy.bat (double-click) or:
#   powershell -NoProfile -ExecutionPolicy Bypass -File deploy.ps1

# Force UTF-8 console output to avoid garbled chars on Chinese Windows
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

$ErrorActionPreference = "Stop"

function Say-Header($text) {
    Write-Host ""
    Write-Host "------------------------------------------------" -ForegroundColor Cyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host "------------------------------------------------" -ForegroundColor Cyan
    Write-Host ""
}
function Say-OK($text)   { Write-Host "[OK]   $text" -ForegroundColor Green }
function Say-Warn($text) { Write-Host "[WARN] $text" -ForegroundColor Yellow }
function Say-Err($text)  { Write-Host "[ERR]  $text" -ForegroundColor Red }
function Say-Step($text) { Write-Host "[..]   $text" }

Say-Header "ORUUN MARKET RADAR - One-shot deploy"

# --- 1. git installed? ----------------------------------------------------
try {
    $gitVer = git --version 2>$null
    Say-OK "Git found: $gitVer"
} catch {
    Say-Err "Git is not installed."
    Write-Host "       Download: https://git-scm.com/download/win" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# --- 2. paths -------------------------------------------------------------
$source = $PSScriptRoot
$destRoot = "C:\dev"
$dest = Join-Path $destRoot "oruun-market-radar"

Write-Host ""
Write-Host "Source : $source"
Write-Host "Target : $dest"
Write-Host ""

# --- 3. copy ---------------------------------------------------------------
if (-not (Test-Path $destRoot)) {
    New-Item -Path $destRoot -ItemType Directory -Force | Out-Null
    Say-OK "Created $destRoot"
}

if (Test-Path $dest) {
    Say-Warn "$dest already exists from a previous run."
    Write-Host "       Recommended: answer Y to wipe and start fresh."
    $answer = Read-Host "Delete it and start fresh? (Y/n)"
    if ([string]::IsNullOrWhiteSpace($answer)) { $answer = "y" }   # default = Yes
    if ($answer -ne "y" -and $answer -ne "Y") {
        Say-Err "Aborted by user. Re-run and choose Y to proceed."
        Read-Host "Press Enter to exit"
        exit 1
    }
    Remove-Item -Recurse -Force $dest
    Say-OK "Removed old copy"
}

Say-Step "Copying project to $dest ..."

# Use robocopy: native Windows tool, handles long paths natively,
# excludes pycache + .git + the deploy scripts in one shot.
# Exit codes 0-7 are success variants; 8+ is failure.
$rcArgs = @(
    "$source",
    "$dest",
    "/E",                               # subdirs incl. empty
    "/R:1", "/W:1",                     # 1 retry, 1s wait
    "/XD", "__pycache__", ".git",       # exclude these dirs
    "/XF", "*.pyc", "deploy.ps1", "deploy.bat",  # exclude these files
    "/NFL", "/NDL", "/NJH", "/NJS", "/NC", "/NS", "/NP"  # quiet output
)
$null = robocopy @rcArgs
if ($LASTEXITCODE -ge 8) {
    Say-Err "robocopy failed with exit code $LASTEXITCODE"
    Read-Host "Press Enter to exit"
    exit 1
}

Say-OK "Copy complete (excluded __pycache__, .git, deploy scripts)"

# --- 4. configure git --------------------------------------------------------
Say-Header "Configure git"
git config --global user.name "Wayne"
git config --global user.email "oruunfit@gmail.com"
git config --global core.longpaths true
git config --global init.defaultBranch main
Say-OK "user.name = Wayne"
Say-OK "user.email = oruunfit@gmail.com"
Say-OK "core.longpaths = true (Windows 260-char path workaround)"

# --- 5. init + first commit -------------------------------------------------
Set-Location $dest
Say-Header "Initialize git repo at $dest"
git init -q
git add .
git commit -q -m "init: ORUUN Market Radar v0.2 (5 free data sources)"
git branch -M main
Say-OK "Initial commit created"

# --- 6. GitHub repo prompt --------------------------------------------------
Say-Header "GitHub repo setup"
Write-Host "I will open https://github.com/new in your browser now."
Write-Host ""
Write-Host "  - Repository name : oruun-market-radar"
Write-Host "  - Visibility      : PUBLIC  (required for free GitHub Pages)"
Write-Host "  - DO NOT tick     : README / .gitignore / license"
Write-Host "  - Click           : Create repository"
Write-Host ""
Start-Process "https://github.com/new"

Write-Host ""
$ghUser = Read-Host "Enter your GitHub username"
if ([string]::IsNullOrWhiteSpace($ghUser)) {
    Say-Err "Empty username. Aborting."
    Read-Host "Press Enter to exit"
    exit 1
}

$repoUrl = "https://github.com/$ghUser/oruun-market-radar.git"
Say-Step "Adding remote: $repoUrl"
git remote add origin $repoUrl

# --- 7. push ----------------------------------------------------------------
Say-Header "Push to GitHub"
Write-Host "(A login window may pop up. Sign in to GitHub if prompted.)"
Write-Host ""
git push -u origin main

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Say-Err "Push failed."
    Write-Host "       Most common cause: the GitHub repo doesn't exist yet, or username is misspelled."
    Write-Host "       After creating the repo at https://github.com/new, retry with:" -ForegroundColor Yellow
    Write-Host "         cd $dest" -ForegroundColor Yellow
    Write-Host "         git push -u origin main" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Say-OK "Push successful!"

# --- 8. final ---------------------------------------------------------------
$repoWeb    = "https://github.com/$ghUser/oruun-market-radar"
$pagesUrl   = "$repoWeb/settings/pages"
$actionsUrl = "$repoWeb/settings/actions"
$siteUrl    = "https://$ghUser.github.io/oruun-market-radar/"

Say-Header "TWO BROWSER STEPS LEFT"
Write-Host "[1] Enable GitHub Pages"
Write-Host "    URL    : $pagesUrl"
Write-Host "    Source : Deploy from a branch"
Write-Host "    Branch : main      Folder : /docs"
Write-Host "    Click  : Save"
Write-Host ""
Write-Host "[2] Allow Actions to commit data back"
Write-Host "    URL    : $actionsUrl"
Write-Host "    Scroll to: Workflow permissions"
Write-Host "    Tick   : Read and write permissions"
Write-Host "    Click  : Save"
Write-Host ""
Write-Host "[3] Trigger first data refresh"
Write-Host "    URL    : $repoWeb/actions"
Write-Host "    Pick   : Weekly Market Radar Update"
Write-Host "    Click  : Run workflow > Run workflow"
Write-Host "    Wait   : ~5 minutes"
Write-Host ""
Write-Host "Your live dashboard:"
Write-Host "    $siteUrl" -ForegroundColor Green
Write-Host ""

Start-Process $pagesUrl
Start-Sleep -Seconds 1
Start-Process $actionsUrl

Write-Host "(Both settings pages are now open in your browser.)" -ForegroundColor DarkGray
Write-Host ""
Read-Host "Press Enter to close this window"
