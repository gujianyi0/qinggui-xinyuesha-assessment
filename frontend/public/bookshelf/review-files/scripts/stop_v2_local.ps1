$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    docker compose -p qinggui-assessment-v2-local -f compose.v2-local.yaml down
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop v2 preview' }
} finally { Pop-Location }
