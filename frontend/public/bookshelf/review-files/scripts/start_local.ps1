param(
    [int]$WebPort = 15173,
    [int]$ApiPort = 18080
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$localDir = Join-Path $projectRoot '.local'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendDir = Join-Path $projectRoot 'frontend'
$nodePath = (Get-Command node -ErrorAction Stop).Source
$statePath = Join-Path $localDir 'preview-processes.json'
if (!(Test-Path -LiteralPath $pythonPath) -or !(Test-Path -LiteralPath (Join-Path $frontendDir 'node_modules\vite\bin\vite.js'))) {
    throw 'Install project dependencies first: uv sync --frozen --extra dev; then run npm ci in frontend.'
}
New-Item -ItemType Directory -Path $localDir -Force | Out-Null

function Wait-Http([string]$Url, [int]$Seconds = 45) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            return Invoke-RestMethod -Uri $Url -TimeoutSec 2 -NoProxy
        } catch {
            Start-Sleep -Milliseconds 400
        }
    } while ((Get-Date) -lt $deadline)
    throw "Service did not become ready: $Url. Check .local/preview-*.log."
}

$apiUrl = "http://127.0.0.1:$ApiPort"
$webUrl = "http://127.0.0.1:$WebPort"
$occupied = @(Get-NetTCPConnection -State Listen -LocalPort $ApiPort,$WebPort -ErrorAction SilentlyContinue)
if ($occupied.Count -gt 0) {
    if (Test-Path -LiteralPath $statePath) {
        $previous = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($previous.web_port -eq $WebPort -and $previous.api_port -eq $ApiPort -and $occupied.Count -eq 2) {
            $health = Wait-Http "$apiUrl/health" 5
            $null = Wait-Http "$webUrl/api/health" 5
            if ($health.model_mode -eq 'mock' -and $health.database -eq 'sqlite') {
                Write-Output "Already running: $webUrl"
                return
            }
        }
    }
    throw "A preview port is occupied. Choose different -WebPort / -ApiPort values. Existing processes were preserved."
}

$api = Start-Process -FilePath $pythonPath -ArgumentList @('scripts/local_demo.py', '--port', "$ApiPort", '--database', '.local/verification.sqlite3') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir 'preview-api.log') -RedirectStandardError (Join-Path $localDir 'preview-api-error.log')
$null = Wait-Http "$apiUrl/health"
$previousProxy = $env:API_PROXY_TARGET
try {
    $env:API_PROXY_TARGET = $apiUrl
    $web = Start-Process -FilePath $nodePath -ArgumentList @('node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', "$WebPort") -WorkingDirectory $frontendDir -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $localDir 'preview-web.log') -RedirectStandardError (Join-Path $localDir 'preview-web-error.log')
} finally {
    if ($null -eq $previousProxy) { Remove-Item Env:API_PROXY_TARGET -ErrorAction SilentlyContinue }
    else { $env:API_PROXY_TARGET = $previousProxy }
}
$null = Wait-Http "$webUrl/api/health"
@{web_pid=$web.Id; api_launcher_pid=$api.Id; web_port=$WebPort; api_port=$ApiPort; started_at=(Get-Date).ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding utf8
Write-Output "Ready: $webUrl"
Write-Output "API: $apiUrl/docs"
Write-Output 'Login: alice or bob, with your project DEMO_PASSWORD (default: local-demo-change-me).'
