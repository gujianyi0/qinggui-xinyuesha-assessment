$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$configFile = Join-Path $projectRoot '.env.docker-live'
if (!(Test-Path -LiteralPath $configFile)) { throw 'Private .env.docker-live is missing; prepare the live configuration first.' }
$stateFile = Join-Path $projectRoot '.local\deployment.json'
if (!(Test-Path -LiteralPath $stateFile)) { throw 'Migrate the source database before starting the live deployment.' }
$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
if ($state.owner -ne 'qinggui-assessment-deployment' -or $state.project -ne $projectRoot -or $state.primary -ne 'docker') { throw 'Docker is not the checked primary; migration is required.' }
$docker = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
if (!(Test-Path -LiteralPath $docker)) { $docker = (Get-Command docker -ErrorAction Stop).Source }
$env:PATH = "$(Split-Path -Parent $docker);$env:PATH"
$env:ASSESSMENT_ENV_FILE = '.env.docker-live'
Push-Location -LiteralPath $projectRoot
try {
    & $docker desktop start
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop did not start.' }
    & $docker compose --env-file .env.docker-live -p qinggui-assessment-live -f compose.yaml -f compose.live.yaml up -d --no-build --wait --wait-timeout 180
    if ($LASTEXITCODE -ne 0) { throw 'Live Compose startup failed; original database remains preserved.' }
    Write-Output 'Docker live preview: http://127.0.0.1:15174 . Do not start the stale native copy.'
} finally { Pop-Location }
