param([switch]$SkipBuild)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    # The preview shares the already-running API, without starting or restarting it.
    $health = Invoke-RestMethod 'http://127.0.0.1:18081/health' -TimeoutSec 10
    if (-not $health.status) { throw 'Existing local API did not return health status.' }
    if (-not $SkipBuild) {
        Push-Location frontend
        try {
            npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
            npm.cmd run build:local
            if ($LASTEXITCODE -ne 0) { throw 'Local preview build failed' }
        } finally { Pop-Location }
    }
    if (-not (Test-Path -LiteralPath frontend/dist/index.html)) { throw 'Build frontend/dist first.' }
    $manifest = Get-Content -LiteralPath frontend/dist/v2-build.json -Raw | ConvertFrom-Json
    $expectedVersion = (Get-Content -LiteralPath VERSION -Raw).Trim()
    if ($manifest.version -ne $expectedVersion -or $manifest.scope -ne 'local-internal-preview') {
        throw 'The selected artifact is not the v2 local preview. Rebuild without -SkipBuild.'
    }
    docker compose -p qinggui-assessment-v2-local -f compose.v2-local.yaml up -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'v2 local preview failed to start' }
    Write-Host 'v2 local preview: http://127.0.0.1:15180/ (15174 remains unchanged)'
} finally { Pop-Location }
