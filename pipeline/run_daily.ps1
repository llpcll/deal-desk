# Run by the "The Deal Desk daily episode" scheduled task at 6:45, 7:30 and at logon (daily.py publishes at most one a day).
# Claude only writes the script; rendering, building and pushing happen here, outside Claude,
# and daily.py refuses to push anything outside scripts/, content/, audio/, site/, published.json.
param([switch]$DryRun)   # -DryRun: write and render a short test script, publish nothing
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"
if ($DryRun) { & python -u pipeline\daily.py --dry-run } else { & python -u pipeline\daily.py }
exit $LASTEXITCODE
