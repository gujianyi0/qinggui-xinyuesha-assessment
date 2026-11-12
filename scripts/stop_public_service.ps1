$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$folder = Join-Path $projectRoot '.local\public-entry'
New-Item -Path (Join-Path $folder 'stop') -ItemType File -Force | Out-Null
Write-Output 'Public entry stop requested. Local Docker and its billing ledger remain running.'
