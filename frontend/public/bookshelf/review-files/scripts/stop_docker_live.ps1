$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$docker = Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop\resources\bin\docker.exe'
if (!(Test-Path -LiteralPath $docker)) { $docker = (Get-Command docker -ErrorAction Stop).Source }
$env:PATH = "$(Split-Path -Parent $docker);$env:PATH"
$env:ASSESSMENT_ENV_FILE = '.env.docker-live'
Push-Location -LiteralPath $projectRoot
try {
    & $docker compose --env-file .env.docker-live -p qinggui-assessment-live -f compose.yaml -f compose.live.yaml stop
    if ($LASTEXITCODE -ne 0) { throw 'Live Compose stop failed.' }
    Write-Output 'Live containers stopped; volumes and the primary-database marker remain. Start with start_docker_live.ps1.'
} finally { Pop-Location }
