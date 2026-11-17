param([switch]$SkipDockerStart)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$folder = Join-Path $projectRoot '.local\public-entry'
if (!(Test-Path -LiteralPath (Join-Path $folder 'config.json'))) { throw 'Configure the private public entry first; see docs/本机对外服务.md.' }
if (!$SkipDockerStart) { & (Join-Path $PSScriptRoot 'start_docker_live.ps1') }
$listener = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 18084 -ErrorAction SilentlyContinue
if ($listener) { Write-Output 'Public entry supervisor is already running.'; return }
Remove-Item -LiteralPath (Join-Path $folder 'stop') -Force -ErrorAction SilentlyContinue
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
Start-Process -FilePath $python -ArgumentList '-m', 'scripts.public_service' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $folder 'supervisor.log') -RedirectStandardError (Join-Path $folder 'supervisor-error.log')
Write-Output 'Public entry is starting. Read .local/public-entry/status.json for status.'
