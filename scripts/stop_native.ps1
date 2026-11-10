$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$stateDir = Join-Path $projectRoot '.local\native-demo'
$stateFile = Join-Path $stateDir 'status.json'
if (!(Test-Path -LiteralPath $stateFile)) { Write-Output 'Native preview has not started.'; return }
$state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
if ($state.owner -ne 'qinggui-assessment-native-demo' -or $state.project -ne $projectRoot) { throw 'Unknown native-demo state; preserved.' }
Set-Content -LiteralPath (Join-Path $stateDir 'stop.request') -Value 'Stop requested by local operator.' -Encoding utf8
Write-Output 'Stop requested. The supervisor will stop its own services and preserve the databases.'
