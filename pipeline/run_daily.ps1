# Run by the "The Deal Desk daily episode" scheduled task at 6:45.
# Claude only writes the script; rendering, building and pushing happen here, outside Claude,
# and daily.py refuses to push anything outside scripts/, content/, audio/, site/, published.json.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
$env:PYTHONIOENCODING = "utf-8"
& python -u pipeline\daily.py
exit $LASTEXITCODE
