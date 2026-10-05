# Run by the "The Deal Desk backfill" scheduled task at 10:00 (Gemini's daily limit
# resets at 00:00 UTC) until Season 1 is rendered. Keeps 20 requests for the 6:45 job.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONIOENCODING = "utf-8"
New-Item -ItemType Directory -Force logs | Out-Null
& python -u pipeline\backfill.py *>> ("logs\backfill-{0:yyyy-MM-dd}.log" -f (Get-Date))
exit $LASTEXITCODE
