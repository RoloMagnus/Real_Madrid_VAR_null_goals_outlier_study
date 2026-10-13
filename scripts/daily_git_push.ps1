# Daily auto-commit and push for the Real Madrid VAR project.
# - Commits only when there are changes; never force-pushes; skips if any changed file is > 50 MB.
# - Credentials come from the Git Credential Manager (already authorised for this repo).
$ErrorActionPreference = 'Continue'
$repo = Split-Path -Parent $PSScriptRoot
$log = Join-Path $repo 'data\daily_push.log'
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Out-File -FilePath $log -Append -Encoding utf8 }
Set-Location $repo
$env:GIT_TERMINAL_PROMPT = '0'

if (-not (Test-Path '.git')) { Log 'ERROR not a git repository'; exit 1 }
git add -A 2>$null
$staged = git diff --cached --name-only
if (-not $staged) { Log 'No changes - nothing to push'; exit 0 }

$big = $staged | ForEach-Object { Get-Item -LiteralPath $_ -ErrorAction SilentlyContinue } | Where-Object { $_.Length -gt 50MB }
if ($big) {
    git reset -q
    Log ("ABORTED: files over 50 MB: " + (($big | ForEach-Object Name) -join ', '))
    exit 2
}

$n = ($staged | Measure-Object).Count
git commit -q -m "Daily update $(Get-Date -Format 'yyyy-MM-dd'): $n file(s) changed

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { Log 'ERROR commit failed'; exit 3 }

$out = git push origin main 2>&1 | Out-String
if ($LASTEXITCODE -eq 0) { Log "Pushed $n file(s)" } else { Log ("ERROR push failed: " + $out.Trim()); exit 4 }
